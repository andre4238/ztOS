// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * ztGlass: the compositor of ztOS's Glass shell, a phone's way of showing
 * windows: one app at a time, full screen, and the home screen under them.
 *
 * It draws next to nothing itself. The home screen, the status bar and the
 * lock screen are the shell's (ztglass-shell, a layer-shell client); this
 * keeps the windows, the touch screen, the keys and the gestures:
 *
 *   swipe up from the bottom edge     back to the home screen
 *   swipe in from the left edge       back (Escape to the app)
 *   power key                         screen off and on (the shell locks)
 *   volume keys                       the default sink's volume
 *
 * The shell talks to it over $XDG_RUNTIME_DIR/ztglass.sock, a line at a time:
 *
 *   launch KEY COMMAND...   open the app KEY (its window if it has one)
 *   home                    the home screen
 *   close KEY               ask the app KEY to close
 *
 * and hears back:  home | app KEY | blank 0|1 | volume up|down | apps KEY...
 */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <linux/input-event-codes.h>
#include <math.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <cairo.h>
#include <drm_fourcc.h>
#include <wayland-server-core.h>
#include <xkbcommon/xkbcommon.h>

#include <wlr/backend.h>
#include <wlr/interfaces/wlr_buffer.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_fractional_scale_v1.h>
#include <wlr/types/wlr_input_device.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_layer_shell_v1.h>
#include <wlr/types/wlr_linux_dmabuf_v1.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_presentation_time.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_screencopy_v1.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_single_pixel_buffer_v1.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_touch.h>
#include <wlr/types/wlr_viewporter.h>
#include <wlr/types/wlr_xdg_decoration_v1.h>
#include <wlr/types/wlr_xdg_output_v1.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/util/log.h>

#define EDGE_BOTTOM	22.0	/* points: where the home swipe starts */
#define EDGE_LEFT	14.0	/* where the back swipe starts */
#define GESTURE_H	16.0	/* the strip under apps, for the home bar */
#define HOME_DISTANCE	90.0	/* how far up a swipe must go to go home */
#define BACK_DISTANCE	70.0
#define FLICK_SPEED	0.45	/* points per ms: a quick flick is enough too */
#define MAX_TOUCH	10
#define MAX_CLIENTS	8
#define MAX_PENDING	8

enum touch_role { TOUCH_NONE, TOUCH_CLIENT, TOUCH_HOME, TOUCH_BACK, TOUCH_EATEN };

struct touch_slot {
	int32_t id;
	enum touch_role role;
	double x0, y0, x, y;		/* layout points */
	double ox, oy;			/* the touched surface's origin */
	uint32_t t0, t;
	double vy, vx;			/* points per ms, lately */
};

struct ztg_server;

struct anim {
	bool on;
	uint32_t t0, ms;
	float from, to;
	void (*done)(struct ztg_server *);
};

struct ztg_server {
	struct wl_display *display;
	struct wl_event_loop *loop;
	struct wlr_backend *backend;
	struct wlr_session *session;
	struct wlr_renderer *renderer;
	struct wlr_allocator *allocator;
	struct wlr_scene *scene;
	struct wlr_scene_output_layout *scene_layout;
	struct wlr_output_layout *output_layout;
	struct wlr_output *output;	/* the phone has the one */
	struct wlr_scene_output *scene_output;

	/* back to front */
	struct wlr_scene_tree *layer_bg, *layer_bottom, *apps, *layer_top, *layer_overlay, *chrome;
	struct wlr_scene_rect *app_black;	/* behind an app: the status bar and the home bar on black */
	struct wlr_scene_buffer *home_bar;
	struct wlr_scene_rect *blank;

	struct wlr_xdg_shell *xdg_shell;
	struct wlr_layer_shell_v1 *layer_shell;
	struct wlr_xdg_decoration_manager_v1 *decorations;
	struct wlr_seat *seat;
	struct wlr_cursor *cursor;
	struct wlr_keyboard vkbd;	/* what the seat's keyboard is: the back key, and keys passed on */
	struct wl_list views, layers, keyboards;
	struct wl_listener new_output, new_input, new_toplevel, new_popup, new_layer, new_decoration;
	struct wl_listener touch_down, touch_up, touch_motion, touch_cancel, touch_frame;

	struct wlr_box full, usable, app_box;
	struct ztg_view *shown;
	float offset, alpha;		/* the shown app's slide (points, up < 0) and fade */
	struct anim anim;
	bool blanked;
	float scale;

	struct touch_slot touches[MAX_TOUCH];

	int listen_fd;
	int clients[MAX_CLIENTS];
	struct wl_event_source *client_src[MAX_CLIENTS];
	char client_buf[MAX_CLIENTS][1024];
	size_t client_len[MAX_CLIENTS];
	char sock_path[256];

	struct { pid_t pid; char key[128]; uint32_t at; } pending[MAX_PENDING];
	char *shell_cmd;
	pid_t shell_pid;
	struct wl_event_source *shell_timer;
};

struct ztg_view {
	struct wl_list link;
	struct ztg_server *server;
	struct wlr_xdg_toplevel *toplevel;
	struct wlr_scene_tree *tree;
	struct wlr_xdg_toplevel_decoration_v1 *decoration;
	struct wl_listener map, unmap, commit, destroy, request_fullscreen, request_maximize;
	struct wl_listener deco_mode, deco_destroy;
	char key[128];
	bool mapped;
};

struct ztg_layer {
	struct wl_list link;
	struct ztg_server *server;
	struct wlr_layer_surface_v1 *surface;
	struct wlr_scene_layer_surface_v1 *scene;
	struct wl_listener map, unmap, commit, destroy, new_popup;
};

struct ztg_popup {
	struct wlr_xdg_popup *popup;
	struct wl_listener commit, destroy;
};

struct ztg_keyboard {
	struct wl_list link;
	struct ztg_server *server;
	struct wlr_keyboard *keyboard;
	struct wl_listener key, destroy;
};

static uint32_t now_ms(void) {
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

/* ---- the shell's socket ------------------------------------------------------------- */

static void tell(struct ztg_server *server, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void tell(struct ztg_server *server, const char *fmt, ...) {
	char line[1024];
	va_list ap;
	va_start(ap, fmt);
	int n = vsnprintf(line, sizeof(line) - 1, fmt, ap);
	va_end(ap);
	if (n < 0) {
		return;
	}
	n = n > (int)sizeof(line) - 2 ? (int)sizeof(line) - 2 : n;
	line[n++] = '\n';
	for (int i = 0; i < MAX_CLIENTS; i++) {
		if (server->clients[i] >= 0) {
			/* a shell that does not read loses lines, it never holds us up */
			(void)!send(server->clients[i], line, n, MSG_DONTWAIT | MSG_NOSIGNAL);
		}
	}
}

static void tell_apps(struct ztg_server *server) {
	char line[1000] = "apps";
	struct ztg_view *view;
	wl_list_for_each(view, &server->views, link) {
		if (view->mapped && view->key[0] && strlen(line) + strlen(view->key) + 2 < sizeof(line)) {
			strcat(line, " ");
			strcat(line, view->key);
		}
	}
	tell(server, "%s", line);
}

/* ---- running things ------------------------------------------------------------------ */

static pid_t spawn(const char *command) {
	pid_t pid = fork();
	if (pid == 0) {
		sigset_t none;
		sigemptyset(&none);
		sigprocmask(SIG_SETMASK, &none, NULL);
		signal(SIGCHLD, SIG_DFL);
		signal(SIGPIPE, SIG_DFL);
		setsid();
		execl("/bin/sh", "/bin/sh", "-c", command, (char *)NULL);
		_exit(127);
	}
	return pid;
}

static int start_shell(void *data) {
	struct ztg_server *server = data;
	if (server->shell_cmd) {
		server->shell_pid = spawn(server->shell_cmd);
		wlr_log(WLR_INFO, "shell: started %s as %d", server->shell_cmd, server->shell_pid);
	}
	return 0;
}

static int on_sigchld(int signal_number, void *data) {
	struct ztg_server *server = data;
	pid_t pid;
	int status;
	while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
		if (pid == server->shell_pid) {
			/* the shell went: it comes back in a second, the apps stay */
			wlr_log(WLR_ERROR, "shell: %d ended (status %d), starting it again", pid, status);
			server->shell_pid = 0;
			wl_event_source_timer_update(server->shell_timer, 1000);
		}
	}
	return 0;
}

static pid_t parent_of(pid_t pid) {
	char path[64], buf[512];
	snprintf(path, sizeof(path), "/proc/%d/stat", pid);
	FILE *f = fopen(path, "r");
	if (!f) {
		return 0;
	}
	size_t n = fread(buf, 1, sizeof(buf) - 1, f);
	fclose(f);
	buf[n] = 0;
	char *end = strrchr(buf, ')');	/* the name may hold anything, the fields follow its ')' */
	int ppid = 0;
	char state;
	if (!end || sscanf(end + 1, " %c %d", &state, &ppid) != 2) {
		return 0;
	}
	return ppid;
}

/* ---- the layout --------------------------------------------------------------------------- */

static void place_view(struct ztg_view *view) {
	struct ztg_server *server = view->server;
	wlr_scene_node_set_position(&view->tree->node, server->app_box.x,
		server->app_box.y + (view == server->shown ? (int)lroundf(server->offset) : 0));
}

static void configure_view(struct ztg_view *view) {
	struct ztg_server *server = view->server;
	if (!view->toplevel->base->initialized) {
		return;
	}
	wlr_xdg_toplevel_set_size(view->toplevel, server->app_box.width, server->app_box.height);
	wlr_xdg_toplevel_set_maximized(view->toplevel, true);
	wlr_xdg_toplevel_set_tiled(view->toplevel, WLR_EDGE_TOP | WLR_EDGE_BOTTOM | WLR_EDGE_LEFT | WLR_EDGE_RIGHT);
	place_view(view);
}

static void arrange_layer(struct ztg_server *server, enum zwlr_layer_shell_v1_layer which, bool exclusive) {
	struct ztg_layer *layer;
	wl_list_for_each(layer, &server->layers, link) {
		struct wlr_layer_surface_v1 *s = layer->surface;
		if (!s->initialized || s->current.layer != which) {
			continue;
		}
		if ((s->current.exclusive_zone > 0) != exclusive) {
			continue;
		}
		wlr_scene_layer_surface_v1_configure(layer->scene, &server->full, &server->usable);
	}
}

static void arrange(struct ztg_server *server) {
	if (!server->output) {
		return;
	}
	wlr_output_layout_get_box(server->output_layout, server->output, &server->full);
	server->usable = server->full;
	/* those that take space first, then those that only lie on what is left */
	for (int pass = 0; pass < 2; pass++) {
		for (int l = ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY; l >= ZWLR_LAYER_SHELL_V1_LAYER_BACKGROUND; l--) {
			arrange_layer(server, l, pass == 0);
		}
	}
	server->app_box = server->usable;
	server->app_box.height -= (int)GESTURE_H;
	wlr_scene_rect_set_size(server->app_black, server->full.width, server->full.height);
	wlr_scene_rect_set_size(server->blank, server->full.width, server->full.height);
	if (server->home_bar) {
		int w = server->home_bar->dst_width, h = server->home_bar->dst_height;
		wlr_scene_node_set_position(&server->home_bar->node, (server->full.width - w) / 2,
			server->full.height - (int)(GESTURE_H / 2) - h / 2);
	}
	struct ztg_view *view;
	wl_list_for_each(view, &server->views, link) {
		configure_view(view);
	}
}

/* ---- cairo pictures as scene buffers --------------------------------------------------------- */

struct cairo_buffer {
	struct wlr_buffer base;
	cairo_surface_t *surface;
};

static void cbuf_destroy(struct wlr_buffer *buffer) {
	struct cairo_buffer *b = wl_container_of(buffer, b, base);
	cairo_surface_destroy(b->surface);
	free(b);
}

static bool cbuf_begin(struct wlr_buffer *buffer, uint32_t flags, void **data, uint32_t *format, size_t *stride) {
	struct cairo_buffer *b = wl_container_of(buffer, b, base);
	if (flags & WLR_BUFFER_DATA_PTR_ACCESS_WRITE) {
		return false;
	}
	*data = cairo_image_surface_get_data(b->surface);
	*format = DRM_FORMAT_ARGB8888;
	*stride = cairo_image_surface_get_stride(b->surface);
	return true;
}

static void cbuf_end(struct wlr_buffer *buffer) {
}

static const struct wlr_buffer_impl cbuf_impl = {
	.destroy = cbuf_destroy,
	.begin_data_ptr_access = cbuf_begin,
	.end_data_ptr_access = cbuf_end,
};

/* The home bar: a short rounded line, light on the black under apps. */
static void make_home_bar(struct ztg_server *server) {
	double w = 128, h = 5, s = server->scale;
	int pw = (int)ceil(w * s), ph = (int)ceil(h * s);
	struct cairo_buffer *b = calloc(1, sizeof(*b));
	b->surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, pw, ph);
	cairo_t *cr = cairo_create(b->surface);
	cairo_scale(cr, s, s);
	double r = h / 2;
	cairo_new_sub_path(cr);
	cairo_arc(cr, w - r, r, r, -M_PI / 2, M_PI / 2);
	cairo_arc(cr, r, r, r, M_PI / 2, 3 * M_PI / 2);
	cairo_close_path(cr);
	cairo_set_source_rgba(cr, 1, 1, 1, 0.85);
	cairo_fill(cr);
	cairo_destroy(cr);
	cairo_surface_flush(b->surface);
	wlr_buffer_init(&b->base, &cbuf_impl, pw, ph);
	if (server->home_bar) {
		wlr_scene_node_destroy(&server->home_bar->node);
	}
	server->home_bar = wlr_scene_buffer_create(server->chrome, &b->base);
	wlr_scene_buffer_set_dest_size(server->home_bar, (int)w, (int)h);
	wlr_buffer_drop(&b->base);
	wlr_scene_node_set_enabled(&server->home_bar->node, server->shown != NULL);
}

/* ---- showing an app, or none ----------------------------------------------------------------- */

static void set_opacity(struct wlr_scene_buffer *buffer, int sx, int sy, void *data) {
	wlr_scene_buffer_set_opacity(buffer, *(float *)data);
}

static void apply_motion(struct ztg_server *server) {
	if (!server->shown) {
		return;
	}
	place_view(server->shown);
	float a = server->alpha;
	wlr_scene_node_for_each_buffer(&server->shown->tree->node, set_opacity, &a);
	/* the black goes with the app, so the home screen shows through as it leaves */
	float black[4] = { 0, 0, 0, a };
	wlr_scene_rect_set_color(server->app_black, black);
}

static void focus(struct ztg_server *server, struct wlr_surface *surface) {
	if (!surface) {
		wlr_seat_keyboard_notify_clear_focus(server->seat);
		return;
	}
	wlr_seat_keyboard_notify_enter(server->seat, surface, server->vkbd.keycodes,
		server->vkbd.num_keycodes, &server->vkbd.modifiers);
}

static void animate(struct ztg_server *server, float from, float to, uint32_t ms, void (*done)(struct ztg_server *)) {
	server->anim = (struct anim){ .on = true, .t0 = now_ms(), .ms = ms, .from = from, .to = to, .done = done };
	if (server->output) {
		wlr_output_schedule_frame(server->output);
	}
}

/* An app, or the home screen (NULL), now; no motion. */
static void show(struct ztg_server *server, struct ztg_view *view) {
	struct ztg_view *v;
	wl_list_for_each(v, &server->views, link) {
		wlr_xdg_toplevel_set_activated(v->toplevel, v == view);
		wlr_scene_node_set_enabled(&v->tree->node, v == view && v->mapped);
	}
	if (server->shown && server->shown != view) {
		float one = 1.0f;
		wlr_scene_node_for_each_buffer(&server->shown->tree->node, set_opacity, &one);
	}
	server->shown = view;
	server->offset = 0;
	server->alpha = 1;
	wlr_scene_node_set_enabled(&server->app_black->node, view != NULL);
	if (server->home_bar) {
		wlr_scene_node_set_enabled(&server->home_bar->node, view != NULL);
	}
	if (view) {
		wlr_scene_node_raise_to_top(&view->tree->node);
		apply_motion(server);
		focus(server, view->toplevel->base->surface);
		tell(server, "app %s", view->key[0] ? view->key : "-");
	} else {
		focus(server, NULL);
		tell(server, "home");
	}
}

static void went_home(struct ztg_server *server) {
	show(server, NULL);
}

static void settle(struct ztg_server *server) {
	server->offset = 0;
	server->alpha = 1;
	apply_motion(server);
}

static void go_home(struct ztg_server *server) {
	if (!server->shown) {
		tell(server, "home");	/* already: the shell takes it as "first page" */
		return;
	}
	/* from where the finger left it, on up and away */
	server->anim.on = false;
	animate(server, server->offset, -(float)server->full.height * 0.45f, 220, went_home);
}

static void open_view(struct ztg_server *server, struct ztg_view *view) {
	show(server, view);
	/* it rises a little into place as it fades in */
	server->offset = 36;
	server->alpha = 0;
	apply_motion(server);
	animate(server, 36, 0, 210, settle);
}

static void step_animation(struct ztg_server *server) {
	struct anim *a = &server->anim;
	if (!a->on) {
		return;
	}
	float t = a->ms ? (float)(now_ms() - a->t0) / a->ms : 1.0f;
	t = t > 1 ? 1 : t < 0 ? 0 : t;
	float e = 1 - powf(1 - t, 3);	/* ease out */
	server->offset = a->from + (a->to - a->from) * e;
	/* fade with the travel: in when it rises to 0, out as it goes up */
	if (a->to == 0) {
		server->alpha = a->from != 0 ? 1 - fabsf(server->offset / a->from) * (a->from > 0 ? 1 : 0.6f) : 1;
	} else {
		server->alpha = 1 - fminf(1, fabsf(server->offset) / fabsf(a->to)) * 0.9f;
	}
	server->alpha = server->alpha < 0 ? 0 : server->alpha > 1 ? 1 : server->alpha;
	apply_motion(server);
	if (t >= 1) {
		a->on = false;
		if (a->done) {
			a->done(server);
		}
	} else {
		wlr_output_schedule_frame(server->output);
	}
}

static struct ztg_view *view_by_key(struct ztg_server *server, const char *key) {
	struct ztg_view *view;
	wl_list_for_each(view, &server->views, link) {
		if (view->mapped && view->key[0] && strcmp(view->key, key) == 0) {
			return view;
		}
	}
	return NULL;
}

/* ---- the keys ------------------------------------------------------------------------------ */

static void set_blank(struct ztg_server *server, bool blanked) {
	server->blanked = blanked;
	wlr_scene_node_set_enabled(&server->blank->node, blanked);
	wlr_scene_node_raise_to_top(&server->blank->node);
	tell(server, "blank %d", blanked);
	wlr_log(WLR_INFO, "screen %s", blanked ? "off" : "on");
	if (blanked) {
		/* the fingers on it now lift */
		for (int i = 0; i < MAX_TOUCH; i++) {
			if (server->touches[i].role == TOUCH_CLIENT) {
				wlr_seat_touch_notify_up(server->seat, now_ms(), server->touches[i].id);
			}
			server->touches[i].role = TOUCH_NONE;
		}
	}
}

static void send_key(struct ztg_server *server, uint32_t keycode) {
	uint32_t t = now_ms();
	wlr_seat_set_keyboard(server->seat, &server->vkbd);
	wlr_seat_keyboard_notify_key(server->seat, t, keycode, WL_KEYBOARD_KEY_STATE_PRESSED);
	wlr_seat_keyboard_notify_key(server->seat, t + 1, keycode, WL_KEYBOARD_KEY_STATE_RELEASED);
}

static void keyboard_key(struct wl_listener *listener, void *data) {
	struct ztg_keyboard *kb = wl_container_of(listener, kb, key);
	struct ztg_server *server = kb->server;
	struct wlr_keyboard_key_event *event = data;
	bool down = event->state == WL_KEYBOARD_KEY_STATE_PRESSED;
	switch (event->keycode) {
	case KEY_POWER:
		if (down) {
			set_blank(server, !server->blanked);
		}
		return;
	case KEY_VOLUMEUP:
	case KEY_VOLUMEDOWN:
		if (down && !server->blanked) {
			bool up = event->keycode == KEY_VOLUMEUP;
			spawn(up ? "wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 6%+" :
				"wpctl set-volume @DEFAULT_AUDIO_SINK@ 6%-");
			tell(server, "volume %s", up ? "up" : "down");
		}
		return;
	case KEY_HOMEPAGE:
		if (down) {
			go_home(server);
		}
		return;
	case KEY_BACK:
		if (down) {
			send_key(server, KEY_ESC);
		}
		return;
	}
	if (server->blanked) {
		return;
	}
	wlr_seat_set_keyboard(server->seat, &server->vkbd);
	wlr_seat_keyboard_notify_key(server->seat, event->time_msec, event->keycode, event->state);
}

static void keyboard_destroy(struct wl_listener *listener, void *data) {
	struct ztg_keyboard *kb = wl_container_of(listener, kb, destroy);
	wl_list_remove(&kb->key.link);
	wl_list_remove(&kb->destroy.link);
	wl_list_remove(&kb->link);
	free(kb);
}

static void vkbd_leds(struct wlr_keyboard *keyboard, uint32_t leds) {
}

static const struct wlr_keyboard_impl vkbd_impl = {
	.name = "ztglass-keys",
	.led_update = vkbd_leds,
};

static struct xkb_keymap *default_keymap(void) {
	struct xkb_context *context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
	struct xkb_keymap *keymap = xkb_keymap_new_from_names(context, NULL, XKB_KEYMAP_COMPILE_NO_FLAGS);
	xkb_context_unref(context);
	return keymap;
}

/* ---- touch ---------------------------------------------------------------------------------- */

static struct touch_slot *slot_for(struct ztg_server *server, int32_t id, bool make) {
	for (int i = 0; i < MAX_TOUCH; i++) {
		if (server->touches[i].role != TOUCH_NONE && server->touches[i].id == id) {
			return &server->touches[i];
		}
	}
	if (!make) {
		return NULL;
	}
	for (int i = 0; i < MAX_TOUCH; i++) {
		if (server->touches[i].role == TOUCH_NONE) {
			server->touches[i] = (struct touch_slot){ .id = id };
			return &server->touches[i];
		}
	}
	return NULL;
}

static bool gesture_running(struct ztg_server *server) {
	for (int i = 0; i < MAX_TOUCH; i++) {
		if (server->touches[i].role == TOUCH_HOME || server->touches[i].role == TOUCH_BACK) {
			return true;
		}
	}
	return false;
}

static struct wlr_surface *surface_at(struct ztg_server *server, double lx, double ly, double *sx, double *sy) {
	struct wlr_scene_node *node = wlr_scene_node_at(&server->scene->tree.node, lx, ly, sx, sy);
	if (!node || node->type != WLR_SCENE_NODE_BUFFER) {
		return NULL;
	}
	struct wlr_scene_surface *ss = wlr_scene_surface_try_from_buffer(wlr_scene_buffer_from_node(node));
	return ss ? ss->surface : NULL;
}

static void touch_down(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, touch_down);
	struct wlr_touch_down_event *event = data;
	double lx, ly;
	wlr_cursor_absolute_to_layout_coords(server->cursor, &event->touch->base, event->x, event->y, &lx, &ly);
	struct touch_slot *slot = slot_for(server, event->touch_id, true);
	if (!slot) {
		return;
	}
	slot->x0 = slot->x = lx;
	slot->y0 = slot->y = ly;
	slot->t0 = slot->t = event->time_msec;
	if (server->blanked || server->anim.on || gesture_running(server)) {
		slot->role = TOUCH_EATEN;
		return;
	}
	if (server->shown && ly >= server->full.height - EDGE_BOTTOM) {
		slot->role = TOUCH_HOME;
		return;
	}
	if (server->shown && lx <= EDGE_LEFT && ly > server->app_box.y) {
		slot->role = TOUCH_BACK;
		return;
	}
	double sx, sy;
	struct wlr_surface *surface = surface_at(server, lx, ly, &sx, &sy);
	if (!surface) {
		slot->role = TOUCH_EATEN;
		return;
	}
	slot->role = TOUCH_CLIENT;
	slot->ox = lx - sx;
	slot->oy = ly - sy;
	wlr_seat_touch_notify_down(server->seat, surface, event->time_msec, event->touch_id, sx, sy);
}

static void touch_motion(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, touch_motion);
	struct wlr_touch_motion_event *event = data;
	struct touch_slot *slot = slot_for(server, event->touch_id, false);
	if (!slot) {
		return;
	}
	double lx, ly;
	wlr_cursor_absolute_to_layout_coords(server->cursor, &event->touch->base, event->x, event->y, &lx, &ly);
	uint32_t dt = event->time_msec - slot->t;
	if (dt > 0) {
		/* a little smoothing, the screen reports often */
		slot->vy = slot->vy * 0.4 + 0.6 * (ly - slot->y) / dt;
		slot->vx = slot->vx * 0.4 + 0.6 * (lx - slot->x) / dt;
	}
	slot->x = lx;
	slot->y = ly;
	slot->t = event->time_msec;
	switch (slot->role) {
	case TOUCH_CLIENT:
		wlr_seat_touch_notify_motion(server->seat, event->time_msec, event->touch_id, lx - slot->ox, ly - slot->oy);
		break;
	case TOUCH_HOME: {
		/* the app follows the finger up, less and less, and fades */
		double up = slot->y0 - ly;
		up = up < 0 ? 0 : up;
		server->offset = -(float)(up * 0.85);
		server->alpha = 1 - (float)fmin(0.55, up / (server->full.height * 0.9));
		apply_motion(server);
		break;
	}
	default:
		break;
	}
}

static void touch_up(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, touch_up);
	struct wlr_touch_up_event *event = data;
	struct touch_slot *slot = slot_for(server, event->touch_id, false);
	if (!slot) {
		return;
	}
	switch (slot->role) {
	case TOUCH_CLIENT:
		wlr_seat_touch_notify_up(server->seat, event->time_msec, event->touch_id);
		break;
	case TOUCH_HOME: {
		double up = slot->y0 - slot->y;
		if (up > HOME_DISTANCE || (up > 24 && -slot->vy > FLICK_SPEED)) {
			wlr_log(WLR_INFO, "gesture: home");
			go_home(server);
		} else {
			animate(server, server->offset, 0, 180, settle);
		}
		break;
	}
	case TOUCH_BACK: {
		double across = slot->x - slot->x0;
		if (across > BACK_DISTANCE || (across > 24 && slot->vx > FLICK_SPEED)) {
			wlr_log(WLR_INFO, "gesture: back");
			send_key(server, KEY_ESC);
		}
		break;
	}
	default:
		break;
	}
	slot->role = TOUCH_NONE;
}

static void touch_cancel(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, touch_cancel);
	struct wlr_touch_cancel_event *event = data;
	struct touch_slot *slot = slot_for(server, event->touch_id, false);
	if (!slot) {
		return;
	}
	if (slot->role == TOUCH_CLIENT) {
		wlr_seat_touch_notify_up(server->seat, event->time_msec, event->touch_id);
	} else if (slot->role == TOUCH_HOME) {
		animate(server, server->offset, 0, 180, settle);
	}
	slot->role = TOUCH_NONE;
}

static void touch_frame(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, touch_frame);
	wlr_seat_touch_notify_frame(server->seat);
}

/* ---- inputs --------------------------------------------------------------------------------- */

static void new_input(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, new_input);
	struct wlr_input_device *device = data;
	switch (device->type) {
	case WLR_INPUT_DEVICE_KEYBOARD: {
		struct ztg_keyboard *kb = calloc(1, sizeof(*kb));
		kb->server = server;
		kb->keyboard = wlr_keyboard_from_input_device(device);
		struct xkb_keymap *keymap = default_keymap();
		wlr_keyboard_set_keymap(kb->keyboard, keymap);
		xkb_keymap_unref(keymap);
		kb->key.notify = keyboard_key;
		wl_signal_add(&kb->keyboard->events.key, &kb->key);
		kb->destroy.notify = keyboard_destroy;
		wl_signal_add(&device->events.destroy, &kb->destroy);
		wl_list_insert(&server->keyboards, &kb->link);
		wlr_log(WLR_INFO, "input: keys %s", device->name);
		break;
	}
	case WLR_INPUT_DEVICE_TOUCH:
	case WLR_INPUT_DEVICE_POINTER:
	case WLR_INPUT_DEVICE_TABLET:
		wlr_cursor_attach_input_device(server->cursor, device);
		if (server->output) {
			wlr_cursor_map_input_to_output(server->cursor, device, server->output);
		}
		wlr_log(WLR_INFO, "input: touch/pointer %s", device->name);
		break;
	default:
		break;
	}
	wlr_seat_set_capabilities(server->seat, WL_SEAT_CAPABILITY_TOUCH | WL_SEAT_CAPABILITY_KEYBOARD);
}

/* ---- the screen ---------------------------------------------------------------------------- */

struct ztg_output {
	struct ztg_server *server;
	struct wlr_output *output;
	struct wl_listener frame, request_state, destroy;
};

static void on_frame(struct wl_listener *listener, void *data) {
	struct ztg_output *o = wl_container_of(listener, o, frame);
	struct ztg_server *server = o->server;
	step_animation(server);
	struct wlr_scene_output *so = wlr_scene_get_scene_output(server->scene, o->output);
	wlr_scene_output_commit(so, NULL);
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	wlr_scene_output_send_frame_done(so, &now);
}

static void on_request_state(struct wl_listener *listener, void *data) {
	struct ztg_output *o = wl_container_of(listener, o, request_state);
	const struct wlr_output_event_request_state *event = data;
	wlr_output_commit_state(o->output, event->state);
	arrange(o->server);
}

static void on_output_destroy(struct wl_listener *listener, void *data) {
	struct ztg_output *o = wl_container_of(listener, o, destroy);
	if (o->server->output == o->output) {
		o->server->output = NULL;
	}
	wl_list_remove(&o->frame.link);
	wl_list_remove(&o->request_state.link);
	wl_list_remove(&o->destroy.link);
	free(o);
}

static void new_output(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, new_output);
	struct wlr_output *output = data;
	if (server->output) {
		return;	/* one screen */
	}
	wlr_output_init_render(output, server->allocator, server->renderer);
	struct wlr_output_state state;
	wlr_output_state_init(&state);
	wlr_output_state_set_enabled(&state, true);
	struct wlr_output_mode *mode = wlr_output_preferred_mode(output);
	if (mode) {
		wlr_output_state_set_mode(&state, mode);
	}
	wlr_output_state_set_scale(&state, server->scale);
	if (!wlr_output_commit_state(output, &state)) {
		wlr_log(WLR_ERROR, "output %s: the first commit failed", output->name);
	}
	wlr_output_state_finish(&state);

	struct ztg_output *o = calloc(1, sizeof(*o));
	o->server = server;
	o->output = output;
	o->frame.notify = on_frame;
	wl_signal_add(&output->events.frame, &o->frame);
	o->request_state.notify = on_request_state;
	wl_signal_add(&output->events.request_state, &o->request_state);
	o->destroy.notify = on_output_destroy;
	wl_signal_add(&output->events.destroy, &o->destroy);

	server->output = output;
	struct wlr_output_layout_output *lo = wlr_output_layout_add_auto(server->output_layout, output);
	server->scene_output = wlr_scene_output_create(server->scene, output);
	wlr_scene_output_layout_add_output(server->scene_layout, lo, server->scene_output);
	wlr_log(WLR_INFO, "output %s: %dx%d at scale %.2f", output->name, output->width, output->height,
		output->scale);
	make_home_bar(server);
	arrange(server);
}

/* ---- windows -------------------------------------------------------------------------------- */

static struct ztg_view *view_of_toplevel(struct wlr_xdg_toplevel *toplevel) {
	struct wlr_scene_tree *tree = toplevel->base->data;
	return tree ? tree->node.data : NULL;
}

static void deco_apply(struct ztg_view *view) {
	if (view->decoration && view->toplevel->base->initialized) {
		wlr_xdg_toplevel_decoration_v1_set_mode(view->decoration,
			WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE);
	}
}

static void name_view(struct ztg_view *view) {
	struct ztg_server *server = view->server;
	pid_t pid = 0;
	uid_t uid;
	gid_t gid;
	wl_client_get_credentials(wl_resource_get_client(view->toplevel->resource), &pid, &uid, &gid);
	const char *app_id = view->toplevel->app_id ? view->toplevel->app_id : "";
	uint32_t now = now_ms();
	int best = -1;
	for (int i = 0; i < MAX_PENDING && best < 0; i++) {
		if (!server->pending[i].key[0]) {
			continue;
		}
		/* the process launched, or one of its children */
		for (pid_t p = pid, n = 0; p > 1 && n < 6; p = parent_of(p), n++) {
			if (p == server->pending[i].pid) {
				best = i;
				break;
			}
		}
	}
	for (int i = 0; i < MAX_PENDING && best < 0; i++) {
		const char *key = server->pending[i].key;
		size_t n = strlen(app_id);
		if (key[0] && n && (strcmp(key, app_id) == 0 ||
				(strncmp(key, app_id, n) == 0 && strcmp(key + n, ".desktop") == 0))) {
			best = i;
		}
	}
	for (int i = 0; i < MAX_PENDING && best < 0; i++) {
		/* started by the zygote or a launcher: the latest launch, if lately */
		if (server->pending[i].key[0] && now - server->pending[i].at < 12000) {
			best = i;
		}
	}
	if (best >= 0) {
		snprintf(view->key, sizeof(view->key), "%s", server->pending[best].key);
		server->pending[best].key[0] = 0;
	} else if (app_id[0]) {
		snprintf(view->key, sizeof(view->key), "%s", app_id);
	}
	wlr_log(WLR_INFO, "window: pid %d app_id '%s' is '%s'", pid, app_id, view->key);
}

static void view_map(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, map);
	view->mapped = true;
	name_view(view);
	open_view(view->server, view);
	tell_apps(view->server);
}

static void view_unmap(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, unmap);
	struct ztg_server *server = view->server;
	view->mapped = false;
	if (server->shown == view) {
		server->anim.on = false;
		show(server, NULL);
	}
	tell_apps(server);
}

static void view_commit(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, commit);
	if (view->toplevel->base->initial_commit) {
		configure_view(view);
		deco_apply(view);
	}
}

static void view_request(struct wl_listener *listener, void *data) {
	/* full screen, maximized: it is all of the screen it gets already, say so again */
	struct ztg_view *view = wl_container_of(listener, view, request_maximize);
	if (view->toplevel->base->initialized) {
		wlr_xdg_surface_schedule_configure(view->toplevel->base);
	}
}

static void view_request_fs(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, request_fullscreen);
	if (view->toplevel->base->initialized) {
		wlr_xdg_surface_schedule_configure(view->toplevel->base);
	}
}

static void deco_destroy(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, deco_destroy);
	wl_list_remove(&view->deco_mode.link);
	wl_list_remove(&view->deco_destroy.link);
	view->decoration = NULL;
}

static void view_destroy(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, destroy);
	if (view->decoration) {
		deco_destroy(&view->deco_destroy, NULL);
	}
	if (view->server->shown == view) {
		view->server->shown = NULL;
	}
	wl_list_remove(&view->map.link);
	wl_list_remove(&view->unmap.link);
	wl_list_remove(&view->commit.link);
	wl_list_remove(&view->destroy.link);
	wl_list_remove(&view->request_fullscreen.link);
	wl_list_remove(&view->request_maximize.link);
	wl_list_remove(&view->link);
	free(view);
}

static void new_toplevel(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, new_toplevel);
	struct wlr_xdg_toplevel *toplevel = data;
	struct ztg_view *view = calloc(1, sizeof(*view));
	view->server = server;
	view->toplevel = toplevel;
	view->tree = wlr_scene_xdg_surface_create(server->apps, toplevel->base);
	view->tree->node.data = view;
	toplevel->base->data = view->tree;
	wlr_scene_node_set_enabled(&view->tree->node, false);
	view->map.notify = view_map;
	wl_signal_add(&toplevel->base->surface->events.map, &view->map);
	view->unmap.notify = view_unmap;
	wl_signal_add(&toplevel->base->surface->events.unmap, &view->unmap);
	view->commit.notify = view_commit;
	wl_signal_add(&toplevel->base->surface->events.commit, &view->commit);
	view->destroy.notify = view_destroy;
	wl_signal_add(&toplevel->events.destroy, &view->destroy);
	view->request_fullscreen.notify = view_request_fs;
	wl_signal_add(&toplevel->events.request_fullscreen, &view->request_fullscreen);
	view->request_maximize.notify = view_request;
	wl_signal_add(&toplevel->events.request_maximize, &view->request_maximize);
	wl_list_insert(&server->views, &view->link);
}

static void deco_request_mode(struct wl_listener *listener, void *data) {
	struct ztg_view *view = wl_container_of(listener, view, deco_mode);
	deco_apply(view);
}

static void new_decoration(struct wl_listener *listener, void *data) {
	struct wlr_xdg_toplevel_decoration_v1 *decoration = data;
	struct ztg_view *view = view_of_toplevel(decoration->toplevel);
	if (!view) {
		return;
	}
	view->decoration = decoration;
	view->deco_mode.notify = deco_request_mode;
	wl_signal_add(&decoration->events.request_mode, &view->deco_mode);
	view->deco_destroy.notify = deco_destroy;
	wl_signal_add(&decoration->events.destroy, &view->deco_destroy);
	deco_apply(view);
}

/* ---- popups, of windows and of the shell's surfaces ------------------------------------------- */

static void popup_commit(struct wl_listener *listener, void *data) {
	struct ztg_popup *p = wl_container_of(listener, p, commit);
	if (p->popup->base->initial_commit) {
		wlr_xdg_surface_schedule_configure(p->popup->base);
	}
}

static void popup_destroy(struct wl_listener *listener, void *data) {
	struct ztg_popup *p = wl_container_of(listener, p, destroy);
	wl_list_remove(&p->commit.link);
	wl_list_remove(&p->destroy.link);
	free(p);
}

static void new_popup(struct wl_listener *listener, void *data) {
	struct wlr_xdg_popup *popup = data;
	struct ztg_popup *p = calloc(1, sizeof(*p));
	p->popup = popup;
	p->commit.notify = popup_commit;
	wl_signal_add(&popup->base->surface->events.commit, &p->commit);
	p->destroy.notify = popup_destroy;
	wl_signal_add(&popup->events.destroy, &p->destroy);
	/* a window's popup goes into the window's tree; a layer surface's is
	 * given its parent later, and placed by layer_new_popup */
	struct wlr_xdg_surface *parent = popup->parent ? wlr_xdg_surface_try_from_wlr_surface(popup->parent) : NULL;
	if (parent && parent->data) {
		popup->base->data = wlr_scene_xdg_surface_create(parent->data, popup->base);
	}
}

/* ---- the shell's surfaces --------------------------------------------------------------------- */

static struct wlr_scene_tree *tree_for_layer(struct ztg_server *server, enum zwlr_layer_shell_v1_layer layer) {
	switch (layer) {
	case ZWLR_LAYER_SHELL_V1_LAYER_BACKGROUND:
		return server->layer_bg;
	case ZWLR_LAYER_SHELL_V1_LAYER_BOTTOM:
		return server->layer_bottom;
	case ZWLR_LAYER_SHELL_V1_LAYER_TOP:
		return server->layer_top;
	default:
		return server->layer_overlay;
	}
}

static void layer_focus(struct ztg_server *server) {
	/* a surface that wants the keys (the lock screen's code, say) has them;
	 * else the app shown */
	struct ztg_layer *layer;
	wl_list_for_each(layer, &server->layers, link) {
		struct wlr_layer_surface_v1 *s = layer->surface;
		if (s->surface->mapped && s->current.keyboard_interactive != ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE &&
				s->current.layer >= ZWLR_LAYER_SHELL_V1_LAYER_TOP) {
			focus(server, s->surface);
			return;
		}
	}
	focus(server, server->shown ? server->shown->toplevel->base->surface : NULL);
}

static void layer_map(struct wl_listener *listener, void *data) {
	struct ztg_layer *layer = wl_container_of(listener, layer, map);
	wlr_log(WLR_INFO, "shell surface '%s' shown", layer->surface->namespace);
	arrange(layer->server);
	layer_focus(layer->server);
}

static void layer_unmap(struct wl_listener *listener, void *data) {
	struct ztg_layer *layer = wl_container_of(listener, layer, unmap);
	arrange(layer->server);
	layer_focus(layer->server);
}

static void layer_commit(struct wl_listener *listener, void *data) {
	struct ztg_layer *layer = wl_container_of(listener, layer, commit);
	struct wlr_layer_surface_v1 *s = layer->surface;
	if (s->initial_commit) {
		wlr_log(WLR_INFO, "shell surface '%s': first commit (initialized %d, layer %d, anchor %u, size %ux%u, zone %d)",
			s->namespace, s->initialized, s->current.layer, s->current.anchor, s->current.desired_width,
			s->current.desired_height, s->current.exclusive_zone);
	}
	if (!s->initialized) {
		return;
	}
	struct wlr_scene_tree *want = tree_for_layer(layer->server, s->current.layer);
	if (layer->scene->tree->node.parent != want) {
		wlr_scene_node_reparent(&layer->scene->tree->node, want);
	}
	if (s->initial_commit || s->current.committed) {
		arrange(layer->server);
	}
}

static void layer_destroy(struct wl_listener *listener, void *data) {
	struct ztg_layer *layer = wl_container_of(listener, layer, destroy);
	wl_list_remove(&layer->map.link);
	wl_list_remove(&layer->unmap.link);
	wl_list_remove(&layer->commit.link);
	wl_list_remove(&layer->destroy.link);
	wl_list_remove(&layer->new_popup.link);
	wl_list_remove(&layer->link);
	struct ztg_server *server = layer->server;
	free(layer);
	arrange(server);
}

static void layer_new_popup(struct wl_listener *listener, void *data) {
	struct ztg_layer *layer = wl_container_of(listener, layer, new_popup);
	struct wlr_xdg_popup *popup = data;
	popup->base->data = wlr_scene_xdg_surface_create(layer->scene->tree, popup->base);
}

static void new_layer(struct wl_listener *listener, void *data) {
	struct ztg_server *server = wl_container_of(listener, server, new_layer);
	struct wlr_layer_surface_v1 *s = data;
	if (!s->output) {
		if (!server->output) {
			wlr_layer_surface_v1_destroy(s);
			return;
		}
		s->output = server->output;
	}
	struct ztg_layer *layer = calloc(1, sizeof(*layer));
	layer->server = server;
	layer->surface = s;
	layer->scene = wlr_scene_layer_surface_v1_create(tree_for_layer(server, s->pending.layer), s);
	s->data = layer;
	layer->map.notify = layer_map;
	wl_signal_add(&s->surface->events.map, &layer->map);
	layer->unmap.notify = layer_unmap;
	wl_signal_add(&s->surface->events.unmap, &layer->unmap);
	layer->commit.notify = layer_commit;
	wl_signal_add(&s->surface->events.commit, &layer->commit);
	layer->destroy.notify = layer_destroy;
	wl_signal_add(&s->events.destroy, &layer->destroy);
	layer->new_popup.notify = layer_new_popup;
	wl_signal_add(&s->events.new_popup, &layer->new_popup);
	wl_list_insert(&server->layers, &layer->link);
	wlr_log(WLR_INFO, "shell surface '%s' on layer %d", s->namespace ? s->namespace : "", s->pending.layer);
}

/* ---- the control socket ----------------------------------------------------------------------- */

static void command(struct ztg_server *server, char *line) {
	char *space = strchr(line, ' ');
	char *arg = space ? space + 1 : "";
	if (space) {
		*space = 0;
	}
	if (strcmp(line, "home") == 0) {
		go_home(server);
	} else if (strcmp(line, "launch") == 0) {
		char *cmd = strchr(arg, ' ');
		if (!cmd) {
			return;
		}
		*cmd++ = 0;
		struct ztg_view *view = view_by_key(server, arg);
		if (view) {
			wlr_log(WLR_INFO, "launch %s: its window", arg);
			open_view(server, view);
			return;
		}
		/* launched lately and not up yet: once is enough */
		for (int i = 0; i < MAX_PENDING; i++) {
			if (server->pending[i].key[0] && strcmp(server->pending[i].key, arg) == 0 &&
					now_ms() - server->pending[i].at < 6000) {
				return;
			}
		}
		int slot = 0;
		for (int i = 0; i < MAX_PENDING; i++) {
			if (!server->pending[i].key[0] || server->pending[i].at < server->pending[slot].at) {
				slot = i;
				if (!server->pending[i].key[0]) {
					break;
				}
			}
		}
		server->pending[slot].pid = spawn(cmd);
		server->pending[slot].at = now_ms();
		snprintf(server->pending[slot].key, sizeof(server->pending[slot].key), "%s", arg);
		wlr_log(WLR_INFO, "launch %s: %s (pid %d)", arg, cmd, server->pending[slot].pid);
	} else if (strcmp(line, "close") == 0) {
		struct ztg_view *view = view_by_key(server, arg);
		if (view) {
			wlr_xdg_toplevel_send_close(view->toplevel);
		}
	} else if (strcmp(line, "sleep") == 0) {
		if (!server->blanked) {
			set_blank(server, true);
		}
	} else if (strcmp(line, "wake") == 0) {
		if (server->blanked) {
			set_blank(server, false);
		}
	} else if (strcmp(line, "apps") == 0) {
		tell_apps(server);
	}
}

static int client_readable(int fd, uint32_t mask, void *data) {
	struct ztg_server *server = data;
	int i;
	for (i = 0; i < MAX_CLIENTS && server->clients[i] != fd; i++) {
	}
	if (i == MAX_CLIENTS) {
		return 0;
	}
	char *buf = server->client_buf[i];
	size_t *len = &server->client_len[i];
	ssize_t n = (mask & WL_EVENT_READABLE) ? read(fd, buf + *len, sizeof(server->client_buf[i]) - 1 - *len) : 0;
	if (n <= 0) {
		if (n < 0 && (errno == EAGAIN || errno == EINTR)) {
			return 0;
		}
		wl_event_source_remove(server->client_src[i]);
		close(fd);
		server->clients[i] = -1;
		*len = 0;
		return 0;
	}
	*len += n;
	buf[*len] = 0;
	char *start = buf, *nl;
	while ((nl = strchr(start, '\n'))) {
		*nl = 0;
		if (*start) {
			command(server, start);
		}
		start = nl + 1;
	}
	*len = strlen(start);
	memmove(buf, start, *len + 1);
	if (*len >= sizeof(server->client_buf[i]) - 1) {
		*len = 0;	/* a line longer than that is no command */
	}
	return 0;
}

static int client_accept(int fd, uint32_t mask, void *data) {
	struct ztg_server *server = data;
	int c = accept4(fd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
	if (c < 0) {
		return 0;
	}
	for (int i = 0; i < MAX_CLIENTS; i++) {
		if (server->clients[i] < 0) {
			server->clients[i] = c;
			server->client_len[i] = 0;
			server->client_src[i] = wl_event_loop_add_fd(server->loop, c, WL_EVENT_READABLE, client_readable, server);
			/* where things are, for a shell that has just come */
			if (server->shown) {
				tell(server, "app %s", server->shown->key[0] ? server->shown->key : "-");
			} else {
				tell(server, "home");
			}
			tell_apps(server);
			return 0;
		}
	}
	close(c);
	return 0;
}

static bool open_socket(struct ztg_server *server) {
	const char *runtime = getenv("XDG_RUNTIME_DIR");
	if (!runtime) {
		return false;
	}
	snprintf(server->sock_path, sizeof(server->sock_path), "%s/ztglass.sock", runtime);
	unlink(server->sock_path);
	server->listen_fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", server->sock_path);
	if (server->listen_fd < 0 || bind(server->listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
			listen(server->listen_fd, 4) < 0) {
		wlr_log_errno(WLR_ERROR, "control socket %s", server->sock_path);
		return false;
	}
	chmod(server->sock_path, 0600);
	wl_event_loop_add_fd(server->loop, server->listen_fd, WL_EVENT_READABLE, client_accept, server);
	return true;
}

/* ---- main ------------------------------------------------------------------------------------ */

int main(int argc, char *argv[]) {
	wlr_log_init(getenv("ZTGLASS_DEBUG") ? WLR_DEBUG : WLR_INFO, NULL);
	struct ztg_server server_ = { 0 }, *server = &server_;
	server->scale = getenv("ZTGLASS_SCALE") ? (float)atof(getenv("ZTGLASS_SCALE")) : 4.0f;
	server->scale = server->scale < 1 ? 1 : server->scale;
	server->alpha = 1;
	for (int i = 0; i < MAX_CLIENTS; i++) {
		server->clients[i] = -1;
	}
	int c;
	while ((c = getopt(argc, argv, "s:h")) != -1) {
		if (c == 's') {
			server->shell_cmd = optarg;
		} else {
			printf("usage: %s [-s shell command]\n", argv[0]);
			return 0;
		}
	}
	signal(SIGPIPE, SIG_IGN);

	server->display = wl_display_create();
	server->loop = wl_display_get_event_loop(server->display);
	server->backend = wlr_backend_autocreate(server->loop, &server->session);
	if (!server->backend) {
		wlr_log(WLR_ERROR, "no backend");
		return 1;
	}
	server->renderer = wlr_renderer_autocreate(server->backend);
	if (!server->renderer) {
		wlr_log(WLR_ERROR, "no renderer");
		return 1;
	}
	wlr_renderer_init_wl_display(server->renderer, server->display);
	server->allocator = wlr_allocator_autocreate(server->backend, server->renderer);
	if (!server->allocator) {
		wlr_log(WLR_ERROR, "no allocator");
		return 1;
	}

	wlr_compositor_create(server->display, 6, server->renderer);
	wlr_subcompositor_create(server->display);
	wlr_data_device_manager_create(server->display);
	wlr_viewporter_create(server->display);
	wlr_presentation_create(server->display, server->backend, 2);
	wlr_single_pixel_buffer_manager_v1_create(server->display);
	wlr_fractional_scale_manager_v1_create(server->display, 1);
	wlr_screencopy_manager_v1_create(server->display);

	server->output_layout = wlr_output_layout_create(server->display);
	wlr_xdg_output_manager_v1_create(server->display, server->output_layout);
	server->scene = wlr_scene_create();
	server->scene_layout = wlr_scene_attach_output_layout(server->scene, server->output_layout);
	if (wlr_renderer_get_texture_formats(server->renderer, WLR_BUFFER_CAP_DMABUF)) {
		struct wlr_linux_dmabuf_v1 *dmabuf = wlr_linux_dmabuf_v1_create_with_renderer(server->display, 4,
			server->renderer);
		if (dmabuf) {
			wlr_scene_set_linux_dmabuf_v1(server->scene, dmabuf);
		}
	}

	struct wlr_scene_tree *root = &server->scene->tree;
	float black[4] = { 0, 0, 0, 1 };
	struct wlr_scene_rect *under = wlr_scene_rect_create(root, 1, 1, black);
	(void)under;
	server->layer_bg = wlr_scene_tree_create(root);
	server->layer_bottom = wlr_scene_tree_create(root);
	server->apps = wlr_scene_tree_create(root);
	server->app_black = wlr_scene_rect_create(server->apps, 1, 1, black);
	wlr_scene_node_set_enabled(&server->app_black->node, false);
	server->layer_top = wlr_scene_tree_create(root);
	server->chrome = wlr_scene_tree_create(root);
	server->layer_overlay = wlr_scene_tree_create(root);
	server->blank = wlr_scene_rect_create(root, 1, 1, black);
	wlr_scene_node_set_enabled(&server->blank->node, false);
	wlr_scene_rect_set_size(under, 8192, 8192);

	wl_list_init(&server->views);
	wl_list_init(&server->layers);
	wl_list_init(&server->keyboards);
	server->new_output.notify = new_output;
	wl_signal_add(&server->backend->events.new_output, &server->new_output);

	server->xdg_shell = wlr_xdg_shell_create(server->display, 5);
	server->new_toplevel.notify = new_toplevel;
	wl_signal_add(&server->xdg_shell->events.new_toplevel, &server->new_toplevel);
	server->new_popup.notify = new_popup;
	wl_signal_add(&server->xdg_shell->events.new_popup, &server->new_popup);
	server->layer_shell = wlr_layer_shell_v1_create(server->display, 4);
	server->new_layer.notify = new_layer;
	wl_signal_add(&server->layer_shell->events.new_surface, &server->new_layer);
	server->decorations = wlr_xdg_decoration_manager_v1_create(server->display);
	server->new_decoration.notify = new_decoration;
	wl_signal_add(&server->decorations->events.new_toplevel_decoration, &server->new_decoration);

	server->cursor = wlr_cursor_create();
	wlr_cursor_attach_output_layout(server->cursor, server->output_layout);
	server->touch_down.notify = touch_down;
	wl_signal_add(&server->cursor->events.touch_down, &server->touch_down);
	server->touch_up.notify = touch_up;
	wl_signal_add(&server->cursor->events.touch_up, &server->touch_up);
	server->touch_motion.notify = touch_motion;
	wl_signal_add(&server->cursor->events.touch_motion, &server->touch_motion);
	server->touch_cancel.notify = touch_cancel;
	wl_signal_add(&server->cursor->events.touch_cancel, &server->touch_cancel);
	server->touch_frame.notify = touch_frame;
	wl_signal_add(&server->cursor->events.touch_frame, &server->touch_frame);

	server->seat = wlr_seat_create(server->display, "seat0");
	wlr_keyboard_init(&server->vkbd, &vkbd_impl, "ztglass-keys");
	struct xkb_keymap *keymap = default_keymap();
	wlr_keyboard_set_keymap(&server->vkbd, keymap);
	xkb_keymap_unref(keymap);
	wlr_seat_set_keyboard(server->seat, &server->vkbd);
	wlr_seat_set_capabilities(server->seat, WL_SEAT_CAPABILITY_TOUCH | WL_SEAT_CAPABILITY_KEYBOARD);
	server->new_input.notify = new_input;
	wl_signal_add(&server->backend->events.new_input, &server->new_input);

	const char *socket_name = wl_display_add_socket_auto(server->display);
	if (!socket_name) {
		wlr_log(WLR_ERROR, "no wayland socket");
		return 1;
	}
	if (!open_socket(server)) {
		wlr_log(WLR_ERROR, "the shell will not reach us: no control socket");
	}
	/* children are reaped on the loop (a signalfd: SIGCHLD stays blocked here) */
	sigset_t chld;
	sigemptyset(&chld);
	sigaddset(&chld, SIGCHLD);
	sigprocmask(SIG_BLOCK, &chld, NULL);
	wl_event_loop_add_signal(server->loop, SIGCHLD, on_sigchld, server);
	server->shell_timer = wl_event_loop_add_timer(server->loop, start_shell, server);

	if (!wlr_backend_start(server->backend)) {
		wlr_log(WLR_ERROR, "the backend did not start");
		return 1;
	}
	setenv("WAYLAND_DISPLAY", socket_name, true);
	setenv("XDG_CURRENT_DESKTOP", "ztGlass", true);
	setenv("XDG_SESSION_TYPE", "wayland", true);
	wlr_log(WLR_INFO, "ztGlass on WAYLAND_DISPLAY=%s", socket_name);
	start_shell(server);

	wl_display_run(server->display);

	wl_display_destroy_clients(server->display);
	unlink(server->sock_path);
	wlr_scene_node_destroy(&server->scene->tree.node);
	wlr_cursor_destroy(server->cursor);
	wlr_keyboard_finish(&server->vkbd);
	wl_display_destroy(server->display);
	return 0;
}

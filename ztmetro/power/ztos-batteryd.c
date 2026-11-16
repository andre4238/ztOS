/*
 * ztos-batteryd: the battery's keeper.
 *
 * The kernel charges by itself once a cable brings power (max77705 charger,
 * its input limited by AICL). What it does not do, this does:
 *
 *  - never run the cell flat: on battery at 5 % a warning; at 2 %, or the
 *    cell under 3.30 V for two readings in a row, the phone shuts down cleanly
 *    (a Li-ion cell taken down to cut-off ages, and an OS that dies mid-write
 *    may not boot again). Before that, at 15 % on battery, power saver.
 *  - not charge a hot cell hard: at 45 °C the charge current drops to 1 A, at
 *    50 °C charging pauses (the input held at its 100 mA minimum), and below
 *    42 °C it goes back to what it was.
 *  - battery care, if asked (battery_care = on in the shell's config): charge
 *    to 85 % and hold there, the cable carrying the phone, until 80 %.
 *
 * Pausing is done with the input limit, since the charger driver has no
 * switch for charging itself: at 100 mA the cable carries some of the phone
 * and the cell gives the rest, so held at 85 % it drifts down to 80 % slowly
 * and charges again.
 *
 * It sleeps on the kernel's power_supply uevents and reads the gauge every
 * 20 s (60 s with nothing to watch). What it does goes to the journal and to
 * /run/ztos-battery.status (key=value), which Settings shows.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/netlink.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define PS		"/sys/class/power_supply"
#define STATUS_FILE	"/run/ztos-battery.status"
#define PERFD_CTL	"/run/zrnperfd.ctl"

#define WARN_PCT	5
#define CRIT_PCT	2
#define CRIT_UV		3300000
#define SAVER_PCT	15
#define HOT_DC		450	/* tenths of a degree */
#define TOO_HOT_DC	500
#define COOL_DC		420
#define HOT_CC_UA	1000000
#define HOLD_UA		100000	/* the charger's lowest input limit */
#define IS_HOLD(ua)	((ua) <= 200000)	/* (it reads back as 125 mA) */
#define CARE_TOP_DEFAULT	85
#define CARE_RESUME_DEFAULT	80
static long care_top = CARE_TOP_DEFAULT, care_resume = CARE_RESUME_DEFAULT;

static char battery[PATH_MAX], charger[PATH_MAX];
static volatile sig_atomic_t stop;

static long rd(const char *dir, const char *name, long fallback) {
	char path[PATH_MAX + 64], buf[64];
	snprintf(path, sizeof(path), "%s/%s", dir, name);
	FILE *f = fopen(path, "r");
	if (!f) return fallback;
	long v = fallback;
	if (fgets(buf, sizeof(buf), f)) v = strtol(buf, NULL, 10);
	fclose(f);
	return v;
}

static bool wr(const char *dir, const char *name, long value) {
	char path[PATH_MAX + 64];
	snprintf(path, sizeof(path), "%s/%s", dir, name);
	FILE *f = fopen(path, "w");
	if (!f) return false;
	bool ok = fprintf(f, "%ld\n", value) > 0;
	ok = fclose(f) == 0 && ok;
	if (!ok) fprintf(stderr, "batteryd: %s = %ld failed: %s\n", path, value, strerror(errno));
	return ok;
}

/* the battery (type Battery) and the supply with an online flag */
static void find_supplies(void) {
	DIR *d = opendir(PS);
	struct dirent *e;
	battery[0] = charger[0] = 0;
	while (d && (e = readdir(d))) {
		if (e->d_name[0] == '.') continue;
		char path[PATH_MAX], type[32] = "";
		snprintf(path, sizeof(path), PS "/%s/type", e->d_name);
		FILE *f = fopen(path, "r");
		if (f) {
			if (!fgets(type, sizeof(type), f)) type[0] = 0;
			fclose(f);
		}
		snprintf(path, sizeof(path), PS "/%s", e->d_name);
		if (!strncmp(type, "Battery", 7)) {
			if (!battery[0]) snprintf(battery, sizeof(battery), "%s", path);
		} else if (!charger[0] && rd(path, "online", -1) >= 0) {
			snprintf(charger, sizeof(charger), "%s", path);
		}
	}
	if (d) closedir(d);
}

/* the shell's control pipe, for a notification (nothing if it is not there) */
static void shell_say(const char *line) {
	DIR *d = opendir("/run/user");
	struct dirent *e;
	while (d && (e = readdir(d))) {
		if (e->d_name[0] == '.') continue;
		char path[300];
		snprintf(path, sizeof(path), "/run/user/%s/ztmetro.ctl", e->d_name);
		int fd = open(path, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
		if (fd >= 0) {
			if (write(fd, line, strlen(line)) < 0) {}
			close(fd);
		}
	}
	if (d) closedir(d);
}

static void notify(const char *title, const char *text) {
	char line[512];
	snprintf(line, sizeof(line), "notify Battery|%s|%s\n", title, text);
	shell_say(line);
	fprintf(stderr, "batteryd: %s: %s\n", title, text);
}

static void perfd(const char *command) {
	int fd = open(PERFD_CTL, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) return;
	if (write(fd, command, strlen(command)) < 0) {}
	close(fd);
}

/* battery_care = on in the first user's shell config (Settings writes it) */
static bool care_wanted(void) {
	struct passwd *pw = getpwuid(1000);
	if (!pw) return false;
	char path[PATH_MAX], line[256];
	snprintf(path, sizeof(path), "%s/.config/ztmetro/config", pw->pw_dir);
	FILE *f = fopen(path, "r");
	bool on = false;
	while (f && fgets(line, sizeof(line), f)) {
		char key[64], value[64];
		if (sscanf(line, " %63[^= ] = %63s", key, value) == 2 && !strcmp(key, "battery_care")) {
			on = !strcmp(value, "on");
		}
	}
	if (f) fclose(f);
	return on;
}

static int uevent_socket(void) {
	int fd = socket(AF_NETLINK, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, NETLINK_KOBJECT_UEVENT);
	if (fd < 0) return -1;
	struct sockaddr_nl addr = { .nl_family = AF_NETLINK, .nl_pid = 0, .nl_groups = 1 };
	if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		close(fd);
		return -1;
	}
	return fd;
}

/* true if a power_supply event came in */
static bool drain_uevents(int fd) {
	char buf[4096];
	bool power = false;
	ssize_t n;
	while ((n = recv(fd, buf, sizeof(buf) - 1, 0)) > 0) {
		buf[n] = 0;
		for (char *p = buf; p < buf + n; p += strlen(p) + 1) {
			if (!strcmp(p, "SUBSYSTEM=power_supply")) power = true;
		}
	}
	return power;
}

static void on_signal(int sig) {
	(void)sig;
	stop = 1;
}

int main(void) {
	signal(SIGTERM, on_signal);
	signal(SIGINT, on_signal);
	/* for tests: other thresholds for battery care (BATTERYD_CARE=top,resume) */
	if (getenv("BATTERYD_CARE")) sscanf(getenv("BATTERYD_CARE"), "%ld,%ld", &care_top, &care_resume);
	find_supplies();
	if (!battery[0]) {
		fprintf(stderr, "batteryd: no battery found under " PS "\n");
		return 1;
	}
	fprintf(stderr, "batteryd: battery %s, charger %s\n", battery, charger[0] ? charger : "(none)");

	long cc_normal = charger[0] ? rd(charger, "constant_charge_current", 0) : 0;
	long input_normal = charger[0] ? rd(charger, "input_current_limit", 0) : 0;
	if (IS_HOLD(input_normal)) input_normal = 1800000;	/* a hold left by a run before this one */
	if (cc_normal <= HOT_CC_UA) cc_normal = 2100000;
	if (charger[0]) {
		wr(charger, "input_current_limit", input_normal);
		wr(charger, "constant_charge_current", cc_normal);
	}

	int ue = uevent_socket();
	bool was_online = charger[0] && rd(charger, "online", 0) == 1;
	bool warned = false, saver = false, care_hold = false, hot = false, too_hot = false;
	int low_readings = 0;
	char state[32] = "";

	while (!stop) {
		long cap = rd(battery, "capacity", -1);
		long uv = rd(battery, "voltage_now", -1);
		long temp = rd(battery, "temp", 250);
		bool online = charger[0] && rd(charger, "online", 0) == 1;
		bool care = care_wanted();

		if (online && !was_online) {
			/* a cable in: what the charger came up with is its normal */
			long in = rd(charger, "input_current_limit", input_normal);
			if (!IS_HOLD(in) && !care_hold && !too_hot) input_normal = in;
			warned = false;
			low_readings = 0;
			if (saver) {
				perfd("profile balanced\n");
				saver = false;
			}
		}
		was_online = online;

		if (!online) {
			/* ---- on battery: never down to cut-off ---- */
			care_hold = hot = too_hot = false;
			bool low = (cap >= 0 && cap <= CRIT_PCT) || (uv > 0 && uv < CRIT_UV);
			low_readings = low ? low_readings + 1 : 0;
			if (low_readings >= 2) {
				notify("Battery empty", "Switching off to protect the battery.");
				sleep(10);
				if (rd(charger[0] ? charger : battery, "online", 0) != 1) {
					fprintf(stderr, "batteryd: %ld %%, %ld uV: powering off\n", cap, uv);
					sync();
					if (system("systemctl poweroff") != 0) {}
					return 0;
				}
				continue;
			}
			if (cap >= 0 && cap <= WARN_PCT && !warned) {
				notify("Battery very low", "The phone switches off at 2 %. Connect a charger.");
				warned = true;
			}
			if (cap >= 0 && cap <= SAVER_PCT && !saver) {
				perfd("profile powersave\n");
				notify("Battery saver on", "Below 15 %: the processor runs slower to last longer.");
				saver = true;
			}
		} else {
			/* ---- charging: not hot, and to 85 % if asked ---- */
			if (temp >= TOO_HOT_DC && !too_hot) {
				too_hot = true;
				notify("Battery hot", "Charging paused until the battery cools down.");
			} else if (temp >= HOT_DC && !hot) {
				hot = true;
				wr(charger, "constant_charge_current", HOT_CC_UA);
				fprintf(stderr, "batteryd: %.1f C: charge current %d mA\n", temp / 10.0, HOT_CC_UA / 1000);
			} else if (temp <= COOL_DC && (hot || too_hot)) {
				hot = too_hot = false;
				wr(charger, "constant_charge_current", cc_normal);
				fprintf(stderr, "batteryd: %.1f C: charging normally again\n", temp / 10.0);
			}
			if (care && cap >= care_top) {
				care_hold = true;
			} else if (!care || (cap >= 0 && cap <= care_resume)) {
				care_hold = false;
			}
			long in = rd(charger, "input_current_limit", 0);
			if ((care_hold || too_hot) && !IS_HOLD(in)) {
				wr(charger, "input_current_limit", HOLD_UA);
			} else if (!care_hold && !too_hot && IS_HOLD(in)) {
				/* only our own hold is lifted: AICL's lower limits stay */
				wr(charger, "input_current_limit", input_normal);
			}
		}

		const char *now = !online ? (low_readings ? "critical" : saver ? "saver" : "discharging") :
			too_hot ? "paused-hot" : care_hold ? "care-hold" : hot ? "charging-cool" :
			cap >= 100 ? "full" : "charging";
		if (strcmp(now, state)) {
			fprintf(stderr, "batteryd: %s (%ld %%, %.2f V, %.1f C)\n", now, cap, uv / 1e6, temp / 10.0);
			snprintf(state, sizeof(state), "%s", now);
		}
		FILE *f = fopen(STATUS_FILE ".new", "w");
		if (f) {
			fprintf(f, "state=%s\ncapacity=%ld\nvoltage_uv=%ld\ntemp_dc=%ld\nonline=%d\ncare=%s\n"
				"charge_full_uah=%ld\ncharge_full_design_uah=%ld\ncycles=%ld\n",
				now, cap, uv, temp, online, care ? "on" : "off",
				rd(battery, "charge_full", -1), rd(battery, "charge_full_design", -1),
				rd(battery, "cycle_count", -1));
			fclose(f);
			rename(STATUS_FILE ".new", STATUS_FILE);
		}

		/* sleep until a power event, or 20 s (60 s on battery with nothing near) */
		int wait_ms = online || low_readings || (cap >= 0 && cap <= SAVER_PCT + 2) ? 20000 : 60000;
		if (low_readings) wait_ms = 5000;
		struct pollfd p = { .fd = ue, .events = POLLIN };
		if (ue >= 0) {
			if (poll(&p, 1, wait_ms) > 0) {
				drain_uevents(ue);
				usleep(300000);	/* let the charger settle after a plug event */
			}
		} else {
			sleep(wait_ms / 1000);
		}
	}
	/* going away: no hold left behind */
	if (charger[0]) {
		wr(charger, "input_current_limit", input_normal);
		wr(charger, "constant_charge_current", cc_normal);
	}
	return 0;
}

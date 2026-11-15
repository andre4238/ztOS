# ztGlass's compositor; built on the phone (aarch64 Arch Linux ARM, wlroots 0.20)
PKGS = wlroots-0.20 wayland-server xkbcommon cairo libdrm
WP := $(shell pkg-config --variable=pkgdatadir wayland-protocols)
CFLAGS ?= -O2 -g
WARN = -std=c11 -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers
PREFIX ?= /usr/local

all: ztglass

xdg-shell-protocol.h:
	wayland-scanner server-header $(WP)/stable/xdg-shell/xdg-shell.xml $@

wlr-layer-shell-unstable-v1-protocol.h: protocols/wlr-layer-shell-unstable-v1.xml
	wayland-scanner server-header $< $@

ztglass: ztglass.c xdg-shell-protocol.h wlr-layer-shell-unstable-v1-protocol.h
	$(CC) $(CFLAGS) $(WARN) -DWLR_USE_UNSTABLE -I. $(shell pkg-config --cflags $(PKGS)) \
		-o $@ ztglass.c $(shell pkg-config --libs $(PKGS)) -lm

install: ztglass
	install -Dm755 ztglass $(DESTDIR)$(PREFIX)/bin/ztglass

clean:
	rm -f ztglass *-protocol.h

.PHONY: all install clean

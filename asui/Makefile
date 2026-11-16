# ASUI, the A-SYSTEMS UI: the compositor (C, built on the phone), the shell
# (Rust, built with cargo in the ARM64 build VM: shell/), the session.
#   make && sudo make install          (on the phone; the shell binary copied in first)
PREFIX ?= /usr/local
SHELL_BIN ?= shell/target/release/asui-shell

all:
	$(MAKE) -C compositor

install: all
	$(MAKE) -C compositor install PREFIX=$(PREFIX)
	install -Dm755 session/asui-session $(DESTDIR)$(PREFIX)/bin/asui-session
	install -Dm755 session/ztos-session $(DESTDIR)$(PREFIX)/bin/ztos-session
	if [ -f $(SHELL_BIN) ]; then install -Dm755 $(SHELL_BIN) $(DESTDIR)$(PREFIX)/bin/asui-shell; fi

clean:
	$(MAKE) -C compositor clean

.PHONY: all install clean

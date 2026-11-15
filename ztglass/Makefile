# ztOS Glass: the compositor, the shell, the session. On the phone:
#   make && sudo make install
PREFIX ?= /usr/local

all:
	$(MAKE) -C compositor

install: all
	$(MAKE) -C compositor install PREFIX=$(PREFIX)
	install -d $(DESTDIR)$(PREFIX)/lib/ztglass/shell/qml
	install -m644 shell/*.py $(DESTDIR)$(PREFIX)/lib/ztglass/shell/
	install -m644 shell/qml/*.qml $(DESTDIR)$(PREFIX)/lib/ztglass/shell/qml/
	install -Dm755 session/ztglass-session $(DESTDIR)$(PREFIX)/bin/ztglass-session
	install -Dm755 session/ztglass-shell $(DESTDIR)$(PREFIX)/bin/ztglass-shell

clean:
	$(MAKE) -C compositor clean

.PHONY: all install clean

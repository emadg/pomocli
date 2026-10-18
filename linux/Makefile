PREFIX ?= $(HOME)/.local
DESTDIR ?=
CARGO ?= cargo
CMAKE ?= cmake
JOBS ?= 1
DIALOGS ?= 1
BUILD_DIR ?= $(CURDIR)/build/kde
CARGO_TARGET_DIR ?= $(CURDIR)/native/target
XDG_CONFIG_HOME ?= $(HOME)/.config

ifeq ($(DIALOGS),1)
CARGO_FEATURES = --features dialogs
endif

.PHONY: help all native native-minimal widget test-widget install install-native install-widget \
        uninstall uninstall-native uninstall-widget autostart-enable autostart-disable deb deb-widget clean

help:
	@printf '%s\n' \
	  'make native          Build the tray companion and on-demand GTK4 dialogs (default)' \
	  'make native-minimal  Build the tray companion without dialogs' \
	  'make widget          Build the optional Plasma 6 panel widget' \
	  'make test-widget     Run isolated D-Bus bridge and responsive UI tests' \
	  'make install         Install the native companion under PREFIX (~/.local by default)' \
	  'make install-widget  Build and install the optional Plasma widget' \
	  'make uninstall       Remove installed native companion and widget files' \
	  'make autostart-enable / autostart-disable  Opt into or out of login autostart' \
	  'make deb / deb-widget  Build separate Debian packages in build/packages' \
	  'Variables: PREFIX, DESTDIR, JOBS (default 1), DIALOGS (default 1), CARGO_TARGET_DIR'

all: native

native:
	$(CARGO) build --manifest-path native/Cargo.toml --target-dir "$(CARGO_TARGET_DIR)" --release --locked -j $(JOBS) $(CARGO_FEATURES)

native-minimal:
	$(MAKE) native DIALOGS=0

widget:
	$(CMAKE) -S . -B "$(BUILD_DIR)" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$(PREFIX)" -DPOMO_BUILD_TESTS=OFF
	$(CMAKE) --build "$(BUILD_DIR)" -j $(JOBS)

test-widget:
	$(CMAKE) -S . -B "$(BUILD_DIR)" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$(PREFIX)" -DPOMO_BUILD_TESTS=ON
	$(CMAKE) --build "$(BUILD_DIR)" -j $(JOBS)
	ctest --test-dir "$(BUILD_DIR)" --output-on-failure

install: install-native

install-native: native
	install -Dm755 "$(CARGO_TARGET_DIR)/release/pomo-tray" "$(DESTDIR)$(PREFIX)/bin/pomo-tray"
ifeq ($(DIALOGS),1)
	install -Dm755 "$(CARGO_TARGET_DIR)/release/pomo-dialog" "$(DESTDIR)$(PREFIX)/bin/pomo-dialog"
endif
	python3 packaging/install-launcher.py --executable "$(PREFIX)/bin/pomo-tray" --output "$(DESTDIR)$(PREFIX)/share/applications/org.pomocli.Desktop.desktop"
	install -Dm644 ../assets/pomocli-status-icon.svg "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/pomocli.svg"
	@if test -z "$(DESTDIR)" && command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$(PREFIX)/share/applications"; fi
	@if test -z "$(DESTDIR)" && command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t -f "$(PREFIX)/share/icons/hicolor"; fi

install-widget: widget
	# The install target also runs any required pre-install relink steps.
	DESTDIR="$(DESTDIR)" $(CMAKE) --build "$(BUILD_DIR)" --target install -j $(JOBS)
	@# Refresh the live KDE icon cache; staged/package installs have no session.
	@if test -z "$(DESTDIR)" && test -n "$$DBUS_SESSION_BUS_ADDRESS" && command -v dbus-send >/dev/null 2>&1; then dbus-send --session --type=signal /KIconLoader org.kde.KIconLoader.iconChanged int32:0 || true; fi

uninstall: uninstall-native uninstall-widget

uninstall-native:
	rm -f "$(DESTDIR)$(PREFIX)/bin/pomo-tray" "$(DESTDIR)$(PREFIX)/bin/pomo-dialog"
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/org.pomocli.Desktop.desktop"
	rm -f "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/pomocli.svg"
	@if test -z "$(DESTDIR)" && command -v update-desktop-database >/dev/null 2>&1 && test -d "$(PREFIX)/share/applications"; then update-desktop-database "$(PREFIX)/share/applications"; fi

uninstall-widget:
	rm -rf "$(DESTDIR)$(PREFIX)/share/plasma/plasmoids/org.pomocli.timer"
	rm -f "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/org.pomocli.timer.svg"

autostart-enable:
	python3 packaging/autostart.py enable --executable "$(PREFIX)/bin/pomo-tray"

autostart-disable:
	python3 packaging/autostart.py disable

deb:
	JOBS="$(JOBS)" DIALOGS="$(DIALOGS)" CARGO_TARGET_DIR="$(CARGO_TARGET_DIR)" bash packaging/build-deb.sh native

deb-widget:
	JOBS="$(JOBS)" bash packaging/build-deb.sh kde

clean:
	rm -rf -- "$(CURDIR)/build"
	$(CARGO) clean --manifest-path native/Cargo.toml --target-dir "$(CARGO_TARGET_DIR)"

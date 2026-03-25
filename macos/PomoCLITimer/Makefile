BINARY_NAME = PomoCLITimer
APP_NAME = PomoCLI Timer
BUILD_DIR = .build/release
APP_BUNDLE = $(APP_NAME).app
INSTALL_DIR = $(HOME)/Applications
REPO_ROOT = ../..
MAC_APP_PNG = $(REPO_ROOT)/assets/pomocli-mac-app.png
STATUS_PNG = $(REPO_ROOT)/assets/pomocli-status-icon.png
VERSION = $(shell grep '^version' $(REPO_ROOT)/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
BUILD_STAMP = $(VERSION).dev$(shell date -u +%Y.%m.%d.%H%M)
VERSION_FILE = Sources/PomoCLITimer/BuildInfo.swift

.PHONY: build bundle install clean

build:
	@echo 'let appVersion = "$(VERSION)"' > $(VERSION_FILE)
	@echo 'let appBuild = "$(BUILD_STAMP)"' >> $(VERSION_FILE)
	swift build -c release

bundle: build
	rm -rf "$(APP_BUNDLE)"
	mkdir -p "$(APP_BUNDLE)/Contents/MacOS"
	mkdir -p "$(APP_BUNDLE)/Contents/Resources"
	cp "$(BUILD_DIR)/$(BINARY_NAME)" "$(APP_BUNDLE)/Contents/MacOS/"
	cp Resources/Info.plist "$(APP_BUNDLE)/Contents/"
	@if [ -f "$(MAC_APP_PNG)" ]; then \
		ICONSET=$$(mktemp -d)/AppIcon.iconset; \
		mkdir "$$ICONSET"; \
		SRC="$(MAC_APP_PNG)"; \
		sips -z 16 16 "$$SRC" --out "$$ICONSET/icon_16x16.png" >/dev/null; \
		sips -z 32 32 "$$SRC" --out "$$ICONSET/icon_16x16@2x.png" >/dev/null; \
		sips -z 32 32 "$$SRC" --out "$$ICONSET/icon_32x32.png" >/dev/null; \
		sips -z 64 64 "$$SRC" --out "$$ICONSET/icon_32x32@2x.png" >/dev/null; \
		sips -z 128 128 "$$SRC" --out "$$ICONSET/icon_128x128.png" >/dev/null; \
		sips -z 256 256 "$$SRC" --out "$$ICONSET/icon_128x128@2x.png" >/dev/null; \
		sips -z 256 256 "$$SRC" --out "$$ICONSET/icon_256x256.png" >/dev/null; \
		sips -z 512 512 "$$SRC" --out "$$ICONSET/icon_256x256@2x.png" >/dev/null; \
		sips -z 512 512 "$$SRC" --out "$$ICONSET/icon_512x512.png" >/dev/null; \
		sips -z 1024 1024 "$$SRC" --out "$$ICONSET/icon_512x512@2x.png" >/dev/null; \
		iconutil -c icns "$$ICONSET" -o "$(APP_BUNDLE)/Contents/Resources/pomocli-mac-app.icns"; \
	else \
		echo "warning: $(MAC_APP_PNG) missing; app bundle will have no custom icon"; \
	fi
	@if [ -f "$(STATUS_PNG)" ]; then \
		cp "$(STATUS_PNG)" "$(APP_BUNDLE)/Contents/Resources/"; \
	else \
		echo "warning: $(STATUS_PNG) missing; status bar will fall back to emoji"; \
	fi

install: bundle
	mkdir -p "$(INSTALL_DIR)"
	rm -rf "$(INSTALL_DIR)/$(APP_BUNDLE)"
	cp -R "$(APP_BUNDLE)" "$(INSTALL_DIR)/"
	@echo "Installed to $(INSTALL_DIR)/$(APP_BUNDLE)"

clean:
	swift package clean
	rm -rf "$(APP_BUNDLE)"
	rm -f $(VERSION_FILE)

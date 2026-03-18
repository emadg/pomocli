BINARY_NAME = PomoCLITimer
APP_NAME = PomoCLI Timer
BUILD_DIR = .build/release
APP_BUNDLE = $(APP_NAME).app
INSTALL_DIR = $(HOME)/Applications
REPO_ROOT = ../..
VERSION = 0.1.0
BUILD_STAMP = $(VERSION).dev$(shell date -u +%Y%m%d%H%M%S)
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
	@if [ -f "$(REPO_ROOT)/assets/tomato.icns" ]; then \
		cp "$(REPO_ROOT)/assets/tomato.icns" "$(APP_BUNDLE)/Contents/Resources/"; \
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

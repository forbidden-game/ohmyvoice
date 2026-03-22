.PHONY: build build-swift build-python test test-swift test-python clean run dist app \
	print-signing-identities notary-store-credentials check-signing check-notary-profile \
	check-create-dmg sign notarize dmg-local dmg

VENV_BIN ?= $(CURDIR)/.venv/bin
PYTHON ?= $(VENV_BIN)/python
PIP ?= $(VENV_BIN)/pip
PYINSTALLER ?= $(VENV_BIN)/pyinstaller
CREATE_DMG ?= create-dmg
CREATE_DMG_FLAGS ?= --skip-jenkins
NOTARY_PROFILE ?= ohmyvoice-notary
DEVELOPER_ID_APPLICATION ?= $(shell security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"\(Developer ID Application:.*\)"/\1/p' | head -1)

VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ohmyvoice/__init__.py)
APP_NAME := OhMyVoice
APP_DIR := dist/$(APP_NAME).app
DMG_PATH := dist/$(APP_NAME)-$(VERSION)-arm64.dmg

build: build-swift

build-swift:
	cd ui && swift build -c release

build-python:
	$(PIP) install -e ".[dev,dist]"

test: test-swift test-python

test-swift:
	cd ui && swift test

test-python:
	$(PYTHON) -m pytest tests/test_ui_bridge.py tests/test_settings_reload.py -v

clean:
	cd ui && swift package clean
	rm -rf ui/.build

run: build-swift
	PATH="$(VENV_BIN):$$PATH" $(PYTHON) -m ohmyvoice

dist: build-swift
	PATH="$(VENV_BIN):$$PATH" $(PYINSTALLER) ohmyvoice.spec --noconfirm
	mkdir -p $(APP_DIR)/Contents/Resources
	cp -R resources/icons $(APP_DIR)/Contents/Resources/icons
	cp -R resources/sounds $(APP_DIR)/Contents/Resources/sounds 2>/dev/null || true
	cp resources/AppIcon.icns $(APP_DIR)/Contents/Resources/AppIcon.icns 2>/dev/null || true
	cp ui/.build/release/ohmyvoice-ui $(APP_DIR)/Contents/MacOS/
	@# mlx Metal shaders are not picked up by PyInstaller — copy manually
	@MLX_METALLIB=$$(PATH="$(VENV_BIN):$$PATH" $(PYTHON) -c 'from pathlib import Path; import mlx; print(next((str(p) for base in getattr(mlx, "__path__", []) for p in [Path(base) / "lib" / "mlx.metallib"] if p.exists()), ""))'); \
	if [ -n "$$MLX_METALLIB" ]; then \
		mkdir -p $(APP_DIR)/Contents/Frameworks/mlx/lib; \
		cp "$$MLX_METALLIB" $(APP_DIR)/Contents/Frameworks/mlx/lib/; \
	fi
	rm -rf $(APP_DIR)/Contents/_CodeSignature
	@for state in idle recording processing done; do \
		if [ ! -f "$(APP_DIR)/Contents/Resources/icons/mic_$${state}@2x.png" ]; then \
			echo "WARNING: missing mic_$${state}@2x.png — Retina displays will show blurry icons"; \
		fi; \
	done

app: dist

print-signing-identities:
	security find-identity -v -p codesigning

notary-store-credentials:
	@test -n "$(APPLE_ID)" || { echo "Set APPLE_ID=your-apple-id@example.com"; exit 1; }
	@test -n "$(APPLE_TEAM_ID)" || { echo "Set APPLE_TEAM_ID=YOURTEAMID"; exit 1; }
	xcrun notarytool store-credentials "$(NOTARY_PROFILE)" \
		--apple-id "$(APPLE_ID)" --team-id "$(APPLE_TEAM_ID)"

check-signing:
	@test -n "$(DEVELOPER_ID_APPLICATION)" || { echo "Missing Developer ID Application certificate in Keychain."; exit 1; }
	@COUNT=$$(security find-identity -v -p codesigning 2>/dev/null | grep -c "Developer ID Application:" || true); \
	if [ "$$COUNT" -gt 1 ]; then \
		echo "WARNING: $$COUNT Developer ID Application certificates found. Using: $(DEVELOPER_ID_APPLICATION)"; \
		echo "Set DEVELOPER_ID_APPLICATION explicitly if this is wrong."; \
	fi

check-notary-profile:
	@security find-generic-password -l "$(NOTARY_PROFILE)" >/dev/null 2>&1 || { \
		echo "Notary profile '$(NOTARY_PROFILE)' not found in Keychain. Run: make notary-store-credentials APPLE_ID=... APPLE_TEAM_ID=..."; \
		exit 1; \
	}

check-create-dmg:
	@command -v "$(CREATE_DMG)" >/dev/null || { echo "Missing create-dmg. Install it with: brew install create-dmg"; exit 1; }

sign: check-signing
	@# inside-out signing: Frameworks/ Mach-O → Swift binary → Python binary → outer bundle
	find $(APP_DIR)/Contents/Frameworks -type f \( -name '*.dylib' -o -name '*.so' -o -name '*.metallib' -o -perm +111 \) -print0 | \
		while IFS= read -r -d '' bin; do \
			if [ "$${bin##*.}" = "metallib" ] || file "$$bin" | grep -q "Mach-O"; then \
				codesign --force --timestamp --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" "$$bin"; \
			fi; \
		done
	codesign --force --timestamp --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" \
		$(APP_DIR)/Contents/MacOS/ohmyvoice-ui
	codesign --force --timestamp --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" \
		--entitlements entitlements.plist $(APP_DIR)/Contents/MacOS/ohmyvoice
	codesign --force --timestamp --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" \
		--entitlements entitlements.plist $(APP_DIR)
	codesign --verify --deep --strict $(APP_DIR)

notarize: sign check-notary-profile
	ditto -c -k --keepParent $(APP_DIR) dist/$(APP_NAME).zip
	xcrun notarytool submit dist/$(APP_NAME).zip \
		--keychain-profile "$(NOTARY_PROFILE)" --wait
	rm dist/$(APP_NAME).zip
	xcrun stapler staple $(APP_DIR)
	xcrun stapler validate $(APP_DIR)

dmg-local: dist check-create-dmg
	rm -f $(DMG_PATH)
	$(CREATE_DMG) $(CREATE_DMG_FLAGS) --volname $(APP_NAME) --window-size 600 400 \
		--icon-size 128 --icon $(APP_NAME).app 150 200 \
		--app-drop-link 450 200 \
		$(DMG_PATH) $(APP_DIR)

dmg: dist notarize check-create-dmg
	rm -f $(DMG_PATH)
	$(CREATE_DMG) $(CREATE_DMG_FLAGS) --volname $(APP_NAME) --window-size 600 400 \
		--icon-size 128 --icon $(APP_NAME).app 150 200 \
		--app-drop-link 450 200 \
		$(DMG_PATH) $(APP_DIR)
	codesign --force --timestamp --sign "$(DEVELOPER_ID_APPLICATION)" $(DMG_PATH)
	xcrun notarytool submit $(DMG_PATH) \
		--keychain-profile "$(NOTARY_PROFILE)" --wait
	xcrun stapler staple $(DMG_PATH)
	xcrun stapler validate $(DMG_PATH)

#!/bin/bash
set -euo pipefail

# Environment variables (must be set for signing/notarization):
# DEVELOPER_ID_APPLICATION  - signing identity, e.g. "Developer ID Application: Name (TEAMID)"
# APPLE_ID                  - Apple ID for notarytool
# APPLE_TEAM_ID             - Team ID
# APP_PASSWORD              - app-specific password for notarytool

# Extract version from source — no pip install needed
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ohmyvoice/__init__.py)
APP_NAME="OhMyVoice"
DMG_NAME="${APP_NAME}-${VERSION}-arm64.dmg"
APP_DIR="dist/${APP_NAME}.app"

# Step 1: Build Swift UI
cd ui && swift build -c release && cd ..

# Step 2: PyInstaller
pyinstaller ohmyvoice.spec --noconfirm

# Step 3: Post-build copy — resources and Swift binary
# PyInstaller datas go to _internal/, we need Contents/Resources/
mkdir -p "${APP_DIR}/Contents/Resources"
cp -R resources/icons  "${APP_DIR}/Contents/Resources/icons"
cp -R resources/sounds "${APP_DIR}/Contents/Resources/sounds" 2>/dev/null || true
cp resources/AppIcon.icns "${APP_DIR}/Contents/Resources/AppIcon.icns" 2>/dev/null || true
cp ui/.build/release/ohmyvoice-ui "${APP_DIR}/Contents/MacOS/"

# Step 4: Pre-flight check — @2x icons
for state in idle recording processing done; do
  if [ ! -f "${APP_DIR}/Contents/Resources/icons/mic_${state}@2x.png" ]; then
    echo "WARNING: missing mic_${state}@2x.png — Retina displays will show blurry icons"
  fi
done

# Step 5: Inside-out code signing
# Sign all Mach-O binaries in _internal/ first, then executables, then outer bundle
# 5a: _internal/ — all .so, .dylib, and executable Mach-O files
find "${APP_DIR}/Contents/MacOS/_internal" -type f \( -name '*.dylib' -o -name '*.so' -o -perm +111 \) | while read bin; do
  if file "$bin" | grep -q "Mach-O"; then
    codesign --force --options runtime --sign "${DEVELOPER_ID_APPLICATION}" "$bin"
  fi
done

# 5b: Swift UI binary (no special entitlements needed)
codesign --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  "${APP_DIR}/Contents/MacOS/ohmyvoice-ui"

# 5c: Python main executable (needs entitlements for MLX JIT)
codesign --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  --entitlements entitlements.plist \
  "${APP_DIR}/Contents/MacOS/ohmyvoice"

# 5d: Outer bundle
codesign --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  --entitlements entitlements.plist \
  "${APP_DIR}"

# Step 6: Notarize (notarytool needs zip/dmg/pkg, not bare .app)
ditto -c -k --keepParent "${APP_DIR}" "dist/${APP_NAME}.zip"
xcrun notarytool submit "dist/${APP_NAME}.zip" \
  --apple-id "${APPLE_ID}" \
  --team-id "${APPLE_TEAM_ID}" \
  --password "${APP_PASSWORD}" \
  --wait
rm "dist/${APP_NAME}.zip"

# Step 7: Staple
xcrun stapler staple "${APP_DIR}"

# Step 8: Create DMG
rm -f "dist/${DMG_NAME}"
create-dmg \
  --volname "${APP_NAME}" \
  --window-size 600 400 \
  --icon-size 128 \
  --icon "${APP_NAME}.app" 150 200 \
  --app-drop-link 450 200 \
  "dist/${DMG_NAME}" \
  "${APP_DIR}"

# Step 9: Sign and notarize DMG
codesign --sign "${DEVELOPER_ID_APPLICATION}" "dist/${DMG_NAME}"
xcrun notarytool submit "dist/${DMG_NAME}" \
  --apple-id "${APPLE_ID}" \
  --team-id "${APPLE_TEAM_ID}" \
  --password "${APP_PASSWORD}" \
  --wait
xcrun stapler staple "dist/${DMG_NAME}"

echo "Done! Output: dist/${DMG_NAME}"

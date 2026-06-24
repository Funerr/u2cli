#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER_DIR="$ROOT_DIR/android-snapshot-helper"
VERSION="${1:-0.1.0}"
OUT_DIR="${2:-$HELPER_DIR/dist}"

PACKAGE_NAME="com.callstack.androidtestclii.snapshothelper"
MIN_SDK=23
TARGET_SDK=36
APK_NAME="androidtestclii-android-snapshot-helper-$VERSION.apk"

ANDROID_HOME_VALUE="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/homebrew/share/android-commandlinetools}}"
ANDROID_JAR="$ANDROID_HOME_VALUE/platforms/android-$TARGET_SDK/android.jar"
BUILD_TOOLS_DIR="$(find "$ANDROID_HOME_VALUE/build-tools" -maxdepth 1 -type d 2>/dev/null | sort -V | tail -n 1)"

if [[ ! -f "$ANDROID_JAR" ]]; then
  echo "android.jar not found at $ANDROID_JAR" >&2
  exit 1
fi
if [[ -z "$BUILD_TOOLS_DIR" || ! -x "$BUILD_TOOLS_DIR/aapt2" || ! -x "$BUILD_TOOLS_DIR/d8" ]]; then
  echo "Android build tools not found under $ANDROID_HOME_VALUE/build-tools" >&2
  exit 1
fi
if [[ ! -x "$BUILD_TOOLS_DIR/zipalign" || ! -x "$BUILD_TOOLS_DIR/apksigner" ]]; then
  echo "zipalign or apksigner not found under $BUILD_TOOLS_DIR" >&2
  exit 1
fi

VERSION_CODE="$(
  printf '%s\n' "$VERSION" | awk -F. '
    /^[0-9]+[.][0-9]+[.][0-9]+$/ {
      print ($1 * 1000000) + ($2 * 1000) + $3
      next
    }
    { print 1 }
  '
)"

BUILD_DIR="$HELPER_DIR/build"
CLASSES_DIR="$BUILD_DIR/classes"
DEX_DIR="$BUILD_DIR/dex"
RES_DIR="$HELPER_DIR/src/main/res"
RES_FLAT_DIR="$BUILD_DIR/res-flat"
UNSIGNED_APK="$BUILD_DIR/helper-unsigned.apk"
ALIGNED_APK="$BUILD_DIR/helper-aligned.apk"
KEYSTORE="$HELPER_DIR/debug.keystore"
APK_PATH="$OUT_DIR/$APK_NAME"

rm -rf "$BUILD_DIR"
mkdir -p "$CLASSES_DIR" "$DEX_DIR" "$RES_FLAT_DIR" "$OUT_DIR"

javac \
  --release 11 \
  -classpath "$ANDROID_JAR" \
  -d "$CLASSES_DIR" \
  $(find "$HELPER_DIR/src/main/java" -name '*.java' | sort)

"$BUILD_TOOLS_DIR/d8" \
  --min-api "$MIN_SDK" \
  --classpath "$ANDROID_JAR" \
  --output "$DEX_DIR" \
  $(find "$CLASSES_DIR" -name '*.class' | sort)

LINK_INPUTS=()
if [[ -d "$RES_DIR" ]]; then
  "$BUILD_TOOLS_DIR/aapt2" compile \
    --dir "$RES_DIR" \
    -o "$RES_FLAT_DIR/resources.zip"
  LINK_INPUTS+=("$RES_FLAT_DIR/resources.zip")
fi

"$BUILD_TOOLS_DIR/aapt2" link \
  --manifest "$HELPER_DIR/AndroidManifest.xml" \
  -I "$ANDROID_JAR" \
  --min-sdk-version "$MIN_SDK" \
  --target-sdk-version "$TARGET_SDK" \
  --version-code "$VERSION_CODE" \
  --version-name "$VERSION" \
  "${LINK_INPUTS[@]}" \
  -o "$UNSIGNED_APK"

zip -q -j "$UNSIGNED_APK" "$DEX_DIR/classes.dex"
"$BUILD_TOOLS_DIR/zipalign" -f 4 "$UNSIGNED_APK" "$ALIGNED_APK"

if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair \
    -keystore "$KEYSTORE" \
    -storepass android \
    -keypass android \
    -alias androiddebugkey \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -dname "CN=Android Debug,O=Android,C=US" \
    >/dev/null
fi

"$BUILD_TOOLS_DIR/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-key-alias androiddebugkey \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out "$APK_PATH" \
  "$ALIGNED_APK"

rm -f "$APK_PATH.idsig"
"$BUILD_TOOLS_DIR/apksigner" verify --min-sdk-version "$MIN_SDK" "$APK_PATH"
shasum -a 256 "$APK_PATH" | awk '{print $1}' > "$APK_PATH.sha256"

cat > "$APK_PATH.manifest.json" <<EOF
{
  "name": "android-snapshot-helper",
  "version": "$VERSION",
  "assetName": "$APK_NAME",
  "apkUrl": null,
  "sha256": "$(cat "$APK_PATH.sha256")",
  "packageName": "$PACKAGE_NAME",
  "versionCode": $VERSION_CODE,
  "instrumentationRunner": "$PACKAGE_NAME/.SnapshotInstrumentation",
  "minSdk": $MIN_SDK,
  "targetSdk": $TARGET_SDK,
  "outputFormat": "uiautomator-xml",
  "statusProtocol": "androidtestclii-snapshot-helper-v1",
  "installArgs": ["install", "-r", "-t"]
}
EOF

echo "$APK_PATH"

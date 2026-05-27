#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/android-snapshot-jar"
VERSION="${1:-0.1.0}"
OUT_DIR="${2:-$PROJECT_DIR/dist}"

ANDROID_HOME_VALUE="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/homebrew/share/android-commandlinetools}}"
PLATFORM_DIR="$(find "$ANDROID_HOME_VALUE/platforms" -maxdepth 1 -type d -name 'android-*' | sort -V | tail -n 1)"
BUILD_TOOLS_DIR="$(find "$ANDROID_HOME_VALUE/build-tools" -maxdepth 1 -type d | sort -V | tail -n 1)"
ANDROID_JAR="$PLATFORM_DIR/android.jar"
UIAUTOMATOR_JAR="$PLATFORM_DIR/uiautomator.jar"
D8_BIN="$BUILD_TOOLS_DIR/d8"

if [[ ! -f "$ANDROID_JAR" || ! -f "$UIAUTOMATOR_JAR" ]]; then
  echo "android.jar or uiautomator.jar not found under $ANDROID_HOME_VALUE" >&2
  exit 1
fi
if [[ ! -x "$D8_BIN" ]]; then
  echo "d8 not found under $ANDROID_HOME_VALUE/build-tools" >&2
  exit 1
fi

TMP_DIR="$PROJECT_DIR/build"
STUB_SRC="$TMP_DIR/stubs-src"
STUB_CLASSES="$TMP_DIR/stubs-classes"
RUNTIME_STUB_SRC="$TMP_DIR/runtime-stubs-src"
RUNTIME_STUB_CLASSES="$TMP_DIR/runtime-stubs-classes"
CLASSES_DIR="$TMP_DIR/classes"
CLASSES_JAR="$TMP_DIR/classes.jar"
RUNTIME_STUBS_JAR="$TMP_DIR/runtime-stubs.jar"
DEX_DIR="$TMP_DIR/dex"

rm -rf "$TMP_DIR"
mkdir -p \
  "$STUB_SRC/junit/framework" \
  "$STUB_CLASSES" \
  "$RUNTIME_STUB_SRC/android/test" \
  "$RUNTIME_STUB_CLASSES" \
  "$CLASSES_DIR" \
  "$DEX_DIR" \
  "$OUT_DIR"

cat > "$STUB_SRC/junit/framework/TestCase.java" <<'STUB'
package junit.framework;
public class TestCase {
    public TestCase() {}
    public TestCase(String name) {}
}
STUB

javac --release 11 -d "$STUB_CLASSES" "$STUB_SRC/junit/framework/TestCase.java"

cat > "$RUNTIME_STUB_SRC/android/test/RepetitiveTest.java" <<'STUB'
package android.test;
public interface RepetitiveTest {
    int numIterations();
}
STUB

javac --release 11 -d "$RUNTIME_STUB_CLASSES" "$RUNTIME_STUB_SRC/android/test/RepetitiveTest.java"

javac --release 11 \
  -classpath "$ANDROID_JAR:$UIAUTOMATOR_JAR:$STUB_CLASSES" \
  -d "$CLASSES_DIR" \
  $(find "$PROJECT_DIR/src/main/java" -name '*.java' | sort)

(cd "$CLASSES_DIR" && jar cf "$CLASSES_JAR" .)
(cd "$RUNTIME_STUB_CLASSES" && jar cf "$RUNTIME_STUBS_JAR" .)

"$D8_BIN" \
  --min-api 23 \
  --classpath "$ANDROID_JAR" \
  --classpath "$UIAUTOMATOR_JAR" \
  --output "$DEX_DIR" \
  "$CLASSES_JAR" \
  "$RUNTIME_STUBS_JAR"

JAR_NAME="u2cli-android-snapshot-jar-$VERSION.jar"
(cd "$DEX_DIR" && jar cf "$OUT_DIR/$JAR_NAME" classes.dex)
shasum -a 256 "$OUT_DIR/$JAR_NAME" | awk '{print $1}' > "$OUT_DIR/$JAR_NAME.sha256"
printf '{"assetName":"%s","version":"%s","protocol":"u2cli-android-snapshot-jar-v1","entryClass":"io.github.funerr.u2cli.snapshotjar.SnapshotDump"}\n' \
  "$JAR_NAME" "$VERSION" > "$OUT_DIR/$JAR_NAME.manifest.json"

echo "$OUT_DIR/$JAR_NAME"

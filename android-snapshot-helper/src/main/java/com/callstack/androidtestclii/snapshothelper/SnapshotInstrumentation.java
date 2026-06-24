package com.callstack.androidtestclii.snapshothelper;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.ComponentName;
import android.content.Context;
import android.graphics.Rect;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeoutException;

public final class SnapshotInstrumentation extends Instrumentation {
  private static final String PROTOCOL = "androidtestclii-snapshot-helper-v1";
  private static final String OUTPUT_FORMAT = "uiautomator-xml";
  private static final String HELPER_API_VERSION = "1";
  private static final int CHUNK_SIZE = 8 * 1024;
  private static final long DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS = 500;
  private static final long DEFAULT_TIMEOUT_MS = 8_000;
  private static final int DEFAULT_MAX_DEPTH = 128;
  private static final int DEFAULT_MAX_NODES = 5_000;
  private static final String ACTION_SNAPSHOT = "snapshot";
  private static final String ACTION_TOAST_GET = "toast-get";
  private static final String ACTION_TOAST_CLEAR = "toast-clear";
  private static final String TOAST_STATUS_CAPTURED = "captured";
  private static final String TOAST_STATUS_EMPTY = "empty";
  private static final String TOAST_STATUS_DISABLED = "disabled";
  private static final String TOAST_STATUS_ERROR = "error";
  private Bundle arguments;

  @Override
  public void onCreate(Bundle arguments) {
    super.onCreate(arguments);
    this.arguments = arguments;
    start();
  }

  @Override
  public void onStart() {
    super.onStart();
    long waitForIdleTimeoutMs =
        readLongArgument(arguments, "waitForIdleTimeoutMs", DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS);
    long timeoutMs = readLongArgument(arguments, "timeoutMs", DEFAULT_TIMEOUT_MS);
    int maxDepth = readIntArgument(arguments, "maxDepth", DEFAULT_MAX_DEPTH);
    int maxNodes = readIntArgument(arguments, "maxNodes", DEFAULT_MAX_NODES);
    Bundle result = new Bundle();
    result.putString("androidtestcliiProtocol", PROTOCOL);
    result.putString("helperApiVersion", HELPER_API_VERSION);
    result.putString("outputFormat", OUTPUT_FORMAT);
    result.putString("waitForIdleTimeoutMs", Long.toString(waitForIdleTimeoutMs));
    result.putString("timeoutMs", Long.toString(timeoutMs));
    result.putString("maxDepth", Integer.toString(maxDepth));
    result.putString("maxNodes", Integer.toString(maxNodes));

    try {
      String action = readStringArgument(arguments, "action", ACTION_SNAPSHOT);
      result.putString("action", action);
      if (ACTION_TOAST_CLEAR.equals(action)) {
        clearToastHistory(result);
        result.putString("ok", "true");
        finish(0, result);
        return;
      }
      if (ACTION_TOAST_GET.equals(action)) {
        appendToastStatus(result);
        result.putString("ok", "true");
        finish(0, result);
        return;
      }
      long startedAtMs = System.currentTimeMillis();
      CaptureResult capture = captureXml(waitForIdleTimeoutMs, maxDepth, maxNodes);
      emitChunks(capture.xml);
      appendToastStatus(result);
      result.putString("ok", "true");
      result.putString("rootPresent", Boolean.toString(capture.rootPresent));
      result.putString("captureMode", capture.captureMode);
      result.putString("windowCount", Integer.toString(capture.windowCount));
      result.putString("nodeCount", Integer.toString(capture.nodeCount));
      result.putString("truncated", Boolean.toString(capture.truncated));
      result.putString("elapsedMs", Long.toString(System.currentTimeMillis() - startedAtMs));
      finish(0, result);
    } catch (Throwable error) {
      result.putString("ok", "false");
      result.putString("errorType", error.getClass().getName());
      result.putString(
          "message",
          error.getMessage() == null ? error.getClass().getName() : error.getMessage());
      finish(1, result);
    }
  }

  private void clearToastHistory(Bundle result) {
    try {
      new ToastHistoryStore(getTargetContext()).clear();
      result.putString("toastStatus", TOAST_STATUS_EMPTY);
      result.putString("toastReason", "history_cleared");
      result.putString("toastMessage", "Toast history cleared");
      result.putString("toastHistorySize", "0");
      result.putString("toastMaxHistorySize", Integer.toString(ToastHistoryStore.MAX_HISTORY_SIZE));
    } catch (RuntimeException error) {
      appendToastError(result, error);
    }
  }

  private void appendToastStatus(Bundle result) {
    try {
      ToastHistoryStore.Snapshot snapshot = new ToastHistoryStore(getTargetContext()).consumeLatest();
      result.putString("toastHistorySize", Integer.toString(snapshot.size()));
      result.putString("toastMaxHistorySize", Integer.toString(ToastHistoryStore.MAX_HISTORY_SIZE));
      if (snapshot.latest == null) {
        if (!isToastServiceEnabled(getTargetContext())) {
          result.putString("toastStatus", TOAST_STATUS_DISABLED);
          result.putString("toastReason", "service_disabled");
          result.putString("toastMessage", "AndroidTestClii Toast accessibility service is disabled");
          return;
        }
        result.putString("toastStatus", TOAST_STATUS_EMPTY);
        result.putString("toastReason", "no_unconsumed_toast");
        result.putString("toastMessage", "No unconsumed Toast captured in helper history");
        return;
      }
      ToastHistoryStore.Observation latest = snapshot.latest;
      result.putString("toastStatus", TOAST_STATUS_CAPTURED);
      result.putString("toastReason", "latest");
      result.putString("toastMessage", "Latest Toast captured");
      result.putString("toastLatestId", Long.toString(latest.id));
      result.putString("toastLatestTextBase64", encodeUtf8(latest.text));
      if (!latest.packageName.isEmpty()) {
        result.putString("toastLatestPackage", latest.packageName);
      }
      result.putString("toastLatestCapturedAtMs", Long.toString(latest.capturedAtMs));
    } catch (RuntimeException error) {
      appendToastError(result, error);
    }
  }

  private static void appendToastError(Bundle result, RuntimeException error) {
    result.putString("toastStatus", TOAST_STATUS_ERROR);
    result.putString("toastReason", "helper_error");
    result.putString(
        "toastMessage",
        error.getMessage() == null ? error.getClass().getName() : error.getMessage());
    result.putString("toastHistorySize", "0");
    result.putString("toastMaxHistorySize", Integer.toString(ToastHistoryStore.MAX_HISTORY_SIZE));
  }

  private static boolean isToastServiceEnabled(Context context) {
    String enabledServices =
        Settings.Secure.getString(
            context.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
    if (enabledServices == null || enabledServices.isEmpty()) {
      return false;
    }
    ComponentName service =
        new ComponentName(context.getPackageName(), ToastAccessibilityService.class.getName());
    String flattened = service.flattenToString();
    String shortFlattened = service.flattenToShortString();
    String[] services = enabledServices.split(":");
    for (String candidate : services) {
      if (flattened.equals(candidate) || shortFlattened.equals(candidate)) {
        return true;
      }
    }
    return false;
  }

  @SuppressWarnings("deprecation")
  private CaptureResult captureXml(long waitForIdleTimeoutMs, int maxDepth, int maxNodes)
      throws TimeoutException {
    UiAutomation automation = getUiAutomation();
    enableInteractiveWindowRetrieval(automation);
    if (waitForIdleTimeoutMs > 0) {
      try {
        // Best-effort settle: avoids empty roots without inheriting UIAutomator's long idle wait.
        automation.waitForIdle(waitForIdleTimeoutMs, waitForIdleTimeoutMs);
      } catch (TimeoutException ignored) {
        // Busy or animated apps can still expose a usable root; capture whatever is available.
      }
    }

    CaptureStats stats = new CaptureStats();
    StringBuilder xml = new StringBuilder();
    xml.append("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>");
    xml.append("<hierarchy rotation=\"0\">");
    int windowCount = appendInteractiveWindowRoots(xml, automation, maxDepth, maxNodes, stats);
    String captureMode = "interactive-windows";
    if (windowCount == 0) {
      AccessibilityNodeInfo root = automation.getRootInActiveWindow();
      try {
        if (root != null) {
          appendNode(xml, root, 0, 0, maxDepth, maxNodes, stats);
          windowCount = 1;
        }
        captureMode = "active-window";
      } finally {
        if (root != null) {
          root.recycle();
        }
      }
    }
    xml.append("</hierarchy>");
    return new CaptureResult(
        xml.toString(), windowCount > 0, captureMode, windowCount, stats.nodeCount, stats.truncated);
  }

  private static void enableInteractiveWindowRetrieval(UiAutomation automation) {
    AccessibilityServiceInfo serviceInfo;
    try {
      serviceInfo = automation.getServiceInfo();
    } catch (RuntimeException error) {
      return;
    }
    if (serviceInfo == null) {
      return;
    }
    if ((serviceInfo.flags & AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS) != 0) {
      return;
    }
    serviceInfo.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
    try {
      automation.setServiceInfo(serviceInfo);
    } catch (RuntimeException ignored) {
      // Fall back to active-window capture if the platform rejects dynamic service flags.
    }
  }

  @SuppressWarnings("deprecation")
  private static int appendInteractiveWindowRoots(
      StringBuilder xml,
      UiAutomation automation,
      int maxDepth,
      int maxNodes,
      CaptureStats stats) {
    List<AccessibilityWindowInfo> windows;
    try {
      windows = automation.getWindows();
    } catch (RuntimeException error) {
      return 0;
    }
    int windowCount = 0;
    for (int index = 0; index < windows.size(); index += 1) {
      if (stats.nodeCount >= maxNodes) {
        stats.truncated = true;
        break;
      }
      AccessibilityWindowInfo window = windows.get(index);
      AccessibilityNodeInfo root = null;
      try {
        root = window.getRoot();
        if (root == null) {
          continue;
        }
        StringBuilder windowXml = new StringBuilder();
        CaptureStats windowStats = stats.copy();
        appendNode(windowXml, root, windowCount, 0, maxDepth, maxNodes, windowStats);
        xml.append(windowXml);
        stats.copyFrom(windowStats);
        windowCount += 1;
      } catch (RuntimeException ignored) {
        // Accessibility windows can disappear while traversing; keep the rest of the snapshot.
      } finally {
        if (root != null) {
          root.recycle();
        }
        // UiAutomation.getWindows() transfers recyclable AccessibilityWindowInfo instances.
        window.recycle();
      }
    }
    return windowCount;
  }

  private void emitChunks(String payload) {
    byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
    int chunkCount = Math.max(1, (bytes.length + CHUNK_SIZE - 1) / CHUNK_SIZE);
    for (int index = 0; index < chunkCount; index += 1) {
      int start = index * CHUNK_SIZE;
      int end = Math.min(bytes.length, start + CHUNK_SIZE);
      Bundle status = new Bundle();
      status.putString("androidtestcliiProtocol", PROTOCOL);
      status.putString("helperApiVersion", HELPER_API_VERSION);
      status.putString("outputFormat", OUTPUT_FORMAT);
      status.putString("chunkIndex", Integer.toString(index));
      status.putString("chunkCount", Integer.toString(chunkCount));
      status.putString(
          "payloadBase64", Base64.encodeToString(bytes, start, end - start, Base64.NO_WRAP));
      sendStatus(1, status);
    }
  }

  @SuppressWarnings("deprecation")
  private static void appendNode(
      StringBuilder xml,
      AccessibilityNodeInfo node,
      int nodeIndex,
      int depth,
      int maxDepth,
      int maxNodes,
      CaptureStats stats) {
    if (stats.nodeCount >= maxNodes) {
      stats.truncated = true;
      return;
    }
    stats.nodeCount += 1;
    Rect bounds = new Rect();
    node.getBoundsInScreen(bounds);
    xml.append("<node");
    appendAttribute(xml, "index", Integer.toString(nodeIndex));
    appendAttribute(xml, "text", node.getText());
    appendAttribute(xml, "resource-id", node.getViewIdResourceName());
    appendAttribute(xml, "class", node.getClassName());
    appendAttribute(xml, "package", node.getPackageName());
    appendAttribute(xml, "content-desc", node.getContentDescription());
    appendAttribute(xml, "checkable", Boolean.toString(node.isCheckable()));
    appendAttribute(xml, "checked", Boolean.toString(node.isChecked()));
    appendAttribute(xml, "clickable", Boolean.toString(node.isClickable()));
    appendAttribute(xml, "enabled", Boolean.toString(node.isEnabled()));
    appendAttribute(xml, "focusable", Boolean.toString(node.isFocusable()));
    appendAttribute(xml, "focused", Boolean.toString(node.isFocused()));
    appendAttribute(xml, "scrollable", Boolean.toString(node.isScrollable()));
    appendAttribute(xml, "long-clickable", Boolean.toString(node.isLongClickable()));
    appendAttribute(xml, "password", Boolean.toString(node.isPassword()));
    appendAttribute(xml, "selected", Boolean.toString(node.isSelected()));
    appendAttribute(
        xml,
        "bounds",
        String.format(
            Locale.ROOT,
            "[%d,%d][%d,%d]",
            bounds.left,
            bounds.top,
            bounds.right,
            bounds.bottom));

    int childCount = depth >= maxDepth ? 0 : node.getChildCount();
    if (depth >= maxDepth && node.getChildCount() > 0) {
      stats.truncated = true;
    }
    if (childCount <= 0) {
      xml.append(" />");
      return;
    }

    xml.append(">");
    for (int index = 0; index < childCount; index += 1) {
      if (stats.nodeCount >= maxNodes) {
        stats.truncated = true;
        break;
      }
      AccessibilityNodeInfo child = node.getChild(index);
      if (child == null) {
        continue;
      }
      try {
        appendNode(xml, child, index, depth + 1, maxDepth, maxNodes, stats);
      } finally {
        child.recycle();
      }
    }
    xml.append("</node>");
  }

  private static void appendAttribute(StringBuilder xml, String name, CharSequence value) {
    String stringValue = value == null ? "" : value.toString();
    xml.append(' ');
    xml.append(name);
    xml.append("=\"");
    appendEscaped(xml, stringValue);
    xml.append('"');
  }

  private static void appendEscaped(StringBuilder xml, String value) {
    for (int index = 0; index < value.length(); index += 1) {
      char character = value.charAt(index);
      switch (character) {
        case '&':
          xml.append("&amp;");
          break;
        case '<':
          xml.append("&lt;");
          break;
        case '>':
          xml.append("&gt;");
          break;
        case '"':
          xml.append("&quot;");
          break;
        case '\'':
          xml.append("&apos;");
          break;
        case '\n':
          xml.append("&#10;");
          break;
        case '\r':
          xml.append("&#13;");
          break;
        case '\t':
          xml.append("&#9;");
          break;
        default:
          xml.append(character);
          break;
      }
    }
  }

  private static long readLongArgument(Bundle arguments, String name, long fallback) {
    if (arguments == null) {
      return fallback;
    }
    String raw = arguments.getString(name);
    if (raw == null || raw.trim().isEmpty()) {
      return fallback;
    }
    try {
      return Math.max(0, Long.parseLong(raw.trim()));
    } catch (NumberFormatException error) {
      return fallback;
    }
  }

  private static int readIntArgument(Bundle arguments, String name, int fallback) {
    if (arguments == null) {
      return fallback;
    }
    String raw = arguments.getString(name);
    if (raw == null || raw.trim().isEmpty()) {
      return fallback;
    }
    try {
      return Math.max(0, Integer.parseInt(raw.trim()));
    } catch (NumberFormatException error) {
      return fallback;
    }
  }

  private static String readStringArgument(Bundle arguments, String name, String fallback) {
    if (arguments == null) {
      return fallback;
    }
    String raw = arguments.getString(name);
    if (raw == null || raw.trim().isEmpty()) {
      return fallback;
    }
    return raw.trim();
  }

  private static String encodeUtf8(String value) {
    return Base64.encodeToString(value.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
  }

  private static final class CaptureStats {
    int nodeCount;
    boolean truncated;

    CaptureStats copy() {
      CaptureStats next = new CaptureStats();
      next.nodeCount = nodeCount;
      next.truncated = truncated;
      return next;
    }

    void copyFrom(CaptureStats next) {
      nodeCount = next.nodeCount;
      truncated = next.truncated;
    }
  }

  private static final class CaptureResult {
    final String xml;
    final boolean rootPresent;
    final String captureMode;
    final int windowCount;
    final int nodeCount;
    final boolean truncated;

    CaptureResult(
        String xml,
        boolean rootPresent,
        String captureMode,
        int windowCount,
        int nodeCount,
        boolean truncated) {
      this.xml = xml;
      this.rootPresent = rootPresent;
      this.captureMode = captureMode;
      this.windowCount = windowCount;
      this.nodeCount = nodeCount;
      this.truncated = truncated;
    }
  }
}

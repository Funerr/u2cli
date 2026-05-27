package io.github.funerr.u2cli.snapshotjar;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import android.util.Xml;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import com.android.uiautomator.core.UiDevice;
import com.android.uiautomator.testrunner.UiAutomatorTestCase;

import org.json.JSONObject;
import org.xmlpull.v1.XmlSerializer;

import java.io.File;
import java.io.FileInputStream;
import java.io.StringWriter;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class SnapshotDump extends UiAutomatorTestCase {
    private static final String PROTOCOL = "u2cli-android-snapshot-jar-v1";
    private static final String OUTPUT_FORMAT = "uiautomator-xml";
    private static final String HELPER_API_VERSION = "1";
    private static final int CHUNK_SIZE = 60_000;
    private static final int DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS = 500;
    private static final int DEFAULT_CAPTURE_TIMEOUT_MS = 8_000;
    private static final int DEFAULT_MAX_DEPTH = 128;
    private static final int DEFAULT_MAX_NODES = 5_000;

    public void testSnapshot() throws Exception {
        long startedAt = SystemClock.uptimeMillis();
        CaptureConfig config = CaptureConfig.from(getParams());
        CaptureResult result;
        try {
            UiDevice device = getUiDevice();
            device.waitForIdle(config.waitForIdleTimeoutMs);
            UiAutomation automation = findUiAutomation(device, getAutomationSupport(), this);
            if (automation != null) {
                result = captureInteractiveWindows(automation, config);
            } else {
                result = captureWithUiDeviceDump(device);
            }
            result.metadata.put("ok", true);
        } catch (Throwable throwable) {
            result = new CaptureResult();
            result.metadata.put("ok", false);
            result.metadata.put("errorType", throwable.getClass().getName());
            result.metadata.put("message", String.valueOf(throwable.getMessage()));
        }
        result.metadata.put("protocol", PROTOCOL);
        result.metadata.put("helperApiVersion", HELPER_API_VERSION);
        result.metadata.put("outputFormat", OUTPUT_FORMAT);
        result.metadata.put("waitForIdleTimeoutMs", config.waitForIdleTimeoutMs);
        result.metadata.put("timeoutMs", config.timeoutMs);
        result.metadata.put("maxDepth", config.maxDepth);
        result.metadata.put("maxNodes", config.maxNodes);
        result.metadata.put("elapsedMs", SystemClock.uptimeMillis() - startedAt);
        emitResult(result);
    }

    private static CaptureResult captureInteractiveWindows(
            UiAutomation automation,
            CaptureConfig config
    ) throws Exception {
        configureAccessibilityFlags(automation);
        try {
            automation.waitForIdle(config.waitForIdleTimeoutMs, config.timeoutMs);
        } catch (Throwable ignored) {
            // Animated or streaming UIs can stay non-idle. Snapshot anyway instead of blocking.
        }

        List<AccessibilityWindowInfo> windows = readWindows(automation);
        List<RootRef> roots = new ArrayList<>();
        Set<String> rootKeys = new HashSet<>();
        for (int i = 0; i < windows.size(); i++) {
            AccessibilityWindowInfo window = windows.get(i);
            AccessibilityNodeInfo root = safeWindowRoot(window);
            addRoot(roots, rootKeys, root, window);
        }
        String captureMode = "interactive-windows";
        int windowCount = roots.size();
        if (roots.isEmpty()) {
            AccessibilityNodeInfo activeRoot = automation.getRootInActiveWindow();
            addRoot(roots, rootKeys, activeRoot, null);
            captureMode = "active-window";
            windowCount = roots.isEmpty() ? 0 : 1;
        }

        NodeStats stats = new NodeStats(config.maxDepth, config.maxNodes);
        XmlSerializer serializer = Xml.newSerializer();
        StringWriter writer = new StringWriter();
        serializer.setOutput(writer);
        serializer.startDocument("UTF-8", true);
        serializer.startTag("", "hierarchy");
        serializer.attribute("", "rotation", "0");
        serializer.attribute("", "capture-mode", captureMode);
        serializer.attribute("", "window-count", String.valueOf(windowCount));
        for (int i = 0; i < roots.size(); i++) {
            writeNode(serializer, roots.get(i).node, roots.get(i).window, stats, 0);
            if (stats.truncated) {
                break;
            }
        }
        serializer.endTag("", "hierarchy");
        serializer.endDocument();

        CaptureResult result = new CaptureResult();
        result.xml = writer.toString();
        result.metadata.put("captureMode", captureMode);
        result.metadata.put("rootPresent", !roots.isEmpty());
        result.metadata.put("windowCount", windowCount);
        result.metadata.put("nodeCount", stats.nodeCount);
        result.metadata.put("truncated", stats.truncated);
        if (stats.childFetchErrors > 0) {
            result.metadata.put("childFetchErrors", stats.childFetchErrors);
        }
        return result;
    }

    private static CaptureResult captureWithUiDeviceDump(UiDevice device) throws Exception {
        String fileName = "u2cli-window-dump.xml";
        File file = new File("/data/local/tmp", fileName);
        device.dumpWindowHierarchy(fileName);
        byte[] bytes = readAll(file);
        CaptureResult result = new CaptureResult();
        result.xml = new String(bytes, StandardCharsets.UTF_8);
        result.metadata.put("captureMode", "ui-device-dump");
        result.metadata.put("rootPresent", result.xml.contains("<hierarchy"));
        result.metadata.put("windowCount", 1);
        result.metadata.put("nodeCount", JSONObject.NULL);
        result.metadata.put("truncated", false);
        result.metadata.put("fallbackReason", "UiAutomation reflection unavailable");
        // Best effort cleanup. Failure does not affect the captured XML.
        file.delete();
        return result;
    }

    private static void configureAccessibilityFlags(UiAutomation automation) {
        AccessibilityServiceInfo info = automation.getServiceInfo();
        if (info == null) {
            return;
        }
        info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        info.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
        automation.setServiceInfo(info);
    }

    private static List<AccessibilityWindowInfo> readWindows(UiAutomation automation) {
        List<AccessibilityWindowInfo> windows = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= 30) {
            Object allDisplays = callNoArg(automation, "getWindowsOnAllDisplays");
            if (allDisplays != null) {
                int size = intCall(allDisplays, "size", 0);
                for (int i = 0; i < size; i++) {
                    Object value = callOneArg(allDisplays, "valueAt", int.class, i);
                    if (value instanceof List<?>) {
                        for (Object item : (List<?>) value) {
                            if (item instanceof AccessibilityWindowInfo) {
                                windows.add((AccessibilityWindowInfo) item);
                            }
                        }
                    }
                }
                return windows;
            }
        }
        List<AccessibilityWindowInfo> singleDisplayWindows = automation.getWindows();
        if (singleDisplayWindows != null) {
            windows.addAll(singleDisplayWindows);
        }
        return windows;
    }

    private static void addRoot(
            List<RootRef> roots,
            Set<String> rootKeys,
            AccessibilityNodeInfo root,
            AccessibilityWindowInfo window
    ) {
        if (root == null) {
            return;
        }
        Rect bounds = new Rect();
        root.getBoundsInScreen(bounds);
        String key = root.getWindowId() + ":"
                + bounds.left + "," + bounds.top + "," + bounds.right + "," + bounds.bottom + ":"
                + safe(root.getPackageName()) + ":" + safe(root.getClassName());
        if (rootKeys.add(key)) {
            roots.add(new RootRef(root, window));
        }
    }

    private static AccessibilityNodeInfo safeWindowRoot(AccessibilityWindowInfo window) {
        try {
            return window.getRoot();
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static void writeNode(
            XmlSerializer serializer,
            AccessibilityNodeInfo node,
            AccessibilityWindowInfo window,
            NodeStats stats,
            int depth
    ) throws Exception {
        if (node == null || stats.truncated) {
            return;
        }
        if (depth > stats.maxDepth || stats.nodeCount >= stats.maxNodes) {
            stats.truncated = true;
            return;
        }

        int index = stats.nodeCount++;
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        serializer.startTag("", "node");
        attribute(serializer, "index", String.valueOf(index));
        attribute(serializer, "text", safe(node.getText()));
        attribute(serializer, "resource-id", safe(node.getViewIdResourceName()));
        attribute(serializer, "class", safe(node.getClassName()));
        attribute(serializer, "package", safe(node.getPackageName()));
        attribute(serializer, "content-desc", safe(node.getContentDescription()));
        attribute(serializer, "checkable", bool(node.isCheckable()));
        attribute(serializer, "checked", bool(node.isChecked()));
        attribute(serializer, "clickable", bool(node.isClickable()));
        attribute(serializer, "enabled", bool(node.isEnabled()));
        attribute(serializer, "focusable", bool(node.isFocusable()));
        attribute(serializer, "focused", bool(node.isFocused()));
        attribute(serializer, "scrollable", bool(node.isScrollable()));
        attribute(serializer, "long-clickable", bool(node.isLongClickable()));
        attribute(serializer, "password", bool(node.isPassword()));
        attribute(serializer, "selected", bool(node.isSelected()));
        attribute(serializer, "visible-to-user", bool(node.isVisibleToUser()));
        attribute(serializer, "bounds", boundsToString(bounds));
        if (window != null) {
            attribute(serializer, "window-id", String.valueOf(safeWindowInt(window, "getId", -1)));
            attribute(serializer, "window-type", String.valueOf(safeWindowInt(window, "getType", -1)));
            attribute(serializer, "window-layer", String.valueOf(safeWindowInt(window, "getLayer", -1)));
            attribute(serializer, "window-active", bool(window.isActive()));
            attribute(serializer, "window-focused", bool(window.isFocused()));
            if (Build.VERSION.SDK_INT >= 30) {
                attribute(
                        serializer,
                        "display-id",
                        String.valueOf(safeWindowInt(window, "getDisplayId", -1))
                );
            }
            Rect windowBounds = new Rect();
            window.getBoundsInScreen(windowBounds);
            attribute(serializer, "window-bounds", boundsToString(windowBounds));
        }

        int childCount = node.getChildCount();
        for (int i = 0; i < childCount; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Throwable ignored) {
                stats.childFetchErrors++;
            }
            if (child != null) {
                writeNode(serializer, child, window, stats, depth + 1);
            }
            if (stats.truncated) {
                break;
            }
        }
        serializer.endTag("", "node");
    }

    private static UiAutomation findUiAutomation(Object... roots) {
        ArrayDeque<Object> queue = new ArrayDeque<>();
        Set<Object> seen = java.util.Collections.newSetFromMap(new IdentityHashMap<Object, Boolean>());
        for (Object root : roots) {
            if (root != null) {
                queue.add(root);
            }
        }

        int inspected = 0;
        while (!queue.isEmpty() && inspected < 128) {
            Object current = queue.removeFirst();
            if (current == null || !seen.add(current)) {
                continue;
            }
            inspected++;
            if (current instanceof UiAutomation) {
                return (UiAutomation) current;
            }

            Object methodValue = callNoArg(current, "getUiAutomation");
            if (methodValue instanceof UiAutomation) {
                return (UiAutomation) methodValue;
            }
            Object bridge = callNoArg(current, "getAutomatorBridge");
            if (bridge instanceof UiAutomation) {
                return (UiAutomation) bridge;
            }
            if (bridge != null) {
                queue.add(bridge);
            }

            Class<?> type = current.getClass();
            while (type != null && !type.getName().startsWith("java.")) {
                Field[] fields;
                try {
                    fields = type.getDeclaredFields();
                } catch (Throwable ignored) {
                    fields = new Field[0];
                }
                for (Field field : fields) {
                    Object value = readField(field, current);
                    if (value instanceof UiAutomation) {
                        return (UiAutomation) value;
                    }
                    if (isUsefulReflectionTarget(value)) {
                        queue.add(value);
                    }
                }
                type = type.getSuperclass();
            }
        }
        return null;
    }

    private static boolean isUsefulReflectionTarget(Object value) {
        if (value == null) {
            return false;
        }
        String name = value.getClass().getName();
        return name.startsWith("com.android.uiautomator.")
                || name.startsWith("android.app.")
                || name.startsWith("android.view.accessibility.");
    }

    private static Object readField(Field field, Object target) {
        try {
            field.setAccessible(true);
            return field.get(target);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static Object callNoArg(Object target, String methodName) {
        try {
            Method method = findMethod(target.getClass(), methodName);
            if (method == null) {
                return null;
            }
            method.setAccessible(true);
            return method.invoke(target);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static Object callOneArg(
            Object target,
            String methodName,
            Class<?> parameterType,
            Object value
    ) {
        try {
            Method method = findMethod(target.getClass(), methodName, parameterType);
            if (method == null) {
                return null;
            }
            method.setAccessible(true);
            return method.invoke(target, value);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static Method findMethod(Class<?> type, String methodName, Class<?>... parameterTypes) {
        Class<?> current = type;
        while (current != null) {
            try {
                return current.getDeclaredMethod(methodName, parameterTypes);
            } catch (NoSuchMethodException ignored) {
                current = current.getSuperclass();
            }
        }
        return null;
    }

    private static int intCall(Object target, String methodName, int fallback) {
        Object value = callNoArg(target, methodName);
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return fallback;
    }

    private static int safeWindowInt(AccessibilityWindowInfo window, String methodName, int fallback) {
        Object value = callNoArg(window, methodName);
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return fallback;
    }

    private static void emitResult(CaptureResult result) throws Exception {
        String xmlBase64 = Base64.encodeToString(
                result.xml.getBytes(StandardCharsets.UTF_8),
                Base64.NO_WRAP
        );
        String metadataBase64 = Base64.encodeToString(
                result.metadata.toString().getBytes(StandardCharsets.UTF_8),
                Base64.NO_WRAP
        );
        System.out.println("U2CLI_SNAPSHOT_METADATA_BASE64:" + metadataBase64);
        int chunkCount = Math.max(1, (xmlBase64.length() + CHUNK_SIZE - 1) / CHUNK_SIZE);
        for (int i = 0; i < chunkCount; i++) {
            int start = i * CHUNK_SIZE;
            int end = Math.min(xmlBase64.length(), start + CHUNK_SIZE);
            System.out.println(
                    "U2CLI_SNAPSHOT_XML_CHUNK:"
                            + i + "/" + chunkCount + ":"
                            + xmlBase64.substring(start, end)
            );
        }
        System.out.println("U2CLI_SNAPSHOT_DONE");
    }

    private static byte[] readAll(File file) throws Exception {
        FileInputStream input = new FileInputStream(file);
        try {
            byte[] buffer = new byte[(int) file.length()];
            int offset = 0;
            while (offset < buffer.length) {
                int read = input.read(buffer, offset, buffer.length - offset);
                if (read < 0) {
                    break;
                }
                offset += read;
            }
            if (offset == buffer.length) {
                return buffer;
            }
            byte[] trimmed = new byte[offset];
            System.arraycopy(buffer, 0, trimmed, 0, offset);
            return trimmed;
        } finally {
            input.close();
        }
    }

    private static void attribute(XmlSerializer serializer, String name, String value) throws Exception {
        serializer.attribute("", name, value);
    }

    private static String safe(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static String bool(boolean value) {
        return value ? "true" : "false";
    }

    private static String boundsToString(Rect bounds) {
        return String.format(
                Locale.US,
                "[%d,%d][%d,%d]",
                bounds.left,
                bounds.top,
                bounds.right,
                bounds.bottom
        );
    }

    private static final class CaptureConfig {
        final int waitForIdleTimeoutMs;
        final int timeoutMs;
        final int maxDepth;
        final int maxNodes;

        CaptureConfig(int waitForIdleTimeoutMs, int timeoutMs, int maxDepth, int maxNodes) {
            this.waitForIdleTimeoutMs = waitForIdleTimeoutMs;
            this.timeoutMs = timeoutMs;
            this.maxDepth = maxDepth;
            this.maxNodes = maxNodes;
        }

        static CaptureConfig from(Bundle params) {
            return new CaptureConfig(
                    readInt(params, "waitForIdleTimeoutMs", DEFAULT_WAIT_FOR_IDLE_TIMEOUT_MS),
                    readInt(params, "timeoutMs", DEFAULT_CAPTURE_TIMEOUT_MS),
                    readInt(params, "maxDepth", DEFAULT_MAX_DEPTH),
                    readInt(params, "maxNodes", DEFAULT_MAX_NODES)
            );
        }

        private static int readInt(Bundle params, String key, int fallback) {
            if (params == null) {
                return fallback;
            }
            String value = params.getString(key);
            if (value == null) {
                return fallback;
            }
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
    }

    private static final class CaptureResult {
        String xml = "<hierarchy/>";
        final JSONObject metadata = new JSONObject();
    }

    private static final class NodeStats {
        final int maxDepth;
        final int maxNodes;
        int nodeCount;
        int childFetchErrors;
        boolean truncated;

        NodeStats(int maxDepth, int maxNodes) {
            this.maxDepth = maxDepth;
            this.maxNodes = maxNodes;
        }
    }

    private static final class RootRef {
        final AccessibilityNodeInfo node;
        final AccessibilityWindowInfo window;

        RootRef(AccessibilityNodeInfo node, AccessibilityWindowInfo window) {
            this.node = node;
            this.window = window;
        }
    }
}

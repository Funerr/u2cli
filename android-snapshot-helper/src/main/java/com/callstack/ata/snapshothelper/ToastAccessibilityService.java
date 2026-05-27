package com.callstack.ata.snapshothelper;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;

public final class ToastAccessibilityService extends AccessibilityService {
  private ToastHistoryStore store;

  @Override
  public void onCreate() {
    super.onCreate();
    store = new ToastHistoryStore(this);
  }

  @Override
  public void onAccessibilityEvent(AccessibilityEvent event) {
    if (event == null || event.getEventType() != AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED) {
      return;
    }
    CharSequence text = joinEventText(event);
    if (text == null || text.toString().trim().isEmpty()) {
      return;
    }
    ensureStore().record(text, event.getPackageName(), System.currentTimeMillis());
  }

  @Override
  public void onInterrupt() {}

  private ToastHistoryStore ensureStore() {
    if (store == null) {
      store = new ToastHistoryStore(this);
    }
    return store;
  }

  private static CharSequence joinEventText(AccessibilityEvent event) {
    if (!event.getText().isEmpty()) {
      StringBuilder joined = new StringBuilder();
      for (CharSequence item : event.getText()) {
        if (item == null) {
          continue;
        }
        String part = item.toString().trim();
        if (part.isEmpty()) {
          continue;
        }
        if (joined.length() > 0) {
          joined.append('\n');
        }
        joined.append(part);
      }
      if (joined.length() > 0) {
        return joined.toString();
      }
    }
    return event.getContentDescription();
  }
}

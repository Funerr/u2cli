package com.callstack.ata.snapshothelper;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

final class ToastHistoryStore {
  static final int MAX_HISTORY_SIZE = 20;
  private static final String PREFS_NAME = "ata_toast_history";
  private static final String KEY_NEXT_ID = "next_id";
  private static final String KEY_HISTORY = "history";
  private static final String KEY_LAST_CONSUMED_ID = "last_consumed_id";
  private static final String FIELD_SEPARATOR = "\t";
  private static final long DUPLICATE_WINDOW_MS = 250;

  private final SharedPreferences prefs;

  ToastHistoryStore(Context context) {
    prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
  }

  synchronized Snapshot consumeLatest() {
    List<Observation> observations = readObservations();
    long lastConsumedId = prefs.getLong(KEY_LAST_CONSUMED_ID, 0);
    Observation latest = latestUnconsumed(observations, lastConsumedId);
    if (latest != null) {
      prefs.edit().putLong(KEY_LAST_CONSUMED_ID, latest.id).commit();
    }
    return new Snapshot(observations, latest);
  }

  synchronized void clear() {
    prefs
        .edit()
        .remove(KEY_HISTORY)
        .putLong(KEY_LAST_CONSUMED_ID, prefs.getLong(KEY_NEXT_ID, 1) - 1)
        .commit();
  }

  synchronized Observation record(CharSequence text, CharSequence packageName, long capturedAtMs) {
    String normalizedText = text == null ? "" : text.toString().trim();
    if (normalizedText.isEmpty()) {
      return null;
    }
    String normalizedPackage = packageName == null ? "" : packageName.toString().trim();
    List<Observation> observations = readObservations();
    Observation latest = observations.isEmpty() ? null : observations.get(observations.size() - 1);
    if (
        latest != null
            && latest.text.equals(normalizedText)
            && latest.packageName.equals(normalizedPackage)
            && Math.abs(capturedAtMs - latest.capturedAtMs) <= DUPLICATE_WINDOW_MS) {
      return latest;
    }
    long id = prefs.getLong(KEY_NEXT_ID, 1);
    Observation observation = new Observation(id, normalizedText, normalizedPackage, capturedAtMs);
    observations.add(observation);
    while (observations.size() > MAX_HISTORY_SIZE) {
      observations.remove(0);
    }
    prefs
        .edit()
        .putLong(KEY_NEXT_ID, id + 1)
        .putString(KEY_HISTORY, encodeObservations(observations))
        .commit();
    return observation;
  }

  private static Observation latestUnconsumed(List<Observation> observations, long lastConsumedId) {
    for (int index = observations.size() - 1; index >= 0; index -= 1) {
      Observation observation = observations.get(index);
      if (observation.id > lastConsumedId) {
        return observation;
      }
    }
    return null;
  }

  private List<Observation> readObservations() {
    String encoded = prefs.getString(KEY_HISTORY, "");
    List<Observation> observations = new ArrayList<>();
    if (encoded == null || encoded.isEmpty()) {
      return observations;
    }
    String[] lines = encoded.split("\n");
    for (String line : lines) {
      if (line.isEmpty()) {
        continue;
      }
      Observation observation = decodeObservation(line);
      if (observation != null) {
        observations.add(observation);
      }
    }
    return observations;
  }

  private static String encodeObservations(List<Observation> observations) {
    StringBuilder encoded = new StringBuilder();
    for (Observation observation : observations) {
      if (encoded.length() > 0) {
        encoded.append('\n');
      }
      encoded.append(observation.id);
      encoded.append(FIELD_SEPARATOR);
      encoded.append(observation.capturedAtMs);
      encoded.append(FIELD_SEPARATOR);
      encoded.append(encodeString(observation.packageName));
      encoded.append(FIELD_SEPARATOR);
      encoded.append(encodeString(observation.text));
    }
    return encoded.toString();
  }

  private static Observation decodeObservation(String line) {
    String[] fields = line.split(FIELD_SEPARATOR, -1);
    if (fields.length != 4) {
      return null;
    }
    try {
      long id = Long.parseLong(fields[0]);
      long capturedAtMs = Long.parseLong(fields[1]);
      return new Observation(id, decodeString(fields[3]), decodeString(fields[2]), capturedAtMs);
    } catch (IllegalArgumentException error) {
      return null;
    }
  }

  private static String encodeString(String value) {
    return Base64.encodeToString(value.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
  }

  private static String decodeString(String value) {
    return new String(Base64.decode(value, Base64.DEFAULT), StandardCharsets.UTF_8);
  }

  static final class Snapshot {
    final List<Observation> observations;
    final Observation latest;

    Snapshot(List<Observation> observations, Observation latest) {
      this.observations = observations;
      this.latest = latest;
    }

    int size() {
      return observations.size();
    }
  }

  static final class Observation {
    final long id;
    final String text;
    final String packageName;
    final long capturedAtMs;

    Observation(long id, String text, String packageName, long capturedAtMs) {
      this.id = id;
      this.text = text;
      this.packageName = packageName;
      this.capturedAtMs = capturedAtMs;
    }
  }
}

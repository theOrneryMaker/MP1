package com.theornerymaker.mp1;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * New firmware on GitHub: about once a day (with internet), Android runs this; if the newest Ember release is newer
 * than the one built into the app and than any already told about, it posts a notification. Tapping it opens the app,
 * whose update card offers the release. Releases: theOrneryMaker/MP1, tag ember-NN.N, with an MP1_Ember_update_*.zip.
 */
public class UpdateCheck extends JobService {
    static final String RELEASES = "https://api.github.com/repos/theOrneryMaker/MP1/releases?per_page=30";
    static final int JOB = 1;
    static final long DAY = 24L * 60 * 60 * 1000;
    static final int MAX_BYTES = 20 * 1024 * 1024;

    /** A web address's bytes (redirects followed: release files live on another server) */
    static byte[] get(String url) throws Exception {
        for (int hop = 0; hop < 5; hop++) {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(20000);
            c.setReadTimeout(30000);
            c.setInstanceFollowRedirects(false);
            c.setRequestProperty("User-Agent", "MP1-phone-app");
            if (url.contains("api.github.com")) c.setRequestProperty("Accept", "application/vnd.github+json");
            int code = c.getResponseCode();
            if (code >= 300 && code < 400 && c.getHeaderField("Location") != null) {
                url = new URL(new URL(url), c.getHeaderField("Location")).toString();
                c.disconnect();
                continue;
            }
            if (code != 200) {
                c.disconnect();
                throw new Exception(code == 403 ? "GitHub says to wait a while (too many checks)" : "GitHub answered " + code);
            }
            try (InputStream in = c.getInputStream()) {
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] buf = new byte[65536];
                for (int n; (n = in.read(buf)) > 0; ) {
                    b.write(buf, 0, n);
                    if (b.size() > MAX_BYTES) throw new Exception("the file is too big");
                }
                return b.toByteArray();
            } finally {
                c.disconnect();
            }
        }
        throw new Exception("too many redirects");
    }

    /** "01.4" from "ember-01.4" ("" if it isn't an Ember release tag) */
    static String version(String tag) {
        return tag != null && tag.matches("ember-\\d+(\\.\\d+)*") ? tag.substring(6) : "";
    }

    /** a < b: -1, same: 0, a > b: 1 ("" is the oldest) */
    static int compare(String a, String b) {
        String[] x = a.isEmpty() ? new String[0] : a.split("\\."), y = b.isEmpty() ? new String[0] : b.split("\\.");
        for (int i = 0; i < Math.max(x.length, y.length); i++) {
            int p = i < x.length ? Integer.parseInt(x[i]) : -1, q = i < y.length ? Integer.parseInt(y[i]) : -1;
            if (p != q) return p < q ? -1 : 1;
        }
        return 0;
    }

    /** The newest full (not test) Ember release with an update package: its version, or "" */
    static String newest() throws Exception {
        JSONArray list = new JSONArray(new String(get(RELEASES), "UTF-8"));
        String best = "";
        for (int i = 0; i < list.length(); i++) {
            JSONObject r = list.getJSONObject(i);
            if (r.optBoolean("draft") || r.optBoolean("prerelease")) continue;
            String v = version(r.optString("tag_name"));
            if (v.isEmpty()) continue;
            JSONArray assets = r.optJSONArray("assets");
            boolean pkg = false;
            for (int n = 0; assets != null && n < assets.length(); n++)
                if (assets.getJSONObject(n).optString("name").matches("MP1_Ember_update_.*\\.zip")) pkg = true;
            if (pkg && compare(v, best) > 0) best = v;
        }
        return best;
    }

    /** The release built into this app (assets/firmware/version.txt, written by build.sh) */
    static String builtIn(Context c) {
        try (InputStream in = c.getAssets().open("firmware/version.txt")) {
            byte[] b = new byte[64];
            int n = in.read(b);
            return n > 0 ? new String(b, 0, n, "UTF-8").trim() : "";
        } catch (Exception e) {
            return "";
        }
    }

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("updates", MODE_PRIVATE); }

    static void markSeen(Context c, String v) {
        if (compare(v, prefs(c).getString("seen", "")) > 0) prefs(c).edit().putString("seen", v).apply();
    }

    static void schedule(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null || js.getPendingJob(JOB) != null) return;
        js.schedule(new JobInfo.Builder(JOB, new ComponentName(c, UpdateCheck.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(DAY)
                .setPersisted(true)
                .build());
    }

    static void notifyNew(Context c, String v) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        nm.createNotificationChannel(new NotificationChannel("firmware", "New firmware", NotificationManager.IMPORTANCE_DEFAULT));
        Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent tap = PendingIntent.getActivity(c, 0, open, PendingIntent.FLAG_IMMUTABLE);
        nm.notify(1, new Notification.Builder(c, "firmware")
                .setSmallIcon(R.drawable.ic_keys)
                .setContentTitle("MP1 Ember " + v + " is out")
                .setContentText("Open MP1 to update your pad.")
                .setContentIntent(tap)
                .setAutoCancel(true)
                .build());
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                String v = newest(), told = prefs(this).getString("seen", ""), mine = builtIn(this);
                if (!v.isEmpty() && compare(v, told) > 0 && compare(v, mine) > 0) {
                    notifyNew(this, v);
                    markSeen(this, v);
                }
            } catch (Exception e) {
                // no internet / GitHub busy: try again next time
            }
            jobFinished(params, false);
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) { return true; }
}

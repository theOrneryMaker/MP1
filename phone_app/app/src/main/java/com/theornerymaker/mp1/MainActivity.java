package com.theornerymaker.mp1;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.hoho.android.usbserial.driver.CdcAcmSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.util.SerialInputOutputManager;

import org.json.JSONArray;
import org.json.JSONObject;

import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * MP1 app: the MP1 Ember page in a WebView, with USB serial underneath. The page comes from the website (so it's
 * always the newest, without a new app); when that can't be reached (no internet, the site down) the copy built into
 * the app is used instead (assets/mp1_ember.html, built from MP1 EMBER/EMBER_01/app/ember.html).
 * Only those two places are shown in the app (they get the bridge below); any other link opens in the browser.
 * The page talks to window.MP1Android (Bridge below); its MP1Serial stand-in turns that into the
 * same port objects Web Serial gives, so the page code is the same in Chrome and here.
 */
public class MainActivity extends Activity {
    static final String ACTION_PERM = "com.theornerymaker.mp1.USB_PERMISSION";
    static final int[] VENDORS = {0x2E8A, 0x239A};          // Raspberry Pi, Adafruit
    static final int PICK_FILE = 1;
    static final String SITE = "https://theornerymaker.github.io/MP_Series_Macropad/ember/";
    static final String SITE_PAGE = SITE + "mp1_ember.html";
    static final String BUILT_IN = "file:///android_asset/mp1_ember.html";
    static final int SITE_WAIT_MS = 12000;              // the website this slow: the built-in copy instead
    static final int PAGE_LEVEL = 1;                    // the page must say <meta name="mp1-app" content="1"> (or more):
                                                        // it works with this app's bridge (an older one doesn't)

    boolean builtIn = false;                            // showing the built-in copy (the website couldn't be reached)
    final Handler ui = new Handler(Looper.getMainLooper());
    final Runnable siteTooSlow = () -> useBuiltIn("too slow");

    WebView web;
    UsbManager usb;
    ValueCallback<Uri[]> fileCallback;
    final Map<String, OpenPort> open = new HashMap<>();             // "deviceName#index" -> open port
    final Map<String, UsbDeviceConnection> conns = new HashMap<>(); // deviceName -> its connection (shared by its ports)

    static class OpenPort {
        UsbSerialPort port;
        SerialInputOutputManager io;
        String device;
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        catchCrashes();
        usb = (UsbManager) getSystemService(Context.USB_SERVICE);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        web.addJavascriptInterface(new Bridge(), "MP1Android");
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = cb;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try { startActivityForResult(Intent.createChooser(pick, "Choose a file"), PICK_FILE); }
                catch (Exception e) { fileCallback = null; return false; }
                return true;
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                String url = req.getUrl().toString();
                if (trusted(url)) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, req.getUrl())); } catch (Exception e) { /* nothing opens it */ }
                return true;
            }
            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) useBuiltIn(String.valueOf(err.getDescription()));
            }
            @Override
            public void onReceivedHttpError(WebView v, WebResourceRequest req, WebResourceResponse r) {
                if (req.isForMainFrame() && r.getStatusCode() >= 400) useBuiltIn("HTTP " + r.getStatusCode());
            }
            @Override
            public void onPageFinished(WebView v, String url) {
                if (!url.startsWith(SITE)) return;
                ui.removeCallbacks(siteTooSlow);
                v.evaluateJavascript("(function(){var m=document.querySelector('meta[name=mp1-app]');return m?m.content:'0';})()", level -> {
                    int n = 0;
                    try { n = Integer.parseInt(level.replace("\"", "").trim()); } catch (Exception e) { /* not a number */ }
                    if (n < PAGE_LEVEL) useBuiltIn("the website's page is older than this app");
                });
            }
        });
        // Android 15 draws apps under the status and navigation bars: keep the page clear of them
        // (a WebView ignores its own padding: it sits in a frame that's padded instead)
        android.widget.FrameLayout frame = new android.widget.FrameLayout(this);
        frame.setBackgroundColor(0xFF15100D);
        web.setBackgroundColor(0xFF15100D);
        frame.addView(web, new android.widget.FrameLayout.LayoutParams(-1, -1));
        if (Build.VERSION.SDK_INT >= 30) frame.setOnApplyWindowInsetsListener((v, insets) -> {
            android.graphics.Insets b = insets.getInsets(android.view.WindowInsets.Type.systemBars() | android.view.WindowInsets.Type.displayCutout());
            v.setPadding(b.left, b.top, b.right, b.bottom);
            return android.view.WindowInsets.CONSUMED;
        });
        setContentView(frame);

        IntentFilter f = new IntentFilter(ACTION_PERM);
        f.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        f.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(usbEvents, f, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(usbEvents, f);

        web.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        ui.postDelayed(siteTooSlow, SITE_WAIT_MS);
        web.loadUrl(SITE_PAGE);

        // new firmware on GitHub: checked about once a day in the background, told as an Android notification
        // (never allowed to stop the app opening: without it there's just no daily check)
        try {
            UpdateCheck.schedule(this);
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
                requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 2);
        } catch (Exception e) {
            android.util.Log.w("MP1", "no daily firmware check: " + e);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {             // the macropad plugged in while the app is open
        super.onNewIntent(intent);
        if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) js("MP1Serial._attached()");
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_FILE || fileCallback == null) return;
        Uri[] picked = null;
        if (result == RESULT_OK && data != null) {
            if (data.getClipData() != null) {                   // several files
                picked = new Uri[data.getClipData().getItemCount()];
                for (int n = 0; n < picked.length; n++) picked[n] = data.getClipData().getItemAt(n).getUri();
            } else if (data.getData() != null) picked = new Uri[]{data.getData()};
        }
        fileCallback.onReceiveValue(picked);
        fileCallback = null;
    }

    @Override
    protected void onDestroy() {
        try { unregisterReceiver(usbEvents); } catch (Exception e) { /* not registered */ }
        for (String key : open.keySet().toArray(new String[0])) closePort(key);
        super.onDestroy();
    }

    final BroadcastReceiver usbEvents = new BroadcastReceiver() {
        @Override
        public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if (ACTION_PERM.equals(a)) {
                js("MP1Serial._perm(" + i.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false) + ")");
            } else if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(a)) {
                js("MP1Serial._attached()");
            } else if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(a)) {
                UsbDevice d = i.getParcelableExtra(UsbManager.EXTRA_DEVICE);
                if (d == null) return;
                for (String key : open.keySet().toArray(new String[0]))
                    if (key.startsWith(d.getDeviceName() + "#")) { closePort(key); js("MP1Serial._gone('" + key + "')"); }
            }
        }
    };

    /** A crash: what went wrong goes into Downloads/MP1_crash.txt (to send in), then Android closes the app as usual */
    void catchCrashes() {
        Thread.UncaughtExceptionHandler android = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
            try {
                java.io.StringWriter w = new java.io.StringWriter();
                e.printStackTrace(new java.io.PrintWriter(w));
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.DISPLAY_NAME, "MP1_crash.txt");
                v.put(MediaStore.Downloads.MIME_TYPE, "text/plain");
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri != null) try (OutputStream out = getContentResolver().openOutputStream(uri)) {
                    out.write(("MP1 app " + Build.MODEL + " Android " + Build.VERSION.RELEASE + "\n" + w).getBytes("UTF-8"));
                }
            } catch (Throwable ignored) { /* nothing more to do */ }
            if (android != null) android.uncaughtException(t, e);
        });
    }

    /** The two places the app shows (and lets use the bridge): the website's Ember folder and its own copy */
    static boolean trusted(String url) {
        return url.startsWith(SITE) || url.equals(BUILT_IN) || url.startsWith(BUILT_IN + "#") || url.startsWith(BUILT_IN + "?");
    }

    /** The website couldn't be reached: the page built into the app (once; the next start tries the website again) */
    void useBuiltIn(String why) {
        runOnUiThread(() -> {
            ui.removeCallbacks(siteTooSlow);
            if (builtIn) return;
            builtIn = true;
            android.util.Log.i("MP1", "website page not used (" + why + "): the built-in copy");
            web.stopLoading();
            web.loadUrl(BUILT_IN);
        });
    }

    static String safeName(String n) { return n.replaceAll("[^A-Za-z0-9._-]", "_"); }

    void js(String code) {
        runOnUiThread(() -> web.evaluateJavascript(code, null));
    }

    static boolean ours(UsbDevice d) {
        for (int v : VENDORS) if (d.getVendorId() == v) return true;
        return false;
    }

    /** The RP2040's own update drive (RPI-RP2: the boot ROM, so it's always there to fall back on) */
    static boolean isBootDrive(UsbDevice d) {
        return d.getVendorId() == 0x2E8A && d.getProductId() == 0x0003;
    }

    UsbDevice bootDrive() {
        for (UsbDevice d : usb.getDeviceList().values()) if (isBootDrive(d)) return d;
        return null;
    }

    // ─── writing a UF2 to RPI-RP2: USB mass storage (bulk-only), SCSI WRITE(10) of 512-byte
    // blocks. The boot ROM takes every UF2 block written anywhere on its drive (no file system
    // needed) and restarts the chip once it has them all. ───
    UsbDeviceConnection mscConn;
    UsbInterface mscIf;
    UsbEndpoint mscIn, mscOut;
    int mscTag = 1;

    synchronized String mscOpen() {
        mscClose();
        UsbDevice d = bootDrive();
        if (d == null) return "The macropad isn't in update mode (no RPI-RP2 drive).";
        if (!usb.hasPermission(d)) return "Not allowed to use the RPI-RP2 drive.";
        for (int n = 0; n < d.getInterfaceCount(); n++) {
            UsbInterface i = d.getInterface(n);
            if (i.getInterfaceClass() != UsbConstants.USB_CLASS_MASS_STORAGE) continue;
            for (int e = 0; e < i.getEndpointCount(); e++) {
                UsbEndpoint ep = i.getEndpoint(e);
                if (ep.getType() != UsbConstants.USB_ENDPOINT_XFER_BULK) continue;
                if (ep.getDirection() == UsbConstants.USB_DIR_IN) mscIn = ep; else mscOut = ep;
            }
            mscIf = i;
            break;
        }
        if (mscIf == null || mscIn == null || mscOut == null) return "The RPI-RP2 drive has no storage interface.";
        mscConn = usb.openDevice(d);
        if (mscConn == null) return "Couldn't open the RPI-RP2 drive.";
        if (!mscConn.claimInterface(mscIf, true)) { mscClose(); return "Couldn't claim the RPI-RP2 drive."; }
        return "";
    }

    synchronized void mscClose() {
        if (mscConn != null) {
            try { if (mscIf != null) mscConn.releaseInterface(mscIf); } catch (Exception e) { /* gone */ }
            try { mscConn.close(); } catch (Exception e) { /* gone */ }
        }
        mscConn = null; mscIf = null; mscIn = mscOut = null;
    }

    /** One SCSI WRITE(10): data (a whole number of 512-byte blocks) at block lba. "" = done. */
    synchronized String mscWrite(long lba, byte[] data) {
        if (mscConn == null) return "The RPI-RP2 drive isn't open.";
        int blocks = data.length / 512;
        ByteBuffer cbw = ByteBuffer.allocate(31).order(ByteOrder.LITTLE_ENDIAN);
        int tag = mscTag++;
        cbw.putInt(0x43425355).putInt(tag).putInt(data.length).put((byte) 0x00).put((byte) 0).put((byte) 10);
        cbw.put((byte) 0x2A).put((byte) 0);
        cbw.put((byte) (lba >> 24)).put((byte) (lba >> 16)).put((byte) (lba >> 8)).put((byte) lba);
        cbw.put((byte) 0).put((byte) (blocks >> 8)).put((byte) blocks).put((byte) 0);
        if (mscConn.bulkTransfer(mscOut, cbw.array(), 31, 5000) != 31) return "The drive didn't take the write command.";
        for (int off = 0; off < data.length; ) {
            int n = Math.min(16384, data.length - off);
            int got = mscConn.bulkTransfer(mscOut, data, off, n, 10000);
            if (got <= 0) return "The drive stopped taking data.";
            off += got;
        }
        byte[] csw = new byte[13];
        int got = mscConn.bulkTransfer(mscIn, csw, 13, 10000);
        if (got != 13) return "The drive didn't confirm the write.";
        ByteBuffer c = ByteBuffer.wrap(csw).order(ByteOrder.LITTLE_ENDIAN);
        if (c.getInt(0) != 0x53425355 || c.getInt(4) != tag) return "The drive's answer was garbled.";
        if (csw[12] != 0) return "The drive refused the write (status " + csw[12] + ").";
        return "";
    }

    UsbDevice find(String name) {
        for (UsbDevice d : usb.getDeviceList().values()) if (d.getDeviceName().equals(name)) return d;
        return null;
    }

    synchronized void closePort(String key) {
        OpenPort o = open.remove(key);
        if (o == null) return;
        try { if (o.io != null) o.io.stop(); } catch (Exception e) { /* stopping */ }
        try { o.port.close(); } catch (Exception e) { /* gone */ }
        boolean shared = false;
        for (OpenPort other : open.values()) if (other.device.equals(o.device)) shared = true;
        if (!shared) {
            UsbDeviceConnection c = conns.remove(o.device);
            if (c != null) try { c.close(); } catch (Exception e) { /* gone */ }
        }
    }

    /** What the page can call (window.MP1Android). Runs on WebView's bridge thread. */
    class Bridge {
        @JavascriptInterface
        public String version() {
            try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionName; }
            catch (Exception e) { return "?"; }
        }

        /** Every serial port of every macropad plugged in: [{key, vid, pid, perm, index, name}] */
        @JavascriptInterface
        public String ports() {
            JSONArray out = new JSONArray();
            for (UsbDevice d : usb.getDeviceList().values()) {
                if (!ours(d) || isBootDrive(d)) continue;
                try {
                    List<UsbSerialPort> ports = new CdcAcmSerialDriver(d).getPorts();
                    for (int n = 0; n < ports.size(); n++) {
                        JSONObject p = new JSONObject();
                        p.put("key", d.getDeviceName() + "#" + n);
                        p.put("vid", d.getVendorId());
                        p.put("pid", d.getProductId());
                        p.put("perm", usb.hasPermission(d));
                        p.put("index", n);
                        p.put("name", d.getProductName() == null ? "" : d.getProductName());
                        out.put(p);
                    }
                } catch (Exception e) { /* not a serial device after all */ }
            }
            return out.toString();
        }

        /** "none": no macropad plugged in; "ok": all allowed already; "asked": Android shows its question */
        @JavascriptInterface
        public String askPermission() {
            UsbDevice ask = null;
            boolean any = false;
            for (UsbDevice d : usb.getDeviceList().values()) {
                if (!ours(d) || isBootDrive(d)) continue;
                any = true;
                if (!usb.hasPermission(d)) { ask = d; break; }
            }
            if (!any) return "none";
            if (ask == null) return "ok";
            Intent i = new Intent(ACTION_PERM).setPackage(getPackageName());
            int flags = Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0;
            usb.requestPermission(ask, PendingIntent.getBroadcast(MainActivity.this, 0, i, flags));
            return "asked";
        }

        @JavascriptInterface
        public boolean open(String key) {
            synchronized (MainActivity.this) {
                if (open.containsKey(key)) return true;
                int hash = key.lastIndexOf('#');
                String name = key.substring(0, hash);
                UsbDevice d = find(name);
                if (d == null || !usb.hasPermission(d)) return false;
                try {
                    UsbDeviceConnection c = conns.get(name);
                    if (c == null) { c = usb.openDevice(d); if (c == null) return false; conns.put(name, c); }
                    UsbSerialPort p = new CdcAcmSerialDriver(d).getPorts().get(Integer.parseInt(key.substring(hash + 1)));
                    p.open(c);
                    p.setParameters(115200, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE);
                    OpenPort o = new OpenPort();
                    o.port = p;
                    o.device = name;
                    o.io = new SerialInputOutputManager(p, new SerialInputOutputManager.Listener() {
                        @Override
                        public void onNewData(byte[] data) {
                            js("MP1Serial._data('" + key + "','" + Base64.encodeToString(data, Base64.NO_WRAP) + "')");
                        }
                        @Override
                        public void onRunError(Exception e) {
                            closePort(key);
                            js("MP1Serial._gone('" + key + "')");
                        }
                    });
                    open.put(key, o);
                    o.io.start();
                    return true;
                } catch (Exception e) {
                    closePort(key);
                    return false;
                }
            }
        }

        @JavascriptInterface
        public boolean write(String key, String b64) {
            OpenPort o = open.get(key);
            if (o == null) return false;
            try { o.port.write(Base64.decode(b64, Base64.DEFAULT), 3000); return true; }
            catch (Exception e) { return false; }
        }

        @JavascriptInterface
        public void setDtr(String key, boolean on) {
            OpenPort o = open.get(key);
            if (o != null) try { o.port.setDTR(on); } catch (Exception e) { /* not supported */ }
        }

        @JavascriptInterface
        public void close(String key) { closePort(key); }

        /** The update drive (RPI-RP2): "none", "noperm" or "ok" */
        @JavascriptInterface
        public String bootDrive() {
            UsbDevice d = MainActivity.this.bootDrive();
            return d == null ? "none" : usb.hasPermission(d) ? "ok" : "noperm";
        }

        /** Android's "allow" question for the update drive (answer: MP1Serial._perm) */
        @JavascriptInterface
        public String askBootPermission() {
            UsbDevice d = MainActivity.this.bootDrive();
            if (d == null) return "none";
            if (usb.hasPermission(d)) return "ok";
            Intent i = new Intent(ACTION_PERM).setPackage(getPackageName());
            int flags = Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0;
            usb.requestPermission(d, PendingIntent.getBroadcast(MainActivity.this, 1, i, flags));
            return "asked";
        }

        @JavascriptInterface
        public String uf2Open() { return mscOpen(); }

        @JavascriptInterface
        public String uf2Write(double lba, String b64) { return mscWrite((long) lba, Base64.decode(b64, Base64.DEFAULT)); }

        @JavascriptInterface
        public void uf2Close() { mscClose(); }

        /** The files in one of the app's own folders (assets/firmware: the built-in update packages) */
        @JavascriptInterface
        public String assets(String dir) {
            JSONArray out = new JSONArray();
            try { for (String n : getAssets().list(dir)) out.put(n); } catch (Exception e) { /* none */ }
            return out.toString();
        }

        /** One of the app's own files, base64 ("" if it isn't there) */
        @JavascriptInterface
        public String asset(String path) {
            try (InputStream in = getAssets().open(path)) {
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] buf = new byte[65536];
                for (int n; (n = in.read(buf)) > 0; ) b.write(buf, 0, n);
                return Base64.encodeToString(b.toByteArray(), Base64.NO_WRAP);
            } catch (Exception e) {
                return "";
            }
        }

        /** Text onto the phone's clipboard (a copied key or layer, to paste into Webex / email) */
        @JavascriptInterface
        public boolean copyText(String text) {
            try {
                runOnUiThread(() -> {
                    ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    cm.setPrimaryClip(ClipData.newPlainText("MP1", text));
                });
                return true;
            } catch (Exception e) {
                return false;
            }
        }

        /** Android's share sheet with this text (Webex, email, messages...) */
        @JavascriptInterface
        public void shareText(String subject, String text) {
            runOnUiThread(() -> {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/plain");
                send.putExtra(Intent.EXTRA_SUBJECT, subject);
                send.putExtra(Intent.EXTRA_TEXT, text);
                try { startActivity(Intent.createChooser(send, subject)); } catch (Exception e) { /* nothing to share with */ }
            });
        }

        /** Download url in the background (no browser limits). saveAs "": the answer comes back as base64 in
         *  MP1Net._done(id, "", b64); otherwise it's kept in the app's own folder (downloads/saveAs, read with saved())
         *  and MP1Net._done(id, "", ""). A failure: MP1Net._done(id, why, ""). */
        @JavascriptInterface
        public void fetch(String id, String url, String saveAs) {
            new Thread(() -> {
                String err = "", body = "";
                try {
                    byte[] b = UpdateCheck.get(url);
                    if (saveAs.isEmpty()) body = Base64.encodeToString(b, Base64.NO_WRAP);
                    else {
                        java.io.File dir = new java.io.File(getFilesDir(), "downloads");
                        dir.mkdirs();
                        java.io.File tmp = new java.io.File(dir, safeName(saveAs) + ".part");
                        try (OutputStream out = new java.io.FileOutputStream(tmp)) { out.write(b); }
                        if (!tmp.renameTo(new java.io.File(dir, safeName(saveAs)))) throw new Exception("couldn't keep the file");
                    }
                } catch (Exception e) {
                    err = String.valueOf(e.getMessage());
                }
                js("MP1Net._done(" + JSONObject.quote(id) + "," + JSONObject.quote(err) + ",'" + body + "')");
            }).start();
        }

        /** A file this app downloaded (downloads/name), base64; "" if it isn't there */
        @JavascriptInterface
        public String saved(String name) {
            java.io.File f = new java.io.File(new java.io.File(getFilesDir(), "downloads"), safeName(name));
            try (InputStream in = new java.io.FileInputStream(f)) {
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] buf = new byte[65536];
                for (int n; (n = in.read(buf)) > 0; ) b.write(buf, 0, n);
                return Base64.encodeToString(b.toByteArray(), Base64.NO_WRAP);
            } catch (Exception e) {
                return "";
            }
        }

        /** The newest release the background check has told about (so the page doesn't tell again) */
        @JavascriptInterface
        public void seen(String version) { UpdateCheck.markSeen(MainActivity.this, version); }

        /** A file into the phone's Downloads folder; "" when it worked, otherwise why not */
        @JavascriptInterface
        public String saveFile(String name, String b64, String mime) {
            try {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.DISPLAY_NAME, name);
                v.put(MediaStore.Downloads.MIME_TYPE, mime);
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri == null) return "Android didn't make the file";
                try (OutputStream out = getContentResolver().openOutputStream(uri)) {
                    out.write(Base64.decode(b64, Base64.DEFAULT));
                }
                return "";
            } catch (Exception e) {
                return String.valueOf(e.getMessage());
            }
        }
    }
}

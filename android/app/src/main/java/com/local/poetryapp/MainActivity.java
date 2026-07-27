package com.local.poetryapp;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ContentValues;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.graphics.Color;
import android.media.MediaPlayer;
import android.net.Uri;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.view.Window;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.os.Environment;
import android.provider.DocumentsContract;
import android.provider.MediaStore;

import androidx.webkit.WebViewAssetLoader;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity {
    private static final int REQUEST_EXPORT_JSON = 41;
    private static final int REQUEST_IMPORT_JSON = 42;
    private WebView webView;
    private String pendingExportText = "";
    private MediaPlayer mediaPlayer;
    private double nativeSpeed = 1.0;
    private final Handler mediaHandler = new Handler(Looper.getMainLooper());
    private final Runnable mediaProgressRunnable = new Runnable() {
        @Override
        public void run() {
            if (mediaPlayer != null && webView != null) {
                try {
                    int current = mediaPlayer.getCurrentPosition();
                    int duration = mediaPlayer.getDuration();
                    boolean playing = mediaPlayer.isPlaying();
                    webView.post(() -> webView.evaluateJavascript(
                        "window.nativeAudioState && window.nativeAudioState(" + current + "," + duration + "," + playing + ")",
                        null
                    ));
                } catch (Exception ignored) {
                }
                mediaHandler.postDelayed(this, 400);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.setStatusBarColor(Color.parseColor("#153d3a"));
        window.setNavigationBarColor(Color.parseColor("#20292a"));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(true);
        }

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowFileAccessFromFileURLs(true);
        settings.setAllowUniversalAccessFromFileURLs(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        webView.addJavascriptInterface(new AppBridge(), "AndroidBridge");

        WebViewAssetLoader assetLoader = new WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
            .build();

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return assetLoader.shouldInterceptRequest(request.getUrl());
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
                return assetLoader.shouldInterceptRequest(Uri.parse(url));
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton(android.R.string.ok, (dialog, which) -> result.confirm())
                    .setOnCancelListener(dialog -> result.cancel())
                    .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton(android.R.string.ok, (dialog, which) -> result.confirm())
                    .setNegativeButton(android.R.string.cancel, (dialog, which) -> result.cancel())
                    .setOnCancelListener(dialog -> result.cancel())
                    .show();
                return true;
            }
        });
        webView.loadUrl("https://appassets.androidplatform.net/assets/index.html");
    }

    public class AppBridge {
        @JavascriptInterface
        public int loadAudio(String assetPath, double speed) {
            releaseNativeAudio();
            try {
                mediaPlayer = new MediaPlayer();
                File downloaded = availableDownloadedAudioFile(assetPath);
                if (downloaded.exists() && downloaded.length() > 64000) {
                    mediaPlayer.setDataSource(downloaded.getAbsolutePath());
                } else {
                    AssetFileDescriptor descriptor = getAssets().openFd(assetPath);
                    mediaPlayer.setDataSource(descriptor.getFileDescriptor(), descriptor.getStartOffset(), descriptor.getLength());
                    descriptor.close();
                }
                mediaPlayer.prepare();
                nativeSpeed = speed;
                mediaPlayer.setOnCompletionListener(player -> webView.post(() -> webView.evaluateJavascript(
                    "window.nativeAudioEnded && window.nativeAudioEnded()",
                    null
                )));
                mediaHandler.post(mediaProgressRunnable);
                return mediaPlayer.getDuration();
            } catch (Exception error) {
                releaseNativeAudio();
                return 0;
            }
        }

        @JavascriptInterface
        public boolean playAudio() {
            try {
                if (mediaPlayer == null) return false;
                applyNativeSpeed(nativeSpeed);
                mediaPlayer.start();
                return true;
            } catch (Exception error) {
                return false;
            }
        }

        @JavascriptInterface
        public void pauseAudio() {
            try {
                if (mediaPlayer != null && mediaPlayer.isPlaying()) mediaPlayer.pause();
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void seekAudio(int millis) {
            try {
                if (mediaPlayer != null) mediaPlayer.seekTo(Math.max(0, millis));
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void setAudioSpeed(double speed) {
            nativeSpeed = speed;
            if (mediaPlayer != null && mediaPlayer.isPlaying()) applyNativeSpeed(speed);
        }

        @JavascriptInterface
        public void releaseAudio() {
            releaseNativeAudio();
        }

        @JavascriptInterface
        public String readUserStore(String key) {
            try {
                File file = userStoreFile(key);
                if (!file.exists()) return "";
                try (InputStream input = new FileInputStream(file)) {
                    ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                    byte[] chunk = new byte[8192];
                    int read;
                    while ((read = input.read(chunk)) != -1) buffer.write(chunk, 0, read);
                    return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
                }
            } catch (Exception error) {
                return "";
            }
        }

        @JavascriptInterface
        public void writeUserStore(String key, String text) {
            try {
                File file = userStoreFile(key);
                File parent = file.getParentFile();
                if (parent != null) parent.mkdirs();
                try (FileOutputStream output = new FileOutputStream(file)) {
                    output.write((text == null ? "" : text).getBytes(StandardCharsets.UTF_8));
                }
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void downloadMissingAudio(String itemsJson) {
            new Thread(() -> {
                int downloaded = 0;
                int skipped = 0;
                int failed = 0;
                try {
                    JSONArray items = new JSONArray(itemsJson == null ? "[]" : itemsJson);
                    int total = items.length();
                    for (int i = 0; i < total; i++) {
                        JSONObject item = items.getJSONObject(i);
                        String collection = item.optString("collection");
                        String number = item.optString("number");
                        String assetPath = item.optString("path");
                        if (assetPath.isEmpty()) {
                            failed++;
                        } else if (audioAvailable(assetPath)) {
                            skipped++;
                        } else if (downloadAudioFile(collection, number, assetPath)) {
                            downloaded++;
                        } else {
                            failed++;
                        }
                        int done = i + 1;
                        int downloadedNow = downloaded;
                        int skippedNow = skipped;
                        int failedNow = failed;
                        webView.post(() -> webView.evaluateJavascript(
                            "window.nativeAudioDownloadProgress && window.nativeAudioDownloadProgress(" + done + "," + total + "," + downloadedNow + "," + skippedNow + "," + failedNow + ")",
                            null
                        ));
                    }
                } catch (Exception error) {
                    failed++;
                }
                int downloadedDone = downloaded;
                int skippedDone = skipped;
                int failedDone = failed;
                webView.post(() -> webView.evaluateJavascript(
                    "window.nativeAudioDownloadDone && window.nativeAudioDownloadDone(" + downloadedDone + "," + skippedDone + "," + failedDone + ")",
                    null
                ));
            }).start();
        }

        @JavascriptInterface
        public void deleteDownloadedAudio() {
            new Thread(() -> {
                int deleted = 0;
                boolean ok = true;
                try {
                    deleted += deleteTree(downloadedAudioRoot());
                    deleted += deleteTree(legacyDownloadedAudioRoot());
                } catch (Exception error) {
                    ok = false;
                }
                int deletedDone = deleted;
                boolean okDone = ok;
                webView.post(() -> webView.evaluateJavascript(
                    "window.nativeAudioDeleteDone && window.nativeAudioDeleteDone(" + deletedDone + "," + okDone + ")",
                    null
                ));
            }).start();
        }

        @JavascriptInterface
        public void saveImage(String assetPath, String fileName) {
            new Thread(() -> {
                boolean ok = saveAssetImageToDownloads(assetPath, fileName);
                runOnUiThread(() -> Toast.makeText(
                    MainActivity.this,
                    ok ? "\u5df2\u5132\u5b58\u5230 Download/Poetry_APP" : "\u5132\u5b58\u5716\u7247\u5931\u6557",
                    Toast.LENGTH_SHORT
                ).show());
            }).start();
        }

        @JavascriptInterface
        public void exportUserData(String text, String fileName) {
            String exportText = text == null ? "" : text;
            String exportFileName = fileName == null ? "" : fileName;
            new Thread(() -> {
                boolean ok = exportBackupToDownloads(exportText, exportFileName);
                runOnUiThread(() -> Toast.makeText(
                    MainActivity.this,
                    ok ? "已匯出到 Download/Poetry_APP" : "匯出失敗",
                    Toast.LENGTH_SHORT
                ).show());
            }).start();
        }

        @JavascriptInterface
        public void importUserData() {
            runOnUiThread(() -> {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] { "application/json", "text/plain", "*/*" });
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, defaultBackupFolderUri());
                }
                try {
                    startActivityForResult(intent, REQUEST_IMPORT_JSON);
                } catch (ActivityNotFoundException error) {
                    Toast.makeText(MainActivity.this, "無法開啟檔案選擇介面", Toast.LENGTH_SHORT).show();
                }
            });
        }
    }

    private void applyNativeSpeed(double speed) {
        try {
            if (mediaPlayer != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                mediaPlayer.setPlaybackParams(mediaPlayer.getPlaybackParams().setSpeed((float) speed));
            }
        } catch (Exception ignored) {
        }
    }

    private File userStoreFile(String key) {
        String safeKey = key == null ? "store" : key.replaceAll("[^A-Za-z0-9._-]", "_");
        return new File(new File(getFilesDir(), "user-data"), safeKey + ".json");
    }

    private File downloadedAudioRoot() {
        File root = getExternalFilesDir(Environment.DIRECTORY_MUSIC);
        if (root == null) root = getFilesDir();
        return new File(root, "Poetry_APP_Audio");
    }

    private File legacyDownloadedAudioRoot() {
        return new File(new File(getFilesDir(), "database"), "audio");
    }

    private File downloadedAudioFile(String assetPath) {
        return new File(downloadedAudioRoot(), assetPath);
    }

    private File legacyDownloadedAudioFile(String assetPath) {
        String prefix = "database/audio/";
        String relative = assetPath != null && assetPath.startsWith(prefix) ? assetPath.substring(prefix.length()) : assetPath;
        return new File(legacyDownloadedAudioRoot(), relative);
    }

    private File availableDownloadedAudioFile(String assetPath) {
        File downloaded = downloadedAudioFile(assetPath);
        if (downloaded.exists() && downloaded.length() > 64000) return downloaded;
        File legacy = legacyDownloadedAudioFile(assetPath);
        if (legacy.exists() && legacy.length() > 64000) {
            try {
                File parent = downloaded.getParentFile();
                if (parent != null) parent.mkdirs();
                copyFile(legacy, downloaded);
                return downloaded;
            } catch (Exception ignored) {
                return legacy;
            }
        }
        return downloaded;
    }

    private boolean audioAvailable(String assetPath) {
        File downloaded = availableDownloadedAudioFile(assetPath);
        if (downloaded.exists() && downloaded.length() > 64000) return true;
        try (AssetFileDescriptor descriptor = getAssets().openFd(assetPath)) {
            return descriptor.getLength() > 64000;
        } catch (Exception error) {
            return false;
        }
    }

    private void copyFile(File source, File target) throws Exception {
        try (InputStream input = new FileInputStream(source); OutputStream output = new FileOutputStream(target)) {
            byte[] chunk = new byte[8192];
            int read;
            while ((read = input.read(chunk)) != -1) output.write(chunk, 0, read);
        }
    }

    private int deleteTree(File file) {
        if (file == null || !file.exists()) return 0;
        int count = 0;
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) count += deleteTree(child);
            }
        }
        if (file.isFile() && file.getName().toLowerCase().endsWith(".mp3")) count++;
        file.delete();
        return count;
    }

    private Uri defaultBackupFolderUri() {
        return Uri.parse("content://com.android.externalstorage.documents/document/primary%3ADownload%2FPoetry_APP");
    }

    private boolean exportBackupToDownloads(String text, String requestedFileName) {
        try {
            String fileName = sanitizeFileName(requestedFileName);
            if (fileName.isEmpty()) fileName = "hymn-library-favorites.json";
            if (!fileName.toLowerCase().endsWith(".json")) fileName += ".json";
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ContentValues values = new ContentValues();
                values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
                values.put(MediaStore.MediaColumns.MIME_TYPE, "application/json");
                values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Poetry_APP");
                values.put(MediaStore.MediaColumns.IS_PENDING, 1);
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) return false;
                try (OutputStream output = getContentResolver().openOutputStream(uri)) {
                    if (output == null) return false;
                    output.write(text.getBytes(StandardCharsets.UTF_8));
                }
                values.clear();
                values.put(MediaStore.MediaColumns.IS_PENDING, 0);
                getContentResolver().update(uri, values, null, null);
                return true;
            }
            File folder = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Poetry_APP");
            if (!folder.exists() && !folder.mkdirs()) return false;
            File target = new File(folder, fileName);
            try (FileOutputStream output = new FileOutputStream(target)) {
                output.write(text.getBytes(StandardCharsets.UTF_8));
            }
            return true;
        } catch (Exception error) {
            return false;
        }
    }

    private boolean saveAssetImageToDownloads(String assetPath, String fileName) {
        try {
            String safeName = sanitizeFileName(fileName);
            if (safeName.isEmpty()) safeName = "poetry-page.jpg";
            if (!safeName.toLowerCase().endsWith(".jpg") && !safeName.toLowerCase().endsWith(".jpeg") && !safeName.toLowerCase().endsWith(".png")) {
                safeName += ".jpg";
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ContentValues values = new ContentValues();
                values.put(MediaStore.MediaColumns.DISPLAY_NAME, safeName);
                values.put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg");
                values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Poetry_APP");
                values.put(MediaStore.MediaColumns.IS_PENDING, 1);
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) return false;
                try (InputStream input = getAssets().open(assetPath); OutputStream output = getContentResolver().openOutputStream(uri)) {
                    if (output == null) return false;
                    byte[] chunk = new byte[8192];
                    int read;
                    while ((read = input.read(chunk)) != -1) output.write(chunk, 0, read);
                }
                values.clear();
                values.put(MediaStore.MediaColumns.IS_PENDING, 0);
                getContentResolver().update(uri, values, null, null);
                return true;
            }
            File folder = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Poetry_APP");
            if (!folder.exists() && !folder.mkdirs()) return false;
            try (InputStream input = getAssets().open(assetPath); OutputStream output = new FileOutputStream(new File(folder, safeName))) {
                byte[] chunk = new byte[8192];
                int read;
                while ((read = input.read(chunk)) != -1) output.write(chunk, 0, read);
            }
            return true;
        } catch (Exception error) {
            return false;
        }
    }

    private String sanitizeFileName(String fileName) {
        String value = fileName == null ? "" : fileName.trim();
        value = value.replaceAll("[\\\\/:*?\"<>|\\r\\n\\t]", "_");
        if (value.length() > 90) value = value.substring(0, 90);
        return value;
    }

    private boolean downloadAudioFile(String collection, String number, String assetPath) {
        if (!"hymns".equals(collection) && !"supplement".equals(collection)) return false;
        try {
            int sourceNumber;
            if (number.startsWith("附")) sourceNumber = 1000 + Integer.parseInt(number.substring(1));
            else sourceNumber = Integer.parseInt(number);
            String book = "hymns".equals(collection) ? "ch" : "ts";
            String pageUrl = "https://www.hymnal.net/en/hymn/" + book + "/" + sourceNumber;
            String page = readUrl(pageUrl);
            Pattern pattern = Pattern.compile("https://www\\.hymnal\\.net/Hymns/[^\\\"'<>\\s]+?\\.mp3");
            Matcher matcher = pattern.matcher(page);
            LinkedHashSet<String> urls = new LinkedHashSet<>();
            while (matcher.find()) urls.add(matcher.group());
            String best = "";
            int bestScore = -1;
            for (String url : urls) {
                int score = 0;
                if ("hymns".equals(collection) && url.contains("/Chinese/mp3/")) score += 100;
                if ("supplement".equals(collection) && url.contains("/ChineseTS/mp3/")) score += 100;
                if (url.contains("_vocal.mp3")) score += 50;
                if (url.contains("_full.mp3")) score += 35;
                if (url.contains("_i.mp3")) score += 25;
                if (score > bestScore) {
                    bestScore = score;
                    best = url;
                }
            }
            if (best.isEmpty()) return false;
            byte[] bytes = readBytes(best);
            if (bytes.length <= 64000) return false;
            File target = downloadedAudioFile(assetPath);
            File parent = target.getParentFile();
            if (parent != null) parent.mkdirs();
            try (FileOutputStream output = new FileOutputStream(target)) {
                output.write(bytes);
            }
            return true;
        } catch (Exception error) {
            return false;
        }
    }

    private String readUrl(String urlText) throws Exception {
        return new String(readBytes(urlText), StandardCharsets.UTF_8);
    }

    private byte[] readBytes(String urlText) throws Exception {
        java.net.URL url = new java.net.URL(urlText);
        java.net.URLConnection connection = url.openConnection();
        connection.setConnectTimeout(45000);
        connection.setReadTimeout(60000);
        connection.setRequestProperty("User-Agent", "Mozilla/5.0");
        try (InputStream input = connection.getInputStream()) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            while ((read = input.read(chunk)) != -1) buffer.write(chunk, 0, read);
            return buffer.toByteArray();
        }
    }

    private void releaseNativeAudio() {
        mediaHandler.removeCallbacks(mediaProgressRunnable);
        if (mediaPlayer != null) {
            try {
                mediaPlayer.release();
            } catch (Exception ignored) {
            }
            mediaPlayer = null;
        }
    }

    @Override
    protected void onDestroy() {
        releaseNativeAudio();
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (requestCode == REQUEST_EXPORT_JSON) {
            try (OutputStream output = getContentResolver().openOutputStream(uri)) {
                if (output != null) output.write(pendingExportText.getBytes(StandardCharsets.UTF_8));
                Toast.makeText(this, "匯出完成", Toast.LENGTH_SHORT).show();
            } catch (Exception error) {
                Toast.makeText(this, "匯出失敗", Toast.LENGTH_SHORT).show();
            }
        } else if (requestCode == REQUEST_IMPORT_JSON) {
            try (InputStream input = getContentResolver().openInputStream(uri)) {
                ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                byte[] chunk = new byte[8192];
                int read;
                while (input != null && (read = input.read(chunk)) != -1) buffer.write(chunk, 0, read);
                String text = new String(buffer.toByteArray(), StandardCharsets.UTF_8);
                webView.evaluateJavascript("window.importUserDataFromText(" + JSONObject.quote(text) + ")", null);
            } catch (Exception error) {
                Toast.makeText(this, "匯入失敗", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (webView == null) {
            super.onBackPressed();
            return;
        }
        webView.evaluateJavascript("Boolean(window.appBack && window.appBack())", handled -> {
            if ("true".equals(handled)) return;
            if (webView.canGoBack()) webView.goBack();
            else MainActivity.super.onBackPressed();
        });
    }
}

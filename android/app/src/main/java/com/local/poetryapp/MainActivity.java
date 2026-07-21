package com.local.poetryapp;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.webkit.JavascriptInterface;
import android.os.Bundle;
import android.os.Build;
import android.view.Window;
import android.webkit.WebSettings;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.webkit.WebViewAssetLoader;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int REQUEST_EXPORT_JSON = 41;
    private static final int REQUEST_IMPORT_JSON = 42;
    private WebView webView;
    private String pendingExportText = "";

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
        webView.loadUrl("https://appassets.androidplatform.net/assets/index.html");
    }

    public class AppBridge {
        @JavascriptInterface
        public void exportUserData(String text) {
            pendingExportText = text == null ? "" : text;
            runOnUiThread(() -> {
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("application/json");
                intent.putExtra(Intent.EXTRA_TITLE, "hymn-library-backup.json");
                try {
                    startActivityForResult(intent, REQUEST_EXPORT_JSON);
                } catch (ActivityNotFoundException error) {
                    Toast.makeText(MainActivity.this, "無法開啟檔案儲存介面", Toast.LENGTH_SHORT).show();
                }
            });
        }

        @JavascriptInterface
        public void importUserData() {
            runOnUiThread(() -> {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("application/json");
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] { "application/json", "text/plain", "*/*" });
                try {
                    startActivityForResult(intent, REQUEST_IMPORT_JSON);
                } catch (ActivityNotFoundException error) {
                    Toast.makeText(MainActivity.this, "無法開啟檔案選擇介面", Toast.LENGTH_SHORT).show();
                }
            });
        }
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

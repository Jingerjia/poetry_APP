"""Static development server for the offline hymn application.

The application itself reads only files from database/ and can therefore be
bundled directly into an Android WebView / Capacitor project later.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class App(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Database files are regenerated during development; never keep a stale
        # JavaScript bundle or index in the browser while testing locally.
        self.send_header("Cache-Control", "no-store")
        return super().end_headers()

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()


if __name__ == "__main__":
    print("Open http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), App).serve_forever()

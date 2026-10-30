"""Windows desktop shell for BSV Intelligence OS.
Install dependencies, then run: python run_desktop.py
The desktop window hosts the same local Flask application.
"""
import threading, time, webbrowser, os, secrets
os.environ.setdefault("BSV_SECRET_KEY", secrets.token_hex(32))
from werkzeug.serving import make_server
from app import app

def serve():
    server = make_server("127.0.0.1", 5001, app)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(1)
    try:
        import webview
        webview.create_window("BSV Intelligence OS", "http://127.0.0.1:5001", width=1440, height=920, min_size=(980,650))
        webview.start()
    except ImportError:
        webbrowser.open("http://127.0.0.1:5001")
        print("Install pywebview for a native desktop window: pip install pywebview")
        input("Press Enter to exit...")

import io
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote

from PIL import Image

SHARED_DIR = "/tmp/fcc_images"
STATE_FILE = os.path.join(SHARED_DIR, "state.json")
PORT = 8999
HISTORY_LIMIT = 10

RUNTIME: dict[str, Any] = {
    "cloudflare_url": None,
    "last_url": None,
    "last_filename": None,
    "history": [],
}

FILE_SERVER: ThreadingHTTPServer | None = None
TUNNEL_PROCESS: subprocess.Popen[str] | None = None

PASTE_PANEL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      color-scheme: dark;
      --surface: #141416;
      --border: #2a2a2e;
      --border-active: #52525b;
      --text: #fafafa;
      --muted: #71717a;
      --success: #22c55e;
      --error: #ef4444;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      height: 100%;
      background: var(--surface);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
    }
    .wrap { height: 100%; padding: 10px; display: flex; }
    .dropzone {
      flex: 1;
      border: 1px dashed var(--border);
      border-radius: 10px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 24px 16px;
      cursor: pointer;
      outline: none;
      transition: border-color 0.15s, background 0.15s;
    }
    .dropzone:hover, .dropzone:focus {
      border-color: var(--border-active);
      background: rgba(255, 255, 255, 0.03);
    }
    .icon {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      border: 1px solid #3f3f46;
      background: rgba(255, 255, 255, 0.04);
      position: relative;
    }
    .icon::before, .icon::after {
      content: "";
      position: absolute;
      background: #a1a1aa;
      border-radius: 1px;
    }
    .icon::before { width: 14px; height: 2px; top: 17px; left: 11px; }
    .icon::after { width: 2px; height: 14px; top: 11px; left: 17px; }
    .label { margin: 0; font-size: 0.9rem; font-weight: 500; }
    .hint { margin: 0; color: var(--muted); font-size: 0.78rem; text-align: center; line-height: 1.45; }
    kbd {
      font: inherit;
      font-size: 0.72rem;
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.04);
    }
    #status { min-height: 1.2em; font-size: 0.78rem; text-align: center; }
    #status.ok { color: var(--success); }
    #status.err { color: var(--error); }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="dropzone" id="zone" tabindex="0">
      <div class="icon"></div>
      <p class="label">Click here and paste</p>
      <p class="hint"><kbd>Ctrl</kbd> + <kbd>V</kbd> or <kbd>Cmd</kbd> + <kbd>V</kbd></p>
      <div id="status"></div>
    </div>
  </div>
  <script>
    const status = document.getElementById("status");
    const zone = document.getElementById("zone");

    function showError(message) {
      status.className = "err";
      status.textContent = message;
    }

    async function uploadBlob(blob) {
      status.className = "";
      status.textContent = "Uploading...";
      const form = new FormData();
      form.append("file", blob, "paste.png");
      const res = await fetch("/upload", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      status.className = "ok";
      status.textContent = "Done. URL is in the panel below.";
      if (data.url) await navigator.clipboard.writeText(data.url);
    }

    zone.addEventListener("click", () => zone.focus());

    document.addEventListener("paste", async (event) => {
      const items = event.clipboardData?.items || [];
      for (const item of items) {
        if (!item.type.startsWith("image/")) continue;
        event.preventDefault();
        try {
          await uploadBlob(item.getAsFile());
        } catch (err) {
          showError(err.message || "Upload failed");
        }
        return;
      }
    });
  </script>
</body>
</html>
"""


def ensure_shared_dir() -> None:
    os.makedirs(SHARED_DIR, exist_ok=True)


def load_state() -> None:
    ensure_shared_dir()
    if not os.path.isfile(STATE_FILE):
        return
    try:
        with open(STATE_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        RUNTIME["cloudflare_url"] = data.get("cloudflare_url")
        RUNTIME["last_url"] = data.get("last_url")
        RUNTIME["last_filename"] = data.get("last_filename")
        RUNTIME["history"] = data.get("history") or []
    except (OSError, json.JSONDecodeError):
        pass


def save_state() -> None:
    ensure_shared_dir()
    payload = {
        "cloudflare_url": RUNTIME.get("cloudflare_url"),
        "last_url": RUNTIME.get("last_url"),
        "last_filename": RUNTIME.get("last_filename"),
        "history": RUNTIME.get("history") or [],
    }
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def to_markdown(url: str, label: str = "screenshot") -> str:
    return f"![{label}]({url})"


def record_publish(public_url: str, filename: str) -> None:
    entry = {
        "url": public_url,
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    history = [entry] + [
        item for item in (RUNTIME.get("history") or []) if item.get("url") != public_url
    ]
    RUNTIME["history"] = history[:HISTORY_LIMIT]
    RUNTIME["last_url"] = public_url
    RUNTIME["last_filename"] = filename
    save_state()


def save_image_bytes(image_bytes: bytes, original_name: str | None = None) -> tuple[str, str]:
    image = Image.open(io.BytesIO(image_bytes))

    ext = "png"
    if original_name and "." in original_name:
        candidate = original_name.rsplit(".", 1)[-1].lower()
        if candidate in {"png", "jpg", "jpeg", "gif", "webp"}:
            ext = "jpg" if candidate == "jpeg" else candidate

    filename = f"live_{uuid.uuid4().hex[:10]}.{ext}"
    target_path = os.path.join(SHARED_DIR, filename)

    if ext == "jpg":
        # JPEG has no alpha channel; flatten onto a white background.
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.save(target_path, format="JPEG", quality=92)
    elif ext == "gif":
        # Preserve animation when present.
        is_animated = getattr(image, "is_animated", False)
        image.save(target_path, format="GIF", save_all=is_animated)
    elif ext == "webp":
        image.save(target_path, format="WEBP", quality=92)
    else:
        if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            image = image.convert("RGBA")
        image.save(target_path, format="PNG")

    return filename, target_path


def build_public_url(filename: str) -> str:
    base = (RUNTIME.get("cloudflare_url") or "").rstrip("/")
    if base:
        return f"{base}/{filename}"
    return f"http://127.0.0.1:{PORT}/{filename}"


def publish_image_bytes(image_bytes: bytes, original_name: str | None = None) -> tuple[str, str]:
    filename, _ = save_image_bytes(image_bytes, original_name)
    public_url = build_public_url(filename)
    record_publish(public_url, filename)
    return public_url, filename


class ImageBridgeHandler(BaseHTTPRequestHandler):
    server_version = "ImageBridge/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _content_type_for_filename(filename: str) -> str:
        suffix = filename.lower()
        if suffix.endswith(".png"):
            return "image/png"
        if suffix.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        if suffix.endswith(".gif"):
            return "image/gif"
        if suffix.endswith(".webp"):
            return "image/webp"
        return "application/octet-stream"

    def _lookup_file(self, path: str) -> tuple[str, str, int] | None:
        filename = os.path.basename(path)
        if not filename or filename in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
            self.send_error(404)
            return None

        file_path = os.path.join(SHARED_DIR, filename)
        if not os.path.isfile(file_path):
            self.send_error(404)
            return None

        return file_path, self._content_type_for_filename(filename), os.path.getsize(file_path)

    def _send_html_headers(self, html: str) -> None:
        size = len(html.encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(size))
        self.end_headers()

    def _send_file_headers(self, content_type: str, size: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()

    def _route_path(self) -> str:
        return unquote(self.path.split("?", 1)[0])

    def _latest_payload(self) -> dict:
        load_state()
        return {
            "url": RUNTIME.get("last_url"),
            "filename": RUNTIME.get("last_filename"),
            "history": RUNTIME.get("history") or [],
        }

    def do_HEAD(self) -> None:
        path = self._route_path()
        if path in ("", "/", "/paste"):
            self._send_html_headers(PASTE_PANEL)
            return

        if path in ("/latest", "/history"):
            body = json.dumps(self._latest_payload())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            return

        if path == "/upload":
            self.send_error(405)
            return

        result = self._lookup_file(path)
        if result is None:
            return

        _, content_type, size = result
        self._send_file_headers(content_type, size)

    def do_GET(self) -> None:
        path = self._route_path()
        if path in ("", "/", "/paste"):
            self._send_html_headers(PASTE_PANEL)
            self.wfile.write(PASTE_PANEL.encode("utf-8"))
            return

        if path in ("/latest", "/history"):
            self._send_json(200, self._latest_payload())
            return

        result = self._lookup_file(path)
        if result is None:
            return

        file_path, content_type, _size = result
        with open(file_path, "rb") as handle:
            body = handle.read()
        self._send_file_headers(content_type, len(body))
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self._route_path() != "/upload":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._send_json(400, {"error": "Empty upload"})
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(400, {"error": "Expected multipart/form-data"})
            return

        boundary = content_type.split("boundary=", 1)[-1].strip()
        raw = self.rfile.read(content_length)
        parts = raw.split(f"--{boundary}".encode("utf-8"))

        file_bytes = None
        original_name = None
        for part in parts:
            if b'Content-Disposition: form-data; name="file"' not in part:
                continue
            header_body = part.split(b"\r\n\r\n", 1)
            if len(header_body) != 2:
                continue
            headers, body = header_body
            if b'filename="' in headers:
                original_name = headers.split(b'filename="', 1)[1].split(b'"', 1)[0].decode("utf-8", "ignore")
            # Each part ends with a trailing CRLF before the next boundary marker.
            # Strip exactly that CRLF instead of rstrip(), which would corrupt
            # image data that legitimately ends in 0x0D, 0x0A, or 0x2D bytes.
            if body.endswith(b"\r\n"):
                body = body[:-2]
            file_bytes = body
            break

        if not file_bytes:
            self._send_json(400, {"error": "No file found in upload"})
            return

        try:
            public_url, filename = publish_image_bytes(file_bytes, original_name)
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid image: {exc}"})
            return

        self._send_json(
            200,
            {
                "url": public_url,
                "filename": filename,
                "markdown": to_markdown(public_url),
            },
        )


def is_file_server_running() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/latest", timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_file_server(force: bool = False) -> None:
    global FILE_SERVER

    load_state()
    if FILE_SERVER is not None and not force:
        return
    if not force and is_file_server_running():
        return

    ensure_shared_dir()
    subprocess.run(f"fuser -k {PORT}/tcp", shell=True, capture_output=True)
    time.sleep(0.4)

    try:
        FILE_SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), ImageBridgeHandler)
        thread = threading.Thread(target=FILE_SERVER.serve_forever, daemon=True)
        thread.start()
        for _ in range(15):
            if is_file_server_running():
                return
            time.sleep(0.1)
    except OSError as exc:
        # Another imgbridge/streamlit instance may already own the port.
        if getattr(exc, "errno", None) == 98:
            for _ in range(15):
                if is_file_server_running():
                    return
                time.sleep(0.1)
            return
        raise


def stop_tunnel() -> None:
    global TUNNEL_PROCESS

    subprocess.run(["pkill", "-f", f"cloudflared tunnel --url http://localhost:{PORT}"], capture_output=True)
    if TUNNEL_PROCESS and TUNNEL_PROCESS.poll() is None:
        TUNNEL_PROCESS.terminate()
        try:
            TUNNEL_PROCESS.wait(timeout=3)
        except subprocess.TimeoutExpired:
            TUNNEL_PROCESS.kill()
    TUNNEL_PROCESS = None
    RUNTIME["cloudflare_url"] = None
    save_state()


def start_tunnel(timeout_seconds: int = 25) -> str | None:
    global TUNNEL_PROCESS

    load_state()
    start_file_server()
    stop_tunnel()

    TUNNEL_PROCESS = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if TUNNEL_PROCESS.stdout is None:
            break
        line = TUNNEL_PROCESS.stdout.readline()
        if not line:
            if TUNNEL_PROCESS.poll() is not None:
                break
            continue
        if "trycloudflare.com" in line:
            for part in line.split():
                if part.startswith("https://") and "trycloudflare.com" in part:
                    url = part.strip()
                    RUNTIME["cloudflare_url"] = url
                    save_state()
                    if wait_for_tunnel_health(url):
                        return url
                    if is_tunnel_process_running():
                        return url
                    return None
    return None


def restart_tunnel() -> str | None:
    return ensure_services(force_restart=True)


def is_tunnel_process_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", f"cloudflared tunnel --url http://localhost:{PORT}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def check_tunnel_health(base_url: str | None, timeout: float = 4.0) -> bool:
    if not base_url:
        return False

    target = base_url.rstrip("/") + "/"
    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(target, method=method)
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                if 200 <= resp.status < 400:
                    return True
        except Exception:
            continue
    return False


def wait_for_tunnel_health(base_url: str, attempts: int = 12, delay_seconds: float = 0.5) -> bool:
    for _ in range(attempts):
        if check_tunnel_health(base_url):
            return True
        time.sleep(delay_seconds)
    return False


def ensure_services(force_restart: bool = False) -> str | None:
    load_state()
    start_file_server()

    current_url = RUNTIME.get("cloudflare_url")
    if not force_restart and current_url and is_tunnel_process_running():
        return current_url

    stop_tunnel()
    return start_tunnel()


def fetch_latest_state() -> dict:
    load_state()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/latest", timeout=1) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("url"):
                RUNTIME["last_url"] = data.get("url")
                RUNTIME["last_filename"] = data.get("filename")
            if data.get("history"):
                RUNTIME["history"] = data["history"]
            return data
    except Exception:
        return {
            "url": RUNTIME.get("last_url"),
            "filename": RUNTIME.get("last_filename"),
            "history": RUNTIME.get("history") or [],
        }


def upload_via_http(path: str) -> tuple[str, str]:
    filename = os.path.basename(path)
    with open(path, "rb") as handle:
        file_bytes = handle.read()

    boundary = f"----ImageBridge{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/upload",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "url" not in data or "filename" not in data:
        raise RuntimeError(data.get("error", "Upload failed"))
    return data["url"], data["filename"]


def upload_file_path(path: str) -> tuple[str, str]:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    load_state()
    start_file_server()
    if not RUNTIME.get("cloudflare_url") or not check_tunnel_health(RUNTIME.get("cloudflare_url")):
        ensure_services()
    if not RUNTIME.get("cloudflare_url"):
        raise RuntimeError("Cloudflare tunnel is not available. Install cloudflared and try again.")

    if is_file_server_running():
        return upload_via_http(path)

    with open(path, "rb") as handle:
        image_bytes = handle.read()
    return publish_image_bytes(image_bytes, os.path.basename(path))

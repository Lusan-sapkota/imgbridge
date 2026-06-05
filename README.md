# Image Bridge

Publish local screenshots and image files as public HTTPS links for IDE agents, chat tools, and other services that need fetchable image URLs.

Image Bridge runs a small local file server, exposes it through a temporary [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) (`trycloudflare.com`), and gives you:

- a raw public URL
- markdown (`![screenshot](https://...)`)
- recent upload history

Repository: [github.com/Lusan-sapkota/imgbridge](https://github.com/Lusan-sapkota/imgbridge)

## Quick install

Linux/macOS one-liner. This will:

- clone the repo to `~/.local/share/imgbridge`
- create a Python virtualenv and install dependencies
- install `cloudflared` to `~/.local/bin` if it is missing
- add `imgbridge` and `imgbridge-ui` commands to `~/.local/bin`

```bash
curl -fsSL https://raw.githubusercontent.com/Lusan-sapkota/imgbridge/main/install.sh | bash
```

Make sure `~/.local/bin` is on your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then use it:

```bash
imgbridge path/to/image.png
imgbridge-ui
```

### Custom install location

```bash
IMGBRIDGE_INSTALL_DIR="$HOME/tools/imgbridge" \
  curl -fsSL https://raw.githubusercontent.com/Lusan-sapkota/imgbridge/main/install.sh | bash
```

## Uninstall

Default uninstall removes the app, command wrappers, and running background processes. It does **not** remove `cloudflared` or uploaded images unless you opt in.

```bash
curl -fsSL https://raw.githubusercontent.com/Lusan-sapkota/imgbridge/main/uninstall.sh | bash
```

If imgbridge is already installed:

```bash
imgbridge --uninstall
```

Remove everything including runtime uploads and cloudflared (only if imgbridge installed it):

```bash
IMGBRIDGE_REMOVE_CLOUDFLARED=1 IMGBRIDGE_PURGE_DATA=1 \
  curl -fsSL https://raw.githubusercontent.com/Lusan-sapkota/imgbridge/main/uninstall.sh | bash
```

Custom install location:

```bash
IMGBRIDGE_INSTALL_DIR="$HOME/tools/imgbridge" \
  curl -fsSL https://raw.githubusercontent.com/Lusan-sapkota/imgbridge/main/uninstall.sh | bash
```

## Requirements

- Python 3.11+ with `venv`
- `git` and `curl`
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (installed automatically by the script if missing)

On Debian/Ubuntu, if Python venv is missing:

```bash
sudo apt update
sudo apt install python3-venv git curl
```

## Manual setup

```bash
git clone git@github.com:Lusan-sapkota/imgbridge.git
cd imgbridge

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

HTTPS clone:

```bash
git clone https://github.com/Lusan-sapkota/imgbridge.git
```

## Web UI

After quick install:

```bash
imgbridge-ui
```

Manual setup:

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

### Layout

- **Left:** paste a screenshot with `Ctrl+V` / `Cmd+V`
- **Right:** upload a file
- **Below:** latest public URL, markdown, preview, and recent history

The tunnel URL changes when the app restarts. Use **Restart tunnel** if the link stops responding.

## CLI

After quick install:

```bash
# Print URL and markdown
imgbridge path/to/image.png

# URL only
imgbridge path/to/image.png --url-only

# Markdown only
imgbridge path/to/image.png --markdown

# Start server + tunnel without opening the UI
imgbridge --serve

# Restart tunnel from the terminal
imgbridge --restart-tunnel

# Uninstall imgbridge
imgbridge --uninstall
```

Manual setup (from the repo with venv activated):

```bash
python imgbridge.py path/to/image.png
```

## How it works

1. Images are saved under `/tmp/fcc_images`.
2. A local HTTP server on port `8999` serves uploaded files.
3. `cloudflared` creates a temporary public HTTPS URL for that server.
4. State and recent history are stored in `/tmp/fcc_images/state.json`.

## Project structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI |
| `imgbridge.py` | CLI entry point |
| `bridge_core.py` | Server, tunnel, upload, and state logic |
| `install.sh` | One-line installer script |
| `uninstall.sh` | One-line uninstaller script |
| `requirements.txt` | Python dependencies |

## Security notes

- Temporary tunnel URLs are public. Anyone with the link can access uploaded images until the tunnel stops.
- This tool is intended for local development and quick agent workflows, not production hosting.
- Do not upload sensitive data.

## License

MIT. See [LICENSE](LICENSE).

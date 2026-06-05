# Image Bridge

Publish local screenshots and image files as public HTTPS links for IDE agents, chat tools, and other services that need fetchable image URLs.

Image Bridge runs a small local file server, exposes it through a temporary [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) (`trycloudflare.com`), and gives you:

- a raw public URL
- markdown (`![screenshot](https://...)`)
- recent upload history

## Requirements

- Python 3.11+
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) on your `PATH`

## Setup

```bash
git clone <your-repo-url>
cd fcc_images

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Web UI

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

From the project directory with the virtualenv activated:

```bash
# Print URL and markdown
python imgbridge.py path/to/image.png

# URL only
python imgbridge.py path/to/image.png --url-only

# Markdown only
python imgbridge.py path/to/image.png --markdown

# Start server + tunnel without opening the UI
python imgbridge.py --serve

# Restart tunnel from the terminal
python imgbridge.py --restart-tunnel
```

The CLI is project-local by default. To run it from anywhere, add a wrapper to `~/.local/bin`:

```bash
cat > ~/.local/bin/imgbridge <<'EOF'
#!/usr/bin/env bash
exec /path/to/fcc_images/.venv/bin/python /path/to/fcc_images/imgbridge.py "$@"
EOF
chmod +x ~/.local/bin/imgbridge
```

Replace `/path/to/fcc_images` with the actual install path.

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
| `requirements.txt` | Python dependencies |

## Security notes

- Temporary tunnel URLs are public. Anyone with the link can access uploaded images until the tunnel stops.
- This tool is intended for local development and quick agent workflows, not production hosting.
- Do not upload sensitive data.

## License

MIT. See [LICENSE](LICENSE).

import hashlib
import os
import time

import streamlit as st

from bridge_core import (
    HISTORY_LIMIT,
    PORT,
    RUNTIME,
    SHARED_DIR,
    check_tunnel_health,
    ensure_services,
    fetch_latest_state,
    is_file_server_running,
    is_tunnel_process_running,
    load_state,
    publish_image_bytes,
    to_markdown,
)

HEALTH_CACHE_TTL = 8.0

load_state()

st.set_page_config(
    page_title="Image Bridge",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {
        max-width: 860px;
        padding-top: 2.5rem;
        padding-bottom: 3rem;
      }
      [data-testid="stHeader"], [data-testid="stToolbar"] { visibility: hidden; height: 0; }
      [data-testid="stMainMenu"] { display: none; }

      .ib-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.25rem;
      }
      .ib-title { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; margin: 0; }
      .ib-subtitle { color: #8b8b94; font-size: 0.9rem; margin: 0.15rem 0 0; }

      .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 5px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        border: 1px solid transparent;
        white-space: nowrap;
      }
      .status-pill.online {
        color: #4ade80;
        background: rgba(34, 197, 94, 0.1);
        border-color: rgba(34, 197, 94, 0.28);
      }
      .status-pill.offline {
        color: #f87171;
        background: rgba(239, 68, 68, 0.1);
        border-color: rgba(239, 68, 68, 0.28);
      }
      .status-dot { width: 7px; height: 7px; border-radius: 999px; background: currentColor; }
      .status-pill.online .status-dot {
        box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.18);
      }

      .ib-url {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 0.85rem;
        padding: 8px 12px;
        border: 1px solid #2a2a2e;
        border-radius: 8px;
        background: #111113;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.82rem;
        color: #c7c7cf;
        word-break: break-all;
      }
      .ib-url-label {
        font-family: ui-sans-serif, system-ui, sans-serif;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #71717a;
        flex-shrink: 0;
      }
      .ib-url.ib-url-inline { margin-top: 0; min-width: 0; flex: 1; }
      div[data-testid="stHorizontalBlock"] .stButton > button {
        margin-top: 0;
        white-space: nowrap;
      }

      .section-label {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: #6e6e78;
        margin: 0 0 0.5rem;
      }

      div[data-testid="stIframe"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #2a2a2e;
      }
      div[data-testid="stFileUploader"] section {
        border: 1px dashed #3a3a40 !important;
        border-radius: 10px !important;
        background: #111113 !important;
        min-height: 220px;
        transition: border-color 0.15s, background 0.15s;
      }
      div[data-testid="stFileUploader"] section:hover {
        border-color: #52525b !important;
        background: rgba(255, 255, 255, 0.03) !important;
      }

      hr.divider { border: none; border-top: 1px solid #232327; margin: 1.6rem 0 1.4rem; }

      .ib-empty {
        border: 1px dashed #3a3a40;
        border-radius: 12px;
        padding: 2.75rem 1rem;
        text-align: center;
        color: #6e6e78;
        font-size: 0.9rem;
        background: #111113;
      }
      .ib-footer {
        text-align: center;
        color: #52525b;
        font-size: 0.78rem;
        margin-top: 2.5rem;
      }
      .ib-footer code {
        background: #1a1a1e;
        padding: 2px 7px;
        border-radius: 5px;
        color: #a1a1aa;
      }

      /* Neutral buttons — no Streamlit purple */
      .stButton > button[kind="primary"],
      .stButton > button[data-testid="stBaseButton-primary"] {
        background: #27272a !important;
        border: 1px solid #3f3f46 !important;
        color: #fafafa !important;
      }
      .stButton > button[kind="primary"]:hover,
      .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background: #3f3f46 !important;
        border-color: #52525b !important;
        color: #fafafa !important;
      }
      .stButton > button[kind="secondary"],
      .stButton > button[data-testid="stBaseButton-secondary"] {
        background: transparent !important;
        border: 1px solid #3f3f46 !important;
        color: #d4d4d8 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def compute_online(tunnel_url: str, force: bool = False) -> bool:
    """Cache the health probe so reruns stay responsive."""
    now = time.time()
    cache = st.session_state.get("_health_cache")
    if not force and cache and now - cache[0] < HEALTH_CACHE_TTL:
        return cache[1]

    local_ok = is_file_server_running()
    if not tunnel_url or not local_ok:
        online = False
    else:
        tunnel_ok = check_tunnel_health(tunnel_url)
        online = tunnel_ok or is_tunnel_process_running()

    st.session_state["_health_cache"] = (now, online)
    return online


def connect_tunnel(force_restart: bool = False) -> str:
    url = ensure_services(force_restart=force_restart) or ""
    if url:
        st.session_state.cloudflare_url = url
        RUNTIME["cloudflare_url"] = url
    st.session_state.pop("_health_cache", None)
    return url


if "boot_done" not in st.session_state:
    url = ""
    with st.spinner("Starting local server and Cloudflare tunnel..."):
        for attempt in range(3):
            try:
                url = connect_tunnel(force_restart=attempt > 0)
            except Exception:
                url = ""
            if url and compute_online(url, force=True):
                break
            time.sleep(1.0)
    st.session_state.cloudflare_url = url or ""
    st.session_state.boot_done = True

# Auto-reconnect once per session if startup succeeded but tunnel dropped.
if st.session_state.get("boot_done") and not st.session_state.get("_auto_reconnect_done"):
    probe_url = st.session_state.get("cloudflare_url") or ""
    if not compute_online(probe_url, force=True):
        st.session_state._auto_reconnect_done = True
        with st.spinner("Connecting tunnel..."):
            url = connect_tunnel(force_restart=True)
            st.session_state.cloudflare_url = url or ""
        st.rerun()

st.session_state.setdefault("last_public_url", RUNTIME.get("last_url"))
st.session_state.setdefault("last_filename", RUNTIME.get("last_filename"))
st.session_state.setdefault("history", RUNTIME.get("history") or [])
st.session_state.setdefault("last_upload_key", None)

tunnel_url = st.session_state.get("cloudflare_url") or ""
online = compute_online(tunnel_url)

# Header: title + status pill
header_left, header_right = st.columns([3, 1.1], vertical_alignment="center")
with header_left:
    st.markdown(
        '<div class="ib-header"><div>'
        '<p class="ib-title">Image Bridge</p>'
        '<p class="ib-subtitle">Local images to public HTTPS links for IDE agents.</p>'
        "</div></div>",
        unsafe_allow_html=True,
    )
with header_right:
    pill_class = "online" if online else "offline"
    pill_label = "Online" if online else "Offline"
    st.markdown(
        f'<div style="text-align:right">'
        f'<span class="status-pill {pill_class}"><span class="status-dot"></span>{pill_label}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

if online:
    st.markdown('<div style="margin-top:0.85rem"></div>', unsafe_allow_html=True)
    url_col, btn_col = st.columns([5.5, 1.5], vertical_alignment="center", gap="small")
    with url_col:
        st.markdown(
            f'<div class="ib-url ib-url-inline">'
            f'<span class="ib-url-label">Tunnel</span>{tunnel_url}'
            f"</div>",
            unsafe_allow_html=True,
        )
    with btn_col:
        if st.button("Restart tunnel", width="stretch"):
            with st.spinner("Restarting..."):
                connect_tunnel(force_restart=True)
            st.rerun()
else:
    st.error("Could not connect the tunnel. Make sure cloudflared is installed, then restart the app.")
    if st.button("Retry connection", type="primary"):
        with st.spinner("Connecting..."):
            connect_tunnel(force_restart=True)
        st.rerun()

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# Input row: paste (left) + upload (right)
paste_col, upload_col = st.columns(2, gap="large")

with paste_col:
    st.markdown('<p class="section-label">Paste</p>', unsafe_allow_html=True)
    st.iframe(f"http://127.0.0.1:{PORT}/paste", height=232)

with upload_col:
    st.markdown('<p class="section-label">Upload</p>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Drop or browse",
        type=["png", "jpg", "jpeg", "gif", "webp"],
        label_visibility="collapsed",
        help="PNG, JPG, GIF, or WEBP",
    )

    if uploaded and online:
        file_bytes = uploaded.getvalue()
        upload_key = hashlib.sha256(
            f"{uploaded.name}:{uploaded.size}:{file_bytes[:4096]}".encode()
        ).hexdigest()

        if upload_key != st.session_state.last_upload_key:
            try:
                public_url, filename = publish_image_bytes(file_bytes, uploaded.name)
                st.session_state.last_upload_key = upload_key
                st.session_state.last_public_url = public_url
                st.session_state.last_filename = filename
                st.session_state.history = RUNTIME.get("history") or []
                st.toast("Image published")
            except Exception as exc:
                st.error(str(exc))
        else:
            st.caption("Already published.")
    elif uploaded and not online:
        st.caption("Tunnel is still connecting. Retry above if this persists.")

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown('<p class="section-label">Output</p>', unsafe_allow_html=True)


@st.fragment(run_every=2)
def render_output() -> None:
    latest = fetch_latest_state()
    if latest.get("url"):
        st.session_state.last_public_url = latest.get("url")
        st.session_state.last_filename = latest.get("filename")
    if latest.get("history"):
        st.session_state.history = latest.get("history")

    public_url = st.session_state.last_public_url

    if not public_url:
        st.markdown(
            '<div class="ib-empty">Paste or upload an image to generate a public link</div>',
            unsafe_allow_html=True,
        )
        return

    url_col, md_col = st.columns(2, gap="medium")
    markdown = to_markdown(public_url)
    with url_col:
        st.caption("URL")
        st.code(public_url, language="text")
    with md_col:
        st.caption("Markdown")
        st.code(markdown, language="markdown")

    filename = st.session_state.last_filename
    if filename:
        preview_path = os.path.join(SHARED_DIR, filename)
        if os.path.isfile(preview_path):
            st.image(preview_path, width="stretch")

    history = st.session_state.history or []
    if len(history) > 1:
        st.markdown(
            '<p class="section-label" style="margin-top:1.25rem">Recent</p>',
            unsafe_allow_html=True,
        )
        for index, item in enumerate(history[:HISTORY_LIMIT], start=1):
            url = item.get("url")
            name = item.get("filename") or f"image {index}"
            if not url:
                continue
            with st.expander(name, expanded=False):
                st.code(url, language="text")
                st.code(to_markdown(url), language="markdown")


render_output()

st.markdown(
    '<p class="ib-footer">CLI: <code>imgbridge path/to/image.png</code></p>',
    unsafe_allow_html=True,
)

import hashlib
import os

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
    load_state,
    publish_image_bytes,
    restart_tunnel,
    to_markdown,
)

load_state()

st.set_page_config(
    page_title="Image Bridge",
    page_icon="IB",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {
        max-width: 980px;
        padding-top: 2rem;
        padding-bottom: 2rem;
      }
      [data-testid="stHeader"] { background: transparent; }
      .bridge-hero {
        margin-bottom: 1.25rem;
      }
      .bridge-hero h1 {
        font-size: 2rem;
        font-weight: 700;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.02em;
      }
      .bridge-hero p {
        margin: 0;
        color: #9ca3af;
        font-size: 0.98rem;
      }
      .bridge-card {
        border: 1px solid #2d3340;
        border-radius: 14px;
        padding: 1rem 1rem 0.5rem 1rem;
        background: #171923;
        min-height: 320px;
      }
      .bridge-card h3 {
        margin: 0 0 0.25rem 0;
        font-size: 1rem;
        font-weight: 600;
      }
      .bridge-card .hint {
        margin: 0 0 0.85rem 0;
        color: #8b93a7;
        font-size: 0.86rem;
      }
      .bridge-status {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        border: 1px solid #2d3340;
        border-radius: 12px;
        padding: 0.85rem 1rem;
        background: #12151c;
        margin-bottom: 1rem;
      }
      .bridge-dot {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        flex-shrink: 0;
      }
      .bridge-dot.online { background: #22c55e; box-shadow: 0 0 0 4px rgba(34,197,94,0.15); }
      .bridge-dot.offline { background: #ef4444; box-shadow: 0 0 0 4px rgba(239,68,68,0.15); }
      .bridge-status-text {
        font-size: 0.92rem;
        color: #d1d5db;
        word-break: break-all;
      }
      .bridge-output {
        border: 1px solid #2d3340;
        border-radius: 14px;
        padding: 1rem;
        background: #12151c;
        margin-top: 0.5rem;
      }
      div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"] div[data-testid="stIframe"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #2d3340;
      }
      div[data-testid="stFileUploader"] section {
        border-radius: 10px;
        border: 1px dashed #3a4150 !important;
        background: #10131a;
        min-height: 180px;
      }
      .stCodeBlock, .stCode {
        border-radius: 10px !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="bridge-hero">
      <h1>Image Bridge</h1>
      <p>Publish local images as public HTTPS links for IDE agents and chat tools.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if "boot_done" not in st.session_state:
    with st.spinner("Starting local server and Cloudflare tunnel..."):
        st.session_state.cloudflare_url = ensure_services()
        st.session_state.boot_done = True

if "last_public_url" not in st.session_state:
    st.session_state.last_public_url = RUNTIME.get("last_url")
if "last_filename" not in st.session_state:
    st.session_state.last_filename = RUNTIME.get("last_filename")
if "history" not in st.session_state:
    st.session_state.history = RUNTIME.get("history") or []
if "last_upload_key" not in st.session_state:
    st.session_state.last_upload_key = None

tunnel_url = st.session_state.get("cloudflare_url")
local_ok = is_file_server_running()
tunnel_ok = check_tunnel_health(tunnel_url) if tunnel_url else False

status_left, status_right = st.columns([5, 1])
with status_left:
    if tunnel_url and tunnel_ok and local_ok:
        st.markdown(
            f"""
            <div class="bridge-status">
              <div class="bridge-dot online"></div>
              <div class="bridge-status-text"><strong>Online</strong> · {tunnel_url}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif tunnel_url:
        st.markdown(
            f"""
            <div class="bridge-status">
              <div class="bridge-dot offline"></div>
              <div class="bridge-status-text"><strong>Reconnecting required</strong> · {tunnel_url}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="bridge-status">
              <div class="bridge-dot offline"></div>
              <div class="bridge-status-text"><strong>Offline</strong> · Install cloudflared and restart tunnel</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with status_right:
    if st.button("Restart tunnel", use_container_width=True):
        with st.spinner("Restarting tunnel..."):
            st.session_state.cloudflare_url = restart_tunnel()
        st.rerun()

if not tunnel_ok or not local_ok:
    if st.button("Connect now", type="primary"):
        with st.spinner("Connecting..."):
            st.session_state.cloudflare_url = ensure_services(force_restart=not tunnel_ok)
        st.rerun()

if st.session_state.cloudflare_url and tunnel_ok:
    input_col, output_col = st.columns([1.05, 0.95], gap="medium")

    with input_col:
        paste_panel, upload_panel = st.tabs(["Paste", "Upload"])

        with paste_panel:
            st.markdown(
                """
                <div class="bridge-card">
                  <h3>Paste screenshot</h3>
                  <p class="hint">Click the panel below, then press Ctrl+V or Cmd+V.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.iframe(f"http://127.0.0.1:{PORT}/paste", height=250)

        with upload_panel:
            st.markdown(
                """
                <div class="bridge-card" style="min-height: 120px; margin-bottom: 0.75rem;">
                  <h3>Upload file</h3>
                  <p class="hint">PNG, JPG, GIF, or WEBP up to 200MB.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            uploaded = st.file_uploader(
                "Choose an image",
                type=["png", "jpg", "jpeg", "gif", "webp"],
                label_visibility="collapsed",
            )

            if uploaded:
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
                        st.success("Uploaded.")
                    except Exception as exc:
                        st.error(f"Processing error: {exc}")
                else:
                    st.info("This file is already published.")

    with output_col:
        st.markdown("### Output")

        @st.fragment(run_every=2)
        def show_results() -> None:
            latest = fetch_latest_state()
            if latest.get("url"):
                st.session_state.last_public_url = latest.get("url")
                st.session_state.last_filename = latest.get("filename")
            if latest.get("history"):
                st.session_state.history = latest.get("history")

            if st.session_state.last_public_url:
                public_url = st.session_state.last_public_url
                markdown = to_markdown(public_url)

                st.caption("Public URL")
                st.code(public_url, language="text")

                st.caption("Markdown")
                st.code(markdown, language="markdown")

                filename = st.session_state.last_filename
                if filename:
                    preview_path = os.path.join(SHARED_DIR, filename)
                    if os.path.isfile(preview_path):
                        st.image(preview_path, use_container_width=True)
            else:
                st.info("Paste or upload an image to generate a public link.")

            history = st.session_state.history or []
            if history:
                st.markdown("#### Recent")
                for index, item in enumerate(history[:HISTORY_LIMIT], start=1):
                    url = item.get("url")
                    filename = item.get("filename") or "image"
                    if not url:
                        continue
                    with st.expander(f"{index}. {filename}", expanded=index == 1):
                        st.code(url, language="text")
                        st.code(to_markdown(url), language="markdown")

        show_results()

st.caption("CLI: `imgbridge path/to/image.png`")

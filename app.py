import hashlib
import os

import streamlit as st

from bridge_core import (
    HISTORY_LIMIT,
    PORT,
    RUNTIME,
    SHARED_DIR,
    check_tunnel_health,
    fetch_latest_state,
    load_state,
    publish_image_bytes,
    restart_tunnel,
    start_tunnel,
    to_markdown,
)

load_state()

st.set_page_config(page_title="Image Bridge", layout="wide")

st.title("Image Bridge")
st.caption("Publish local images as public HTTPS links for IDE agents and chat tools.")

if "cloudflare_url" not in st.session_state:
    st.session_state.cloudflare_url = RUNTIME.get("cloudflare_url")
if "servers_started" not in st.session_state:
    st.session_state.servers_started = bool(st.session_state.cloudflare_url)
if "last_public_url" not in st.session_state:
    st.session_state.last_public_url = RUNTIME.get("last_url")
if "last_filename" not in st.session_state:
    st.session_state.last_filename = RUNTIME.get("last_filename")
if "history" not in st.session_state:
    st.session_state.history = RUNTIME.get("history") or []
if "last_upload_key" not in st.session_state:
    st.session_state.last_upload_key = None

if not st.session_state.servers_started:
    with st.spinner("Starting local server and Cloudflare tunnel..."):
        tunnel_url = start_tunnel()
        st.session_state.cloudflare_url = tunnel_url
        st.session_state.servers_started = bool(tunnel_url)

status_col, action_col = st.columns([3, 1])
with status_col:
    if st.session_state.cloudflare_url:
        healthy = check_tunnel_health(st.session_state.cloudflare_url)
        if healthy:
            st.success(f"Tunnel online: `{st.session_state.cloudflare_url}`")
        else:
            st.warning(
                f"Tunnel URL assigned but not responding: `{st.session_state.cloudflare_url}`"
            )
    else:
        st.error("Cloudflare tunnel did not start. Install `cloudflared`, then restart this app.")

with action_col:
    if st.button("Restart tunnel", use_container_width=True):
        with st.spinner("Restarting tunnel..."):
            tunnel_url = restart_tunnel()
            st.session_state.cloudflare_url = tunnel_url
            st.session_state.servers_started = bool(tunnel_url)
        st.rerun()

if st.session_state.cloudflare_url:
    paste_col, upload_col = st.columns(2, gap="large")

    with paste_col:
        st.subheader("Paste")
        st.caption("Click the panel, then paste a screenshot with Ctrl+V or Cmd+V.")
        st.iframe(f"http://127.0.0.1:{PORT}/paste", height=220)

    with upload_col:
        st.subheader("Upload")
        st.caption("Choose a local image file from your machine.")
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
                    st.success("Uploaded. Public URL is shown below.")
                except Exception as exc:
                    st.error(f"Processing error: {exc}")
            else:
                st.info("This file is already published. Paste or choose a different image.")

    @st.fragment(run_every=2)
    def show_results() -> None:
        latest = fetch_latest_state()
        if latest.get("url"):
            st.session_state.last_public_url = latest.get("url")
            st.session_state.last_filename = latest.get("filename")
        if latest.get("history"):
            st.session_state.history = latest.get("history")

        st.divider()
        st.subheader("Public URL")

        if st.session_state.last_public_url:
            public_url = st.session_state.last_public_url
            markdown = to_markdown(public_url)

            st.markdown("**URL**")
            st.code(public_url, language="text")

            st.markdown("**Markdown**")
            st.code(markdown, language="markdown")

            filename = st.session_state.last_filename
            if filename:
                preview_path = os.path.join(SHARED_DIR, filename)
                if os.path.isfile(preview_path):
                    st.image(preview_path, caption="Latest image", width=420)
        else:
            st.info("Paste or upload an image above to generate a public link.")

        history = st.session_state.history or []
        if history:
            st.subheader("Recent links")
            for index, item in enumerate(history[:HISTORY_LIMIT], start=1):
                url = item.get("url")
                filename = item.get("filename")
                if not url:
                    continue

                with st.expander(f"{index}. {filename or 'image'}", expanded=index == 1):
                    st.code(url, language="text")
                    st.code(to_markdown(url), language="markdown")
                    if filename:
                        preview_path = os.path.join(SHARED_DIR, filename)
                        if os.path.isfile(preview_path):
                            st.image(preview_path, width=280)

    show_results()

st.caption("CLI: `python imgbridge.py path/to/image.png`")

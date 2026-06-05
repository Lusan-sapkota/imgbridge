#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${IMGBRIDGE_INSTALL_DIR:-$HOME/.local/share/imgbridge}"
BIN_DIR="${IMGBRIDGE_BIN_DIR:-$HOME/.local/bin}"
MANIFEST="$INSTALL_DIR/.imgbridge-manifest"
RUNTIME_DIR="/tmp/fcc_images"
PORT=8999

info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }

remove_if_our_wrapper() {
  local name="$1"
  local path="$BIN_DIR/$name"

  if [ ! -f "$path" ]; then
    return
  fi

  if grep -q "$INSTALL_DIR" "$path" 2>/dev/null; then
    rm -f "$path"
    info "Removed $path"
  else
    warn "Skipped $path (not managed by imgbridge)"
  fi
}

stop_services() {
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "cloudflared tunnel --url http://localhost:${PORT}" >/dev/null 2>&1 || true
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
  fi

  info "Stopped imgbridge background processes on port ${PORT}"
}

remove_cloudflared_if_managed() {
  local remove_cloudflared="${IMGBRIDGE_REMOVE_CLOUDFLARED:-0}"
  local cloudflared_path="$BIN_DIR/cloudflared"
  local installed_by_imgbridge=0

  if [ -f "$MANIFEST" ]; then
    # shellcheck disable=SC1090
    source "$MANIFEST"
    installed_by_imgbridge="${cloudflared_installed:-0}"
    cloudflared_path="${cloudflared_path:-$BIN_DIR/cloudflared}"
  fi

  if [ "$remove_cloudflared" != "1" ]; then
    return
  fi

  if [ "$installed_by_imgbridge" = "1" ] && [ -x "$cloudflared_path" ]; then
    rm -f "$cloudflared_path"
    info "Removed cloudflared installed by imgbridge: $cloudflared_path"
  else
    warn "cloudflared was not installed by imgbridge; leaving it in place"
  fi
}

purge_runtime_data() {
  if [ "${IMGBRIDGE_PURGE_DATA:-0}" = "1" ] && [ -d "$RUNTIME_DIR" ]; then
    rm -rf "$RUNTIME_DIR"
    info "Removed runtime data: $RUNTIME_DIR"
  fi
}

main() {
  info "Image Bridge uninstaller"

  stop_services
  remove_if_our_wrapper "imgbridge"
  remove_if_our_wrapper "imgbridge-ui"
  remove_cloudflared_if_managed

  if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    info "Removed install directory: $INSTALL_DIR"
  else
    warn "Install directory not found: $INSTALL_DIR"
  fi

  purge_runtime_data

  cat <<EOF

Image Bridge has been uninstalled.

Removed:
  - command wrappers from $BIN_DIR (if managed by imgbridge)
  - install directory $INSTALL_DIR

Not removed by default:
  - cloudflared (set IMGBRIDGE_REMOVE_CLOUDFLARED=1 to remove if imgbridge installed it)
  - uploaded images in $RUNTIME_DIR (set IMGBRIDGE_PURGE_DATA=1 to delete)

EOF
}

main "$@"

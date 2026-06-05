#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${IMGBRIDGE_REPO_URL:-https://github.com/Lusan-sapkota/imgbridge.git}"
INSTALL_DIR="${IMGBRIDGE_INSTALL_DIR:-$HOME/.local/share/imgbridge}"
BIN_DIR="${IMGBRIDGE_BIN_DIR:-$HOME/.local/bin}"
BRANCH="${IMGBRIDGE_BRANCH:-main}"
IMGBRIDGE_INSTALLED_CLOUDFLARED=0

info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ensure_bin_dir() {
  mkdir -p "$BIN_DIR"
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
      warn "$BIN_DIR is not on your PATH."
      warn "Add this to your shell profile:"
      warn "  export PATH=\"$BIN_DIR:\$PATH\""
      ;;
  esac
}

detect_cloudflared_arch() {
  local machine
  machine="$(uname -m)"
  case "$machine" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    armv7l|armv6l) echo "arm" ;;
    i386|i686) echo "386" ;;
    *) die "Unsupported architecture for automatic cloudflared install: $machine" ;;
  esac
}

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    info "cloudflared already installed: $(command -v cloudflared)"
    IMGBRIDGE_INSTALLED_CLOUDFLARED=0
    return
  fi

  local os arch target asset
  os="$(uname -s)"
  arch="$(detect_cloudflared_arch)"
  target="$BIN_DIR/cloudflared"

  case "$os" in
    Linux)
      asset="cloudflared-linux-${arch}"
      ;;
    Darwin)
      asset="cloudflared-darwin-${arch}"
      ;;
    *)
      die "Automatic cloudflared install is not supported on $os. Install cloudflared manually."
      ;;
  esac

  info "Installing cloudflared to $target"
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${asset}" -o "$target"
  chmod +x "$target"
  IMGBRIDGE_INSTALLED_CLOUDFLARED=1
  info "cloudflared installed"
}

ensure_python() {
  require_cmd python3

  if ! python3 -c 'import venv' >/dev/null 2>&1; then
    die "Python venv module is missing. Install it first, e.g. sudo apt install python3-venv"
  fi
}

clone_or_update_repo() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing install in $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
  else
    info "Cloning imgbridge into $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
}

setup_python_env() {
  info "Setting up Python virtual environment"
  if [ ! -d "$INSTALL_DIR/.venv" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
  fi

  "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
}

write_wrappers() {
  info "Installing command wrappers into $BIN_DIR"

  cat >"$BIN_DIR/imgbridge" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/imgbridge.py" "\$@"
EOF

  cat >"$BIN_DIR/imgbridge-ui" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/streamlit" run "$INSTALL_DIR/app.py" "\$@"
EOF

  chmod +x "$BIN_DIR/imgbridge" "$BIN_DIR/imgbridge-ui"
}

write_manifest() {
  cat >"$INSTALL_DIR/.imgbridge-manifest" <<EOF
install_dir=$INSTALL_DIR
bin_dir=$BIN_DIR
cloudflared_installed=$IMGBRIDGE_INSTALLED_CLOUDFLARED
cloudflared_path=$BIN_DIR/cloudflared
EOF
}

main() {
  info "Image Bridge installer"
  ensure_bin_dir
  require_cmd git
  require_cmd curl
  ensure_python
  install_cloudflared
  clone_or_update_repo
  setup_python_env
  write_wrappers
  write_manifest

  cat <<EOF

Image Bridge is ready.

Install directory:
  $INSTALL_DIR

Commands:
  imgbridge screenshot.png
  imgbridge-ui

Examples:
  imgbridge ./shot.png --url-only
  imgbridge ./shot.png --markdown
  imgbridge --serve
  imgbridge --restart-tunnel

If \`imgbridge\` is not found, restart your shell or run:
  export PATH="$BIN_DIR:\$PATH"

EOF
}

main "$@"

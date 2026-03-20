#!/usr/bin/env bash
# Bootstrap ohmyvoice on Linux from a single command.
# Wrapped in main() so that bash reads the entire script before executing,
# preventing package managers from consuming stdin when run via curl|bash.
set -euo pipefail

main() {

REPO="${OHMYVOICE_GITHUB_REPO:-forbidden-game/ohmyvoice}"
REF="${OHMYVOICE_REF:-main}"
INSTALL_DIR="${OHMYVOICE_INSTALL_DIR:-${HOME}/.local/share/ohmyvoice}"
ARCHIVE_URL="${OHMYVOICE_ARCHIVE_URL:-https://codeload.github.com/${REPO}/tar.gz/refs/heads/${REF}}"
SKIP_PACKAGE_INSTALL="${OHMYVOICE_SKIP_PACKAGE_INSTALL:-0}"

if [ "$(uname -s)" != "Linux" ]; then
  echo "install-linux.sh only supports Linux." >&2
  exit 1
fi

for cmd in curl tar; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

node_major() {
  if ! command -v node >/dev/null 2>&1; then
    echo 0
    return
  fi

  node -p "process.versions.node.split('.')[0]"
}

install_dependencies_apt() {
  if [ "$(node_major)" -lt 20 ]; then
    echo "[1/4] Installing Node.js 20..."
    run_as_root apt-get update </dev/null
    run_as_root apt-get install -y ca-certificates curl gnupg </dev/null
    curl -fsSL https://deb.nodesource.com/setup_20.x | run_as_root bash - </dev/null
  else
    echo "[1/4] Node.js >= 20 already present."
    run_as_root apt-get update </dev/null
  fi

  echo "[2/4] Installing Linux dependencies..."
  run_as_root apt-get install -y \
    nodejs \
    ffmpeg \
    python3 \
    python3-venv \
    pipewire-tools \
    wl-clipboard \
    libnotify-bin </dev/null
}

install_dependencies_pacman() {
  echo "[1/4] Installing Linux dependencies..."
  run_as_root pacman -S --needed --noconfirm \
    nodejs \
    npm \
    ffmpeg \
    python \
    pipewire \
    wl-clipboard \
    libnotify </dev/null
}

install_dependencies() {
  if command -v apt-get >/dev/null 2>&1; then
    install_dependencies_apt
  elif command -v pacman >/dev/null 2>&1; then
    install_dependencies_pacman
  else
    echo "Unsupported package manager. Supported installers: apt and pacman." >&2
    exit 1
  fi

  if [ "$(node_major)" -lt 20 ]; then
    echo "Node.js 20+ is required, but the detected version is too old." >&2
    echo "Install Node.js 20+, then re-run this installer." >&2
    exit 1
  fi

  for cmd in node npm ffmpeg python3 pw-record pw-play wl-copy notify-send; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      echo "Missing required command after install: ${cmd}" >&2
      exit 1
    fi
  done
}

download_repo() {
  local tmp_dir archive
  tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/ohmyvoice-install.XXXXXX")"
  archive="${tmp_dir}/ohmyvoice.tar.gz"
  trap 'rm -rf "${tmp_dir}"' EXIT

  echo "[3/4] Downloading ohmyvoice (${REPO}@${REF})..."
  curl -fsSL "${ARCHIVE_URL}" -o "${archive}"
  mkdir -p "$(dirname "${INSTALL_DIR}")"

  if [ -e "${INSTALL_DIR}" ] && [ ! -d "${INSTALL_DIR}" ]; then
    echo "Install path exists but is not a directory: ${INSTALL_DIR}" >&2
    exit 1
  fi

  if [ -d "${INSTALL_DIR}" ]; then
    echo "  Preserving existing files in ${INSTALL_DIR}"
  else
    mkdir -p "${INSTALL_DIR}"
  fi

  tar -xzf "${archive}" --strip-components=1 -C "${INSTALL_DIR}"

  trap - EXIT
  rm -rf "${tmp_dir}"
}

run_setup() {
  echo "[4/4] Running ohmyvoice setup..."
  cd "${INSTALL_DIR}"
  bash ./setup-linux.sh
}

if [ "${SKIP_PACKAGE_INSTALL}" != "1" ]; then
  install_dependencies
else
  echo "[1/4] Skipping package installation (OHMYVOICE_SKIP_PACKAGE_INSTALL=1)."
fi

download_repo
run_setup

echo ""
echo "ohmyvoice is installed in ${INSTALL_DIR}"
echo "Re-run this command anytime to update."

}

main "$@"

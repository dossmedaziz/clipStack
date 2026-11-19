#!/usr/bin/env bash
#
# setup-clipstack-tools.sh
# Installs everything needed to develop, package and publish ClipStack
# (a Win+V style clipboard history for Ubuntu), and prepares the project folder.
#
# Usage:
#   chmod +x setup-clipstack-tools.sh
#   ./setup-clipstack-tools.sh
#
set -euo pipefail

PROJECT_DIR="$HOME/projects/clipstack"
SHORTCUT="<Super>b"

green()  { printf "\033[1;32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[1;33m%s\033[0m\n" "$*"; }
red()    { printf "\033[1;31m%s\033[0m\n" "$*"; }
step()   { echo; green "==> $*"; }

# ---------------------------------------------------------------- checks ----
if [[ $EUID -eq 0 ]]; then
  red "Please run this script as your normal user, not with sudo."
  red "It will ask for your password when it needs it."
  exit 1
fi

if ! grep -qi "ubuntu" /etc/os-release; then
  yellow "Warning: this does not look like Ubuntu. Continuing anyway..."
fi

. /etc/os-release
step "Detected: ${PRETTY_NAME:-unknown}, session: ${XDG_SESSION_TYPE:-unknown}, desktop: ${XDG_CURRENT_DESKTOP:-unknown}"

# ------------------------------------------------------- enable universe ----
step "Making sure the 'universe' repository is enabled (needed for some tools)"
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y universe
sudo apt-get update

# ------------------------------------------------------------- packages ----
PACKAGES=(
  # Basics
  git curl sqlite3

  # Python + GTK 3 (the popup window)
  python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-setuptools

  # Clipboard tools
  wl-clipboard   # Wayland: wl-copy / wl-paste
  xclip          # X11

  # Auto-paste helpers
  xdotool        # X11
  ydotool        # Wayland (needs extra setup, optional)

  # Debian packaging (.deb) and publishing to a Launchpad PPA
  build-essential devscripts debhelper dh-python python3-all
  lintian dput gnupg
)

step "Installing packages"
sudo apt-get install -y "${PACKAGES[@]}"

# ------------------------------------------------------ git identity -------
step "Checking your Git identity"
if [[ -z "$(git config --global user.name || true)" ]]; then
  read -rp "Your full name (for Git and the package changelog): " NAME
  git config --global user.name "$NAME"
fi
if [[ -z "$(git config --global user.email || true)" ]]; then
  read -rp "Your email (use the same one you will use on Launchpad): " EMAIL
  git config --global user.email "$EMAIL"
fi

GIT_NAME="$(git config --global user.name)"
GIT_EMAIL="$(git config --global user.email)"

# Debian packaging tools (dch, debuild) read these variables
if ! grep -q "DEBFULLNAME" "$HOME/.bashrc"; then
  {
    echo ""
    echo "# Used by Debian packaging tools (dch, debuild)"
    echo "export DEBFULLNAME=\"$GIT_NAME\""
    echo "export DEBEMAIL=\"$GIT_EMAIL\""
  } >> "$HOME/.bashrc"
  green "Added DEBFULLNAME and DEBEMAIL to ~/.bashrc"
fi

# ------------------------------------------------------ project folder -----
step "Preparing the project folder: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
if [[ ! -d .git ]]; then
  git init -q
  green "Created an empty Git repository."
else
  yellow "Git repository already exists, leaving it as it is."
fi

# ------------------------------------------------------- shortcut check ----
step "Checking that Super + B is free"
if command -v gsettings >/dev/null 2>&1; then
  if gsettings list-recursively 2>/dev/null | grep -qi "'${SHORTCUT}'"; then
    yellow "Super + B is ALREADY used by something:"
    gsettings list-recursively | grep -i "'${SHORTCUT}'" || true
    yellow "Free it or choose another shortcut before installing ClipStack."
  else
    green "Super + B is free."
  fi
else
  yellow "gsettings not found (not GNOME?). Skipping the shortcut check."
fi

# ---------------------------------------------------------- claude code ----
step "Checking for Claude Code"
if command -v claude >/dev/null 2>&1; then
  green "Claude Code is installed."
else
  yellow "Claude Code is not installed. Install it from https://claude.com/claude-code"
fi

# ------------------------------------------------------------- summary -----
echo
green "All done!"
echo "Next steps:"
echo "  1. Close and reopen your terminal (to load DEBFULLNAME / DEBEMAIL)."
echo "  2. cd $PROJECT_DIR"
echo "  3. Copy CLAUDE_CODE_PROMPT.md into that folder."
echo "  4. Run: claude"
echo "  5. Paste the prompt, or type: Read CLAUDE_CODE_PROMPT.md and follow it."
#!/usr/bin/env bash
# install_service.sh — install and enable CAAMS as a systemd service.
#
# Safe to run multiple times (idempotent).
# Must be run as root (or with sudo).
#
# What this script does:
#   1. Validates prerequisites (systemctl, python3)
#   2. Copies the repo to /opt/caams (or uses it in-place if already there)
#   3. Creates a virtualenv at /opt/caams/venv and installs dependencies
#   4. Verifies TLS certificates (prints generation command and aborts if missing)
#   5. Creates the 'caams' system user/group if they don't exist
#   6. Sets file ownership/permissions and creates the log directory
#   7. Creates /etc/caams.env with CAAMS_SECRET_KEY
#   8. Seeds the database via seed.py if no caams.db exists yet
#   9. Installs /etc/systemd/system/caams.service
#  10. Enables the service (auto-start on boot) and starts it now

set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  error "This script must be run as root.  Try: sudo $0"
fi

# ── Locate the repo ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"

# ── Configuration (override via environment) ──────────────────────────────────
INSTALL_DIR="${CAAMS_INSTALL_DIR:-/opt/caams}"
SERVICE_USER="${CAAMS_USER:-caams}"
SERVICE_GROUP="${CAAMS_GROUP:-caams}"
ENV_FILE="/etc/caams.env"
UNIT_FILE="/etc/systemd/system/caams.service"
CERT="$INSTALL_DIR/certs/cert.pem"
KEY="$INSTALL_DIR/certs/key.pem"
VENV_DIR="$INSTALL_DIR/venv"

echo ""
echo "========================================"
echo "  CAAMS service installer"
echo "========================================"
echo "  Repo:        $REPO_DIR"
echo "  Install dir: $INSTALL_DIR"
echo "  Service user: $SERVICE_USER"
echo "========================================"
echo ""

# ── 1. Prerequisites ──────────────────────────────────────────────────────────
info "Checking prerequisites…"

if ! command -v systemctl &>/dev/null; then
  error "systemd not found.  This installer requires a systemd-based Linux distro."
fi

SYS_PYTHON3="$(command -v python3 2>/dev/null || true)"
if [[ -z "$SYS_PYTHON3" ]]; then
  error "python3 not found on PATH. Install Python 3.11+ first."
fi
info "Found python3 at $SYS_PYTHON3"

# ── 2. Copy / sync repo to install dir ───────────────────────────────────────
if [[ "$REPO_DIR" != "$INSTALL_DIR" ]]; then
  info "Syncing repo → $INSTALL_DIR …"
  # rsync preserves permissions and is idempotent; fall back to cp if missing
  if command -v rsync &>/dev/null; then
    rsync -a --delete \
      --exclude='.git' \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='caams.db' \
      --exclude='venv/' \
      --exclude='certs/' \
      --exclude='logs/' \
      "$REPO_DIR/" "$INSTALL_DIR/"
  else
    mkdir -p "$INSTALL_DIR"
    cp -r "$REPO_DIR"/. "$INSTALL_DIR/"
  fi
  info "Synced to $INSTALL_DIR"
else
  info "Repo is already at install dir — no copy needed."
fi

# ── 3. Virtualenv and dependencies ───────────────────────────────────────────
if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  info "Creating virtualenv at $VENV_DIR …"
  "$SYS_PYTHON3" -m venv "$VENV_DIR"
else
  info "Virtualenv already exists at $VENV_DIR — reusing."
fi

PYTHON3="$VENV_DIR/bin/python3"
info "Installing Python dependencies into venv …"
"$PYTHON3" -m pip install --quiet --upgrade pip
"$PYTHON3" -m pip install --quiet --upgrade -r "$INSTALL_DIR/requirements.txt"
info "Dependencies installed."

# ── 4. TLS certificates ───────────────────────────────────────────────────────
if [[ ! -f "$CERT" || ! -f "$KEY" ]]; then
  warn "TLS certificate not found at $INSTALL_DIR/certs/."
  echo ""
  echo "  Generate a self-signed cert with:"
  echo ""
  echo "    mkdir -p $INSTALL_DIR/certs"
  echo "    openssl req -x509 -newkey rsa:4096 \\"
  echo "      -keyout $INSTALL_DIR/certs/key.pem \\"
  echo "      -out    $INSTALL_DIR/certs/cert.pem \\"
  echo "      -sha256 -days 3650 -nodes \\"
  echo "      -subj   \"/CN=\$(hostname)\" \\"
  echo "      -addext \"subjectAltName=DNS:\$(hostname),IP:\$(hostname -I | awk '{print \$1}')\""
  echo ""
  echo "  Or copy your CA-signed cert.pem + key.pem into $INSTALL_DIR/certs/ ."
  echo ""
  error "Aborting — install the certificate and re-run this script."
fi

info "TLS certificate: OK"

# ── 5. System user ────────────────────────────────────────────────────────────
if ! getent group "$SERVICE_GROUP" &>/dev/null; then
  info "Creating group '$SERVICE_GROUP' …"
  groupadd --system "$SERVICE_GROUP"
fi

if ! id -u "$SERVICE_USER" &>/dev/null; then
  info "Creating system user '$SERVICE_USER' …"
  useradd --system \
    --gid "$SERVICE_GROUP" \
    --no-create-home \
    --shell /usr/sbin/nologin \
    --comment "CAAMS service account" \
    "$SERVICE_USER"
else
  info "User '$SERVICE_USER' already exists — skipping."
fi

# ── 6. File ownership, permissions, and log directory ─────────────────────────
info "Setting ownership on $INSTALL_DIR …"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"

# Key must not be world-readable
chmod 640 "$KEY"
chmod 644 "$CERT"

# Create log directory — the app writes access.log and app.log here.
# 750 keeps logs readable only by root and the service account.
LOG_DIR="$INSTALL_DIR/logs"
mkdir -p "$LOG_DIR"
chown "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 750 "$LOG_DIR"
info "Log directory: $LOG_DIR"

# Database (may not exist yet; seed.py creates it)
DB="$INSTALL_DIR/caams.db"
if [[ -f "$DB" ]]; then
  chown "$SERVICE_USER:$SERVICE_GROUP" "$DB"
  chmod 660 "$DB"
fi

# ── 7. Environment file (/etc/caams.env) ──────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
  if grep -q "caams-dev-secret-please-change-in-production" "$ENV_FILE"; then
    error "$ENV_FILE still contains the default development secret key — refusing to continue. Generate a real key: python3 -c \"import secrets; print(secrets.token_hex(32))\" and set it as CAAMS_SECRET_KEY in $ENV_FILE"
  fi
  warn "$ENV_FILE already exists — leaving it untouched."
  warn "Make sure CAAMS_SECRET_KEY is set inside it."
else
  info "Generating $ENV_FILE …"
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$ENV_FILE" <<EOF
# CAAMS runtime environment
# This file is readable only by root and the caams service account.
CAAMS_SECRET_KEY=${SECRET_KEY}

# Optional overrides:
# CAAMS_HOST=0.0.0.0
# CAAMS_PORT=8443
EOF
  chown root:"$SERVICE_GROUP" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  info "Generated CAAMS_SECRET_KEY and wrote $ENV_FILE"
fi

# ── 8. Seed the database if it doesn't exist yet ──────────────────────────────
if [[ ! -f "$DB" ]]; then
  info "Seeding database …"
  (cd "$INSTALL_DIR" && sudo -u "$SERVICE_USER" "$PYTHON3" seed.py)
fi

# ── 9. Install the systemd unit file ──────────────────────────────────────────
info "Installing $UNIT_FILE …"

# Substitute the template paths with the actual install dir and venv python.
sed \
  -e "s|/opt/caams|${INSTALL_DIR}|g" \
  -e "s|User=caams|User=${SERVICE_USER}|g" \
  -e "s|Group=caams|Group=${SERVICE_GROUP}|g" \
  -e "s|/usr/bin/python3|${PYTHON3}|g" \
  "$REPO_DIR/caams.service" > "$UNIT_FILE"

chmod 644 "$UNIT_FILE"
info "Unit file written to $UNIT_FILE"

# ── 10. Enable and start ──────────────────────────────────────────────────────
info "Reloading systemd daemon …"
systemctl daemon-reload

info "Enabling caams.service (auto-start on boot) …"
systemctl enable caams.service

if systemctl is-active --quiet caams.service; then
  info "Restarting caams.service (already running) …"
  systemctl restart caams.service
else
  info "Starting caams.service …"
  systemctl start caams.service
fi

# Give it a moment to confirm it started cleanly
sleep 2

echo ""
echo "========================================"
info "Installation complete!"
echo "========================================"
echo ""
systemctl status caams.service --no-pager --lines=10 2>&1 || true
echo ""
echo "  Useful commands:"
echo "    systemctl status  caams      — check status"
echo "    systemctl stop    caams      — stop the service"
echo "    systemctl restart caams      — restart after config changes"
echo "    journalctl -u caams -f       — tail the live log"
echo "    journalctl -u caams --since today  — today's logs"
echo ""

#!/usr/bin/env bash
# CAAMS startup script — serves over HTTPS using certs/cert.pem + certs/key.pem
#
# First-time setup:
#   mkdir -p certs
#   openssl req -x509 -newkey rsa:4096 \
#     -keyout certs/key.pem -out certs/cert.pem \
#     -sha256 -days 3650 -nodes \
#     -subj "/CN=<your-hostname>" \
#     -addext "subjectAltName=DNS:<your-hostname>,IP:<your-ip>"
#
# Or to use a CA-signed cert, drop cert.pem and key.pem into certs/ and run this script.
#
# Environment variables:
#   CAAMS_SECRET_KEY  — JWT signing key (required in production)
#   CAAMS_HOST        — bind address (default: 0.0.0.0)
#   CAAMS_PORT        — port (default: 8443)

set -euo pipefail

CERT="certs/cert.pem"
KEY="certs/key.pem"
HOST="${CAAMS_HOST:-0.0.0.0}"
PORT="${CAAMS_PORT:-8443}"

if [[ ! -f "$CERT" || ! -f "$KEY" ]]; then
  echo "ERROR: TLS certificate not found. Generate one with:"
  echo ""
  echo "  mkdir -p certs"
  echo "  openssl req -x509 -newkey rsa:4096 \\"
  echo "    -keyout certs/key.pem -out certs/cert.pem \\"
  echo "    -sha256 -days 3650 -nodes \\"
  echo '    -subj "/CN=<your-hostname>" \\'
  echo '    -addext "subjectAltName=DNS:<your-hostname>,IP:<your-ip>"'
  exit 1
fi

if [[ -z "${CAAMS_SECRET_KEY:-}" ]]; then
  echo "WARNING: CAAMS_SECRET_KEY is not set — using insecure default. Set it before going to production:"
  echo "  export CAAMS_SECRET_KEY=\"\$(python3 -c 'import secrets; print(secrets.token_hex(32))')\""
fi

#fire up web server with ssl & port
exec uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --ssl-certfile "$CERT" \
  --ssl-keyfile "$KEY"

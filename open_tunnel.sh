#!/bin/bash
# Open the SSH tunnel to the rented GPU's vLLM server, and keep it open.
#
# Why a tunnel rather than the public port: Vast.ai fronts every externally
# exposed port with a Caddy reverse proxy that requires HTTP Basic authentication.
# vLLM requires a Bearer token. There is only one Authorization header, and the
# BFCL harness builds its client as OpenAI(base_url, api_key) with no way to add a
# second auth scheme -- and we cannot patch it, because it lives under gorilla/.
# SSH bypasses Caddy entirely and also keeps the model endpoint off the open
# internet.
#
# Instance 47425997 (machine 36444807). Port 311 -> container port 22.
# vLLM listens on the container's 127.0.0.1:18000, NOT :8000 (that is Caddy).

set -euo pipefail

HOST=${VAST_HOST:?set VAST_HOST}
SSH_PORT=${VAST_SSH_PORT:?set VAST_SSH_PORT}
LOCAL_PORT=18000
REMOTE_PORT=18000

# -N: no remote command, just forward. -T: no pty.
# ExitOnForwardFailure makes a port collision a loud error rather than a tunnel
# that silently forwards nothing.
exec ssh -N -T \
  -p "$SSH_PORT" \
  -i ~/.ssh/id_ed25519 \
  -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=4 \
  -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
  "root@${HOST}"

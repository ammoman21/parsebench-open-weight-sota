#!/bin/bash
# Wait for the ParseBench parity run to finish, then release the rented GPU.
#
# WHY THIS EXISTS: the benchmark client runs on the Mac and talks to the GPU over an
# SSH tunnel. When the run ends, the instance keeps billing at ~$3/hour until something
# releases it. This watches the run and releases it automatically.
#
# SETUP (one time) — get your key from https://cloud.vast.ai/account/
#   export VAST_API_KEY=...        # or: echo '<key>' > ~/.vast_api_key
#   ./auto_teardown.sh &           # leave it running; safe to background and forget
#
# MODE:
#   destroy (default) — instance deleted, billing stops completely. IRREVERSIBLE.
#                       Fine here: all results are written on the Mac, and the model
#                       weights re-download in ~4 min on this host's 2.6 Gbps link.
#   stop            — compute billing stops, but the 200 GB disk keeps billing
#                     (~$0.03/hr). Keeps the cached weights and setup.
#
# Override with:  MODE=stop ./auto_teardown.sh &

set -uo pipefail
cd "$(dirname "$0")"

INSTANCE_ID=${VAST_INSTANCE_ID:?set VAST_INSTANCE_ID}
MODE="${MODE:-destroy}"
LOG=teardown.log
RUN_LOG=parsebench/parity_run.log

KEY="${VAST_API_KEY:-}"
[ -z "$KEY" ] && [ -f "$HOME/.vast_api_key" ] && KEY="$(tr -d '[:space:]' < "$HOME/.vast_api_key")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

if [ -z "$KEY" ]; then
  log "REFUSING TO START: no VAST_API_KEY and no ~/.vast_api_key."
  log "Get a key at https://cloud.vast.ai/account/ then re-run. Instance $INSTANCE_ID is still billing."
  exit 1
fi

log "watching for parity run completion (instance $INSTANCE_ID, mode=$MODE)"

# 1. Wait for the run to finish. Two independent signals so a crashed run still
#    triggers teardown rather than billing all night.
while true; do
  if grep -q "=== .*DONE ===" "$RUN_LOG" 2>/dev/null; then
    log "run log reports DONE"; break
  fi
  if ! pgrep -f "bash ./run_parity.sh" > /dev/null 2>&1 \
     && ! pgrep -f "parse-bench run" > /dev/null 2>&1; then
    log "no run process alive (crashed, killed, or finished without the DONE marker)"; break
  fi
  sleep 60
done

# 2. Confirm results actually landed locally before destroying anything.
FOUND=$(ls parsebench/output/kdl_frontier_nano/*/_evaluation_report.json 2>/dev/null | wc -l | tr -d ' ')
log "evaluation reports found locally: $FOUND (expect 5 for a complete run)"
if [ "$MODE" = "destroy" ] && [ "$FOUND" -eq 0 ]; then
  log "NO results on disk — downgrading destroy -> stop so nothing is lost. Inspect, then release manually."
  MODE=stop
fi

# 3. Release.
API="https://console.vast.ai/api/v0/instances/${INSTANCE_ID}/"
if [ "$MODE" = "destroy" ]; then
  log "destroying instance $INSTANCE_ID"
  RESP=$(curl -s -w '\n%{http_code}' -X DELETE "$API" \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json")
else
  log "stopping instance $INSTANCE_ID"
  RESP=$(curl -s -w '\n%{http_code}' -X PUT "$API" \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"state":"stopped"}')
fi
CODE=$(echo "$RESP" | tail -1); BODY=$(echo "$RESP" | sed '$d')
log "HTTP $CODE  $BODY"

if [ "$CODE" = "200" ]; then
  log "SUCCESS: instance released ($MODE). Billing stopped."
else
  log "FAILED to release. RELEASE IT MANUALLY at https://cloud.vast.ai/instances/ — it is still billing."
fi

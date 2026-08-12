# Track A environment. Usage:  source track_a_env.sh
#
# Assumes the SSH tunnel from open_tunnel.sh is already running.
# Every variable here exists because the harness reads it via os.getenv at import
# time. Setting them in the shell (rather than in a .env file) keeps gorilla/
# untouched, which CLAUDE.md rule 5 requires. Note the harness calls
# load_dotenv(override=True), so a .env file would silently BEAT these exports.

# Where the harness writes result/, score/, .file_locks/ and looks for .env.
# WITHOUT this, all of that is written INSIDE gorilla/ (the pinned upstream
# checkout we are forbidden to modify). Defined in
# gorilla/berkeley-function-call-leaderboard/bfcl_eval/constants/eval_config.py:20
export BFCL_PROJECT_ROOT="$HOME/forecasting_networks/bfcl-sprint/bfcl_runs"

# The SSH tunnel maps this local port to the container's 127.0.0.1:18000, where
# vLLM actually listens. We deliberately do NOT go through the instance's public
# port 31624: that is fronted by a Caddy reverse proxy demanding HTTP Basic auth,
# and the harness's OpenAI client can only send a Bearer token.
export LOCAL_SERVER_ENDPOINT="localhost"
export LOCAL_SERVER_PORT="18000"

# vLLM on this image is launched WITHOUT --api-key (the Caddy edge provides auth
# instead), so it accepts any token. The harness would send the literal string
# "EMPTY" by default, which is fine. Set explicitly so the value is on the record.
# (base_oss_handler.py:46 — variable is REMOTE_OPENAI_*, not OPENAI_*.)
export REMOTE_OPENAI_API_KEY="EMPTY"

echo "BFCL_PROJECT_ROOT = $BFCL_PROJECT_ROOT"
echo "model server      = http://$LOCAL_SERVER_ENDPOINT:$LOCAL_SERVER_PORT/v1 (via SSH tunnel)"

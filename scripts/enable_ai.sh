#!/usr/bin/env bash
# Turn the AI on, on the production server, after submission.
#
#   ./scripts/enable_ai.sh --status    what the server is doing and what it has spent
#   ./scripts/enable_ai.sh             put the key in place and switch AI on
#   ./scripts/enable_ai.sh --off       switch it back off (the key stays)
#
# Everything this needs is already deployed. The key is the only thing missing, and it
# is missing on purpose: the demo is a public URL, and before the guards below existed
# a stranger could have emptied the budget in about a minute by calling /run in a loop —
# six vision calls per run, and every run reset the per-run counter.
#
# What now stands in the way:
#   * POST /run and POST /settings/llm require SDOC_ADMIN_TOKEN
#   * /run refuses if one started in the last 20 seconds
#   * a CUMULATIVE spend ceiling (LLM_SPEND_CAP_USD, default $2.50) written to disk on
#     every call and surviving restarts. When it is reached the AI switches itself off
#     and stays off, whatever the switch says.
set -euo pipefail

HOST="${SDOC_HOST:-docmatch.tech}"
KEY_FILE="${SDOC_KEY_FILE:-$HOME/Desktop/Project/Hackaton-Averis/Hackaton-info/api-key.txt}"
SSH_KEY="${SDOC_SSH_KEY:-$HOME/.ssh/sdoc-key.pem}"
REMOTE="ubuntu@$HOST"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml"

status () {
  echo "-- $HOST --"
  # note: the body goes through an env var, not a pipe. `curl | python3 - <<EOF` looks
  # right and is not: the heredoc becomes python's stdin, so the piped body is lost.
  local body
  body=$(curl -fsS "https://$HOST/health") || { echo "  unreachable" >&2; return 1; }
  SDOC_HEALTH="$body" python3 - <<'PYEOF'
import json, os
d = json.loads(os.environ["SDOC_HEALTH"])
l = d["llm_detail"]
print("  version      %s" % d["version"])
print("  AI           %-4s key present: %s   (%s)"
      % ("ON" if l["enabled"] else "off", l["has_key"], l["source"]))
print("  spent        $%.4f of $%.2f over %d calls"
      % (l.get("total_usd", 0), l.get("cap_usd", 0), l.get("total_calls", 0)))
print("  per-run cap  %s calls" % l["budget"])
PYEOF
}

wait_healthy () {
  for _ in $(seq 1 25); do
    curl -fsS "https://$HOST/health" >/dev/null 2>&1 && return 0
    sleep 3
  done
  echo "the service did not come back — ssh in and check the logs" >&2
  return 1
}

case "${1:-}" in
  --status)
    status
    exit 0
    ;;
  --off)
    echo "switching AI off..."
    ssh -i "$SSH_KEY" "$REMOTE" \
      "cd averis-hackaton && $COMPOSE exec -T app python -c \"from src import config; config.set_llm_enabled(False)\"" \
      >/dev/null
    status
    exit 0
    ;;
esac

[ -f "$KEY_FILE" ] || { echo "no key file at $KEY_FILE (set SDOC_KEY_FILE)" >&2; exit 1; }
KEY=$(grep -oE 'sk-ant-[A-Za-z0-9_-]+' "$KEY_FILE" | head -1)
[ -n "$KEY" ] || { echo "no sk-ant- key found in $KEY_FILE" >&2; exit 1; }
ADMIN=$(openssl rand -hex 16)

echo "-> writing the key and a fresh admin token to $HOST"
KEY="$KEY" ADMIN="$ADMIN" ssh -i "$SSH_KEY" "$REMOTE" \
  "KEY='$KEY' ADMIN='$ADMIN' bash -s" <<'REMOTE'
set -euo pipefail
cd averis-hackaton
python3 - <<'PY'
import os, pathlib, re
p = pathlib.Path(".env")
t = p.read_text() if p.exists() else ""
for k, v in (("ANTHROPIC_API_KEY", os.environ["KEY"]),
             ("SDOC_ADMIN_TOKEN", os.environ["ADMIN"]),
             ("SDOC_LLM", "on")):
    if re.search(rf"(?m)^{k}=", t):
        t = re.sub(rf"(?m)^{k}=.*$", f"{k}={v}", t)
    else:
        t = t.rstrip("\n") + f"\n{k}={v}\n"
p.write_text(t)
p.chmod(0o600)
print("  .env updated")
PY
docker compose -f deploy/docker-compose.prod.yml up -d >/dev/null 2>&1
echo "  container restarted"
REMOTE

echo "-> waiting for it to come back"
wait_healthy
sleep 2
echo
status
echo
echo "-- the admin token for this server --"
echo "   $ADMIN"
echo
echo "   Re-run and the AI switch in the header will ask for it once and remember it in"
echo "   your browser. Nobody else can start a run or turn the spending on."
echo "   Keep it with the other credentials, not in git."
echo
echo "Switch it off again:  $0 --off"

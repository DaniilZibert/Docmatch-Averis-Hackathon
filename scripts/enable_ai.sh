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
# We asked the organizers whether the paid actions could sit behind a token. They said
# no — the prototype must be publicly accessible in full. So there is no lock on the
# door, and everything below is about making an unlocked door cheap to walk through:
#   * every AI answer is cached against the exact bytes of the request, so a second run
#     over the same documents costs nothing (measured: 6 paid calls, then 0)
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
echo "-> writing the key to $HOST"
KEY="$KEY" ssh -i "$SSH_KEY" "$REMOTE" \
  "KEY='$KEY' bash -s" <<'REMOTE'
set -euo pipefail
cd averis-hackaton
python3 - <<'PY'
import os, pathlib, re
p = pathlib.Path(".env")
t = p.read_text() if p.exists() else ""
for k, v in (("ANTHROPIC_API_KEY", os.environ["KEY"]),
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
echo "-- what protects the budget from here --"
echo "   The site is public and so is the AI switch: the organizers ruled that the"
echo "   prototype must be accessible in full, so anyone can press Re-run. What makes"
echo "   that affordable is that the answers are cached, the ceiling above is"
echo "   cumulative and survives restarts, and a run costs six calls at most."
echo
echo "   Watch it:            $0 --status"
echo "   Switch it off again: $0 --off"

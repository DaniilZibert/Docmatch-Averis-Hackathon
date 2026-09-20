# Running it in production

Everything about the deployed service: what exists, how a change reaches it, how to
turn the AI on, and how to take it all down. Replaces the three separate deploy notes
that used to disagree with each other.

**Live: <https://docmatch.tech>**

---

## 1. What is running

Provisioned 20 September 2026 in **ap-southeast-2** (Sydney), CLI profile `sdoc`. The
account id is deliberately not written here — this repository is public.

| resource | id | note |
|---|---|---|
| EC2 instance | `i-0c7ff1d36649f09e3` | t3.micro, Ubuntu 24.04, 16 GB gp3 encrypted |
| Elastic IP | **54.66.241.118** | the domain's A record points here |
| Security group | `sg-0ac5e3caa5fec55d0` | 22 from one address only, 80 + 443 open |
| Key pair | `sdoc-key` | private half at `~/.ssh/sdoc-key.pem` (Daniil's laptop) |
| EIP allocation | `eipalloc-08b3980fbe62c6c64` | release on teardown or it bills |
| Domain | `docmatch.tech` | free year from the GitHub Student Pack |

```bash
ssh -i ~/.ssh/sdoc-key.pem ubuntu@docmatch.tech
```

On the box: 2 GB swap (1 GB of RAM cannot start a container comfortably), Docker,
unattended security upgrades, IMDSv2 required, and a systemd timer that keeps the
service up to date.

Two containers: `app` (the service) behind `caddy` (TLS). No database, no queue, no
load balancer — the pipeline is a sub-second batch and keeps its results in memory.
`src/db/schema.sql` records the shape a persistent deployment would use.

### Costs

t3.micro and 16 GB of gp3 are inside the 12-month free tier. An Elastic IP is free
**while attached to a running instance** and billed hourly when it is not — stopping
the box overnight to save money starts costing money. Nothing else is provisioned; the
three things that quietly bill on AWS (load balancer, NAT gateway, RDS) are all absent.

---

## 2. How a change reaches production

```
git push origin main
   └─ test    228 tests, then a real pass over 520 emails, submission validated
   └─ build   build the image, prove the container starts, push to the GitLab registry
   └─ deploy  wait until /health reports this commit
                  ↑
        the server pulls it itself, within 60s, on a systemd timer
```

**There is no ssh anywhere in the pipeline, deliberately.** The security group opens
port 22 to a single address, and GitLab.com publishes no static IPs for shared runners
— its documentation says to allowlist "both AWS and Google Cloud IP ranges". A CI job
that sshs in therefore needs port 22 open to most of a cloud provider. Pulling inverts
the direction: nothing inbound, CI holds no credentials of any kind, and the deploy is
still verified rather than assumed.

The image carries the commit it was built from (`ARG GIT_SHA` → `SDOC_VERSION`), and
`/health` reports it. That is how the pipeline knows its own change went live, and how
you answer "which build am I looking at?" from a browser.

### GitLab CI variables

**Settings → CI/CD → Variables.** One variable, and it is not a secret:

| variable | value |
|---|---|
| `DEPLOY_HOST` | `docmatch.tech` |

`SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`, `DEPLOY_USER`, `DEPLOY_PATH` are left over from
the ssh design and are unused — delete them.

### The update timer

```bash
systemctl list-timers sdoc-update --no-pager   # when it next fires
journalctl -u sdoc-update -n 30                # what it did last time
sudo systemctl start sdoc-update.service       # force an update now
```

Units live in `deploy/systemd/`. On a fresh server:

```bash
sudo cp deploy/systemd/sdoc-update.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sdoc-update.timer
```

`docker compose up -d` is a no-op when the image digest has not moved, so the
steady-state cost of a one-minute timer is one registry HEAD request.

The registry serves anonymous pulls because the project is public. If it is ever made
private, run `docker login registry.gitlab.com` once on the server with a
`read_registry` deploy token — it persists in `~/.docker/config.json`. Do not thread
credentials through CI.

### Deploying by hand

From an address the security group allows:

```bash
ssh -i ~/.ssh/sdoc-key.pem ubuntu@docmatch.tech
cd averis-hackaton && git pull
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 3. The AI switch, and what stops it emptying the budget

**Claude is off, and there is no key on the server.** That is deliberate and it is not
only about cost discipline: the demo is a public URL, and until the guards below existed
a stranger could have emptied the whole budget in about a minute.

### Why a public URL with a key is dangerous by default

`POST /run` re-processes the inbox. With the AI on that is six vision calls — the
image-only scans — roughly $0.07 a time. It is a button, so anyone can press it. And
`store._run()` calls `reset_budget()` on every run, so `LLM_MAX_CALLS` is a *per-run*
number that a caller resets simply by calling again. Unprotected, a loop against `/run`
costs about $5 in sixty seconds.

**We asked the organizers whether the paid actions could sit behind a token. They said
no** — the prototype has to be publicly accessible, all of it. So the endpoints are
open, and the spending is defended somewhere else entirely.

### The three defences, none of which restricts anybody

**1. Every AI answer is cached on disk**, keyed by a hash of the model and the exact
request. The cache is not pre-filled — the first pass over any document is a genuine
call, because a demo that never calls the AI is not a demo of the AI. What it stops is
the *second* pass costing anything:

```
upload a pair of never-seen documents:   2 paid calls,  $0.0104
upload the identical files again:        0 paid calls,  $0.0000
change one line of the BL:               1 paid call   (the SI came from cache)
```

So somebody pressing `/run` in a loop pays for the first press and nothing after it, and
we did not have to take the button away from them.

**2. A cumulative spend ceiling** (`LLM_SPEND_CAP_USD`, default $2.50), written to disk
on every single call rather than at the end of a run — a process killed mid-run still
spent the money. It survives restarts and overrides the switch: a budget is a budget
whatever anybody clicked. When it trips the header reads `AI capped`.

**3. A 20-second cooldown on `/run`**, which throttles rather than denies. Everyone can
still press the button, just not a thousand times a second.

Limiting our own resource consumption is not the same as limiting access, and that
distinction is why this arrangement satisfies the rule.

### Uploads are the case where the AI genuinely earns its place

`/upload` lets anyone hand the system a document it has never seen. That is a real cost
vector and it is supposed to be: the rules parse the labels they recognise, Claude reads
the rest, and the ceiling is what bounds it. A booking note written entirely in
unfamiliar labels ("Party sending the goods", "Taking on board at", "Boxes in this lot")
came back with all seven fields, `seven x 40'HC` read as 7, the gross weight taken
rather than the net sitting beside it, and the planted discrepancy found — for about a
cent.

### The switch means off, cache included

When the AI is off the cache is not consulted either. That is deliberate: serving a
cached answer while reporting "rules only" would put vision results into the
deterministic column of the ablation table and silently turn a scan that *should*
escalate into one that passes. Off means off; the cache exists to stop a second run
costing money, not to smuggle answers past the switch.

### Turning it on, after submission

```bash
./scripts/enable_ai.sh --status      # what the server is doing and what it has spent
./scripts/enable_ai.sh               # key in place, AI on, fresh admin token printed
./scripts/enable_ai.sh --off         # back off; the key stays
```

The script writes the key and a freshly generated `SDOC_ADMIN_TOKEN` into the server's
`.env`, restarts, waits for health and prints the token. Keep that token with the other
credentials — the header's **Re-run** button and the AI switch ask for it once and
remember it in your browser.

In the header:

```
●  520 emails in 1.3s · no LLM calls    [ ○──  AI off ]    Re-run
●  520 emails in 1.3s · 6 calls         [ ──●  AI on   6 calls · $0.07 of $2.50 ]
```

The key goes in `.env` on the box and nowhere else — never in the repo, never in the
image, never in a CI variable. Confirm it arrived without printing it:

```bash
docker compose -f deploy/docker-compose.prod.yml exec app env | grep -c ANTHROPIC_API_KEY
```

### If the ceiling trips

```bash
# raise it
ssh -i ~/.ssh/sdoc-key.pem ubuntu@docmatch.tech
cd averis-hackaton && sed -i 's/^LLM_SPEND_CAP_USD=.*/LLM_SPEND_CAP_USD=5.00/' .env
docker compose -f deploy/docker-compose.prod.yml up -d
```

Clearing the ledger instead of raising the ceiling is possible (`config.reset_spend()`)
but it throws away the record of what has actually been spent. Raise the number.

## 4. When it does not work

| symptom | cause |
|---|---|
| a variable in `.env` seems ignored | compose reads `.env` from the **compose file's** directory, not your shell's. The services pull `../.env` through `env_file` for exactly this reason — check `exec app printenv` before assuming the app is wrong |
| the site loads on http, no padlock | `SDOC_DOMAIN` did not reach the container. `exec caddy printenv SDOC_DOMAIN` — a setting that never arrived and a certificate that failed look identical from a browser |
| Caddy logs `could not get certificate` | DNS was not ready when it tried. Fix DNS, then `docker compose restart caddy` |
| `too many failed authorizations` | Let's Encrypt rate-limited you for retrying against broken DNS. Wait an hour |
| ssh times out | the security group pins port 22 to one address and your home IP changed — see below. Do **not** open 22 to `0.0.0.0/0`; scanners find it within minutes |
| deploy job times out waiting for its commit | the timer is not running (`systemctl status sdoc-update.timer`) or the pull failed (`journalctl -u sdoc-update -n 40`) |
| a deploy is slow | the timer fires once a minute, so up to 60s plus the restart. That is the price of not exposing ssh |
| `AI no key` and you expected otherwise | no key in the server's `.env`, or `LLM_MAX_CALLS=0` |
| the switch forgets itself on restart | the `sdoc_state` volume is not writable by the container user — `logs app` says so outright |
| the first `up` gets killed silently | no swap on a 1 GB box |

### Your IP changed

```bash
export AWS_PROFILE=sdoc AWS_REGION=ap-southeast-2
MYIP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id sg-0ac5e3caa5fec55d0 \
  --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=${MYIP}/32}]"
```

---

## 5. Two traps worth remembering

Both cost real pipeline runs, and neither is visible from reading the config.

**An escaped variable in an unquoted ssh heredoc resolves on the SERVER.** The runner
expands the heredoc, which is what you want for CI variables; writing `\$VAR` sends the
name literally and the server resolves it against its own empty environment. That is
how a deploy job spent three runs failing inside its own `docker login`.

**`curl -f` counts a redirect as success.** Once Caddy has a certificate it answers
port 80 with a 308, so a health check that does not follow redirects goes green while
the app behind it is down. Match on the response body, not the exit code.

---

## 6. Rebuilding or tearing down

The domain and the key pair survive; everything else is one command each.

```bash
export AWS_PROFILE=sdoc AWS_REGION=ap-southeast-2
aws ec2 terminate-instances --instance-ids i-0c7ff1d36649f09e3
aws ec2 wait instance-terminated --instance-ids i-0c7ff1d36649f09e3
aws ec2 release-address --allocation-id eipalloc-08b3980fbe62c6c64
aws ec2 delete-security-group --group-id sg-0ac5e3caa5fec55d0
aws ec2 delete-key-pair --key-name sdoc-key
```

If you rebuild: allocate a new Elastic IP, point the `.tech` A record at it, wait for
`dig +short docmatch.tech` to return it **before** starting Caddy, then reinstall the
systemd timer.

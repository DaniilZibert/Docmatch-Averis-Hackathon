# Putting the service on the internet

> **Already done once.** The instance, Elastic IP, security group and key are
> provisioned — see [aws-resources.md](aws-resources.md) for the ids and the teardown
> commands. This document is how it was done and how to do it again.

Goal: a URL a judge can open on their phone, with HTTPS and a real hostname, that keeps
working after we close our laptops.

The whole service is one container. It needs no database and no queue, so the smallest
instance AWS offers is genuinely enough — the pipeline processes all 520 emails in about
1.5 seconds and then serves pages out of memory.

---

## Before you start: what the Student Pack actually gives you

**Check what is in yours at <https://education.github.com/pack> before planning around
it — the offers change, and the ones below are what to look for rather than a promise.**

| you need | where it usually comes from |
|---|---|
| a server | **AWS Free Tier** — `t3.micro`, 750 hours/month for the first 12 months. This is enough on its own; AWS credits from the pack are a bonus, not a requirement. |
| a domain | **Namecheap** (free `.me` for a year) or **`.tech`** (free domain for a year), both in the pack. Any registrar works — you only need to point one A record. |
| TLS | free and automatic, from Let's Encrypt via Caddy. Nothing to buy. |

If AWS turns into a fight over billing verification, **DigitalOcean's $200 pack credit
and a $6 droplet** run these exact same commands. Do not lose an evening to an account
problem the day before judging.

---

## 1. The instance

EC2 → Launch instance:

- **AMI** Ubuntu Server 24.04 LTS
- **Type** `t3.micro` (free tier). `t3.small` if you want the LLM paths to feel snappy.
- **Key pair** create one and keep the `.pem` — it is the only way back in.
- **Storage** 16 GB gp3
- **Security group** — exactly three rules inbound:

  | port | source | why |
  |---|---|---|
  | 22 | **your IP only** | ssh. Never `0.0.0.0/0`. |
  | 80 | `0.0.0.0/0` | Let's Encrypt validates over http, then Caddy redirects |
  | 443 | `0.0.0.0/0` | the actual site |

Allocate an **Elastic IP** and associate it. Without one the address changes on every
stop/start and your DNS record goes stale mid-event.

## 2. The domain — a free `.tech` from the Student Pack

> Step by step, with the real IP filled in: **[domain-tech.md](domain-tech.md)**.

The GitHub Student Developer Pack includes a free `.tech` domain for a year. Claim it
at <https://get.tech/github-student-developer-pack> (sign in with GitHub so it can see
your student status) and pick something short — `averis-sdoc.tech`, `sdoc-check.tech`.
You will be reading it out loud to judges.

Then, in the **.tech dashboard → Manage → DNS records**, add one record:

| type | host | value | TTL |
|---|---|---|---|
| A | `@` | *the Elastic IP* | 300 |

Add a second one for `www` if you want it, same value. That is all — no nameserver
change, no CNAME, nothing else.

**Do this before you deploy.** DNS takes a few minutes and Caddy cannot get a
certificate until the name resolves to the box. Check from your laptop:

```bash
dig +short averis-sdoc.tech          # must print your Elastic IP
```

If it prints nothing after ten minutes, the record has not propagated; wait, do not
start changing things.

> Registering a domain at `.tech` puts your name and address in WHOIS. Turn on the free
> privacy protection in the dashboard.

## 3. Docker

```bash
ssh -i <key>.pem ubuntu@<elastic-ip>

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit          # log back in so the group takes effect
```

## 4. The service

```bash
ssh -i <key>.pem ubuntu@<elastic-ip>

# a t3.micro has 1 GB of RAM. Give it swap before anything else, or the first
# container start will be an unexplained kill.
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

git clone https://gitlab.com/daniilz2018/averis-hackaton.git
cd averis-hackaton
# private repo? GitLab → Settings → Repository → Deploy tokens (read_repository), then
#   git clone https://<token-user>:<token>@gitlab.com/daniilz2018/averis-hackaton.git
# Do not put a personal SSH key on a server judges can reach.

cp .env.example .env
nano .env
#   SDOC_DOMAIN=averis-sdoc.tech
#   SDOC_LLM=off                 leave it off; you turn Claude on from the UI
#   ANTHROPIC_API_KEY=...        optional — see "the Claude switch" below

docker compose -f deploy/docker-compose.prod.yml up -d --build
```

The first build takes a few minutes (CI builds the image for you after this, so this is
the only time you wait). Then:

```bash
curl -s https://averis-sdoc.tech/health
docker compose -f deploy/docker-compose.prod.yml logs -f --tail=50
```

`/health` reporting `"run": {"status": "ready", "processed": 520}` means it is done.

## 5. Check it the way a judge will

Open `https://sdoc.<your-domain>` in a browser you have never used for this and walk the
actual path: overview → a case that needs a person → open the SI and the BL → settle it →
watch the report change. If any of that needs a terminal, it is not finished.

---

## The Claude switch

**The service does not need a key.** With none it runs rules-only, scores exactly the
same on the sample data, and says `"llm": "rules-only"` on `/health`. Everything it
cannot read deterministically is escalated to a person with the evidence — correct
behaviour, not a degraded mode.

Even with a key present, **Claude is off until somebody turns it on.** There is a switch
in the header of every screen:

```
●  520 emails in 1.3s · no LLM calls    [ ○──  Claude off ]    Re-run
```

Click it and it goes green, shows the calls made and the running cost, and the scanned
documents start going to vision. Click it again and it stops. No redeploy, no ssh, and
the setting is written to the `sdoc_state` volume so it survives a restart — including a
CI deploy.

That is the answer to "don't burn the budget for nothing": leave it off, turn it on for
the two minutes of the demo where you show a scanned BL being read, turn it off after.

Belt and braces around it:

- `SDOC_LLM=off` in `.env` is the default the container starts with. The switch, once
  used, overrides it and persists.
- `LLM_MAX_CALLS` (default 40) caps calls per run whatever the switch says. A public URL
  with an unmetered key behind it is a way to donate a budget to a crawler.
- CI never spends: `.gitlab-ci.yml` pins `SDOC_LLM=off` and `LLM_MAX_CALLS=0`, and the
  test suite disables it independently in `tests/conftest.py`.
- The key goes in `.env` on the box, or in a Protected CI variable — never in the repo
  and never baked into the image. Confirm it arrived without printing it:
  `docker compose -f deploy/docker-compose.prod.yml exec app env | grep -c ANTHROPIC_API_KEY`

## CI/CD

`.gitlab-ci.yml` runs on every push: the 197 tests, then a real pass over all 520 emails
with the submission validated for shape. On `main` it also builds the image, proves the
container actually starts, and pushes it to the GitLab registry.

**The deploy is a pull, not a push, and there is no ssh anywhere in the pipeline.**

The server runs a one-minute systemd timer (`deploy/systemd/`) that pulls `:latest` and
restarts if the digest moved. The image carries the commit it was built from, `/health`
reports it, and the deploy job simply waits until it sees its own commit go live.

This is not a stylistic preference. The security group opens port 22 to a single
address, and GitLab.com publishes **no static IPs** for its shared runners — the
documentation says to allowlist "both AWS and Google Cloud IP ranges". A CI job that
sshs in therefore needs port 22 open to most of a cloud provider. Pulling inverts the
direction: nothing inbound, CI holds no credentials of any kind, and the deploy is
still verified rather than assumed.

The first version of this pipeline did ssh in, and failed every single run. The
server's `auth.log` was what settled it — a GitLab runner had never connected at all.

### The one variable

**Settings → CI/CD → Variables:**

| variable | value | secret? |
|---|---|---|
| `DEPLOY_HOST` | `docmatch.tech` | no |

That is the whole list. `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`, `DEPLOY_USER` and
`DEPLOY_PATH` are no longer used — delete them.

### Installing the timer on a new server

```bash
sudo cp deploy/systemd/sdoc-update.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sdoc-update.timer

systemctl list-timers sdoc-update --no-pager     # when it next fires
journalctl -u sdoc-update -n 30                  # what it did last time
sudo systemctl start sdoc-update.service         # force an update now
```

The registry is public for a public project, so the timer needs no credentials. If the
repository is ever made private, run `docker login registry.gitlab.com` once on the
server with a `read_registry` deploy token; it persists in `~/.docker/config.json`.

## When it does not work

| symptom | cause |
|---|---|
| browser cannot connect at all | security group is missing 80/443, or the Elastic IP is not associated |
| connects on http, no certificate | DNS has not propagated yet, or `SDOC_DOMAIN` still says `:80` |
| `/health` shows `"processed": 0` | the run failed — `logs app` will have the traceback |
| pages are slow the first few seconds after a deploy | the startup run is still going; the page refreshes itself |
| a variable in `.env` seems ignored | compose reads `.env` from the compose file's directory, not your shell's. The services pull `../.env` through `env_file` for exactly this reason — check `exec app printenv` before assuming the app is wrong |
| `"llm": "rules-only"` and you expected otherwise | the switch is off (click it in the header), or there is no key in `.env`, or `LLM_MAX_CALLS=0` |
| the Claude switch forgets itself on restart | the `sdoc_state` volume is not writable by the container user — `logs app` will say so outright |
| the first `up` gets killed with no message | no swap on a 1 GB box; see step 4 |
| deploy job times out waiting for its commit | the timer is not running (`systemctl status sdoc-update.timer`), or the pull failed (`journalctl -u sdoc-update -n 40`) |
| a deploy takes longer than expected | the timer fires once a minute, so up to 60s plus the restart. That is the price of not exposing ssh |

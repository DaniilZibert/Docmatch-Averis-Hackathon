# Putting the service on the internet

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

## 2. The domain

At your registrar, one record:

```
A    sdoc.<your-domain>    <the Elastic IP>    TTL 300
```

Do this first — DNS takes a few minutes to propagate and Caddy cannot issue a
certificate until it resolves. Check with `dig +short sdoc.<your-domain>`.

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
git clone https://gitlab.com/daniilz2018/averis-hackaton.git
cd averis-hackaton
# private repo? GitLab → Settings → Repository → Deploy tokens (read_repository), then
#   git clone https://<token-user>:<token>@gitlab.com/daniilz2018/averis-hackaton.git
# Do not put a personal SSH key on a server judges can reach.

cp .env.example .env
nano .env
#   SDOC_DOMAIN=sdoc.<your-domain>
#   ANTHROPIC_API_KEY=...        optional — see the note below
#   LLM_MAX_CALLS=40

docker compose -f deploy/docker-compose.prod.yml up -d --build
```

First build takes a few minutes. Then:

```bash
curl -s https://sdoc.<your-domain>/health
docker compose -f deploy/docker-compose.prod.yml logs -f --tail=50
```

`/health` reporting `"run": {"status": "ready", "processed": 520}` means it is done.

## 5. Check it the way a judge will

Open `https://sdoc.<your-domain>` in a browser you have never used for this and walk the
actual path: overview → a case that needs a person → open the SI and the BL → settle it →
watch the report change. If any of that needs a terminal, it is not finished.

---

## About the API key in production

**The service does not need one.** With no key it runs rules-only, scores the same on
the sample data, and says `"llm": "rules-only"` on `/health`. Everything it cannot read
deterministically is escalated to a person with the evidence — which is correct
behaviour, not a degraded mode.

Put the key on the server only if you want the scanned-document path live in the demo.
If you do:

- it goes in `.env` on the box and nowhere else — never in the repo, never in the image;
- keep `LLM_MAX_CALLS` set. A public URL with an unmetered key on it is a way to lose a
  budget to a crawler;
- `docker compose ... exec app env | grep -c ANTHROPIC_API_KEY` to confirm it arrived,
  which prints a count rather than the key.

## Operations

```bash
# deploy a change
git pull && docker compose -f deploy/docker-compose.prod.yml up -d --build

# re-process the inbox without a restart
curl -X POST https://sdoc.<your-domain>/run

# logs, and the certificate Caddy issued
docker compose -f deploy/docker-compose.prod.yml logs --tail=100 caddy
docker compose -f deploy/docker-compose.prod.yml exec caddy ls /data/caddy/certificates
```

The Caddy certificates live in the `caddy_data` volume. Keep it across rebuilds or
Let's Encrypt will rate-limit you for re-issuing.

## When it does not work

| symptom | cause |
|---|---|
| browser cannot connect at all | security group is missing 80/443, or the Elastic IP is not associated |
| connects on http, no certificate | DNS has not propagated yet, or `SDOC_DOMAIN` still says `:80` |
| `/health` shows `"processed": 0` | the run failed — `logs app` will have the traceback |
| pages are slow the first few seconds after a deploy | the startup run is still going; the page refreshes itself |
| `"llm": "rules-only"` and you expected otherwise | the key is not in `.env` on the server, or `LLM_MAX_CALLS=0` |

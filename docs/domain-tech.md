# Pointing a free .tech domain at the service

The GitHub Student Developer Pack includes one free `.tech` domain for a year. Five
minutes of work, and it is what turns "here is an IP address" into something a judge
will open on their phone.

**The address to point at: `54.66.241.118`**

---

## 1. Claim the domain

<https://get.tech/github-student-developer-pack> — sign in with the GitHub account that
has the Student Pack, and it verifies your student status automatically.

Pick something short and sayable. You will be reading it out loud:

    averis-sdoc.tech        sdoc-check.tech        bl-check.tech

Avoid hyphens if you can and avoid anything you would have to spell out. At checkout
the price should be **$0.00** for the first year — if it is not, the Student Pack offer
did not attach and you should go back through the link above rather than paying.

Turn on the free WHOIS privacy while you are there. Registering a domain otherwise puts
your name and home address in a public database.

## 2. One DNS record

In the .tech dashboard: **My Products → the domain → Manage → DNS Records**.

Delete the parking/redirect record they add by default, then create:

| Type | Host / Name | Value / Points to | TTL |
|---|---|---|---|
| A | `@` | `54.66.241.118` | 300 |

Add a second identical row with host `www` if you want `www.` to work too.

That is the whole change. No nameserver switch, no CNAME, nothing else. Leave the
nameservers on .tech's defaults.

## 3. Wait for it to resolve

```bash
dig +short yourname.tech
# must print: 54.66.241.118
```

Usually a couple of minutes, occasionally up to an hour. **Do not go to step 4 until
this prints the right address** — Caddy asks Let's Encrypt for a certificate, Let's
Encrypt checks the name resolves to the box asking, and a failed check counts against a
rate limit that will lock you out for hours.

## 4. Tell the service its name

```bash
ssh -i ~/.ssh/sdoc-key.pem ubuntu@54.66.241.118
cd averis-hackaton
sed -i 's|^SDOC_DOMAIN=.*|SDOC_DOMAIN=yourname.tech|' .env
docker compose -f deploy/docker-compose.prod.yml up -d
docker compose -f deploy/docker-compose.prod.yml logs -f caddy
```

Caddy will say `certificate obtained successfully` within about thirty seconds. Then:

```bash
curl -s https://yourname.tech/health
```

HTTP redirects to HTTPS automatically. The certificate renews itself.

## If it does not work

| what you see | what it is |
|---|---|
| `dig` prints nothing | the record has not propagated — wait, do not change things |
| `dig` prints a different IP | the parking record is still there; delete it |
| Caddy logs `could not get certificate` | DNS was not ready when it tried. Fix DNS, then `docker compose restart caddy` |
| `too many failed authorizations` | Let's Encrypt rate-limited you for retrying against broken DNS. Wait an hour; it clears |
| the site loads on http but not https | `SDOC_DOMAIN` is still `:80` in `.env` |

## Also update, once the domain works

- `DEPLOY_HOST` in the GitLab CI variables, so the deploy job's health check uses the
  name rather than the IP.
- The security group does **not** need changing. DNS points at the same address.

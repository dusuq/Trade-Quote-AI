# Cloudflare edge — T309 / M24

Terraform for the public edge: DNS, TLS posture, WAF, rate limits, cache policy.

## What's public, and what isn't

| Hostname       | Points at                | Proxied         |
| -------------- | ------------------------ | --------------- |
| `api.<domain>` | Fly.io `api-gateway` app | ✅ orange cloud |
| `app.<domain>` | Vercel (`apps/web`)      | ✅ orange cloud |

The other 11 services have **no DNS record at all**. They're reachable only from
the gateway over Fly's private `.internal` network. Adding a record for one of
them is an architecture change — take it through review, not through a
`terraform apply`.

Both records must stay **proxied**. A grey-cloud record bypasses the WAF, the
rate limits, and the cache policy in this directory, silently.

## Apply

```bash
export TF_VAR_cloudflare_api_token="<zone-scoped token>"
cd infra/cloudflare
terraform init
terraform plan     # always read the plan; DNS mistakes are user-visible instantly
terraform apply
```

The token needs exactly `Zone:Read`, `DNS:Edit`, and `Firewall Services:Edit`,
scoped to the one zone. A global API key works and is a bad idea.

## Decisions worth knowing before you edit

- **`ssl = "strict"`** — requires a real cert on the origin. Fly provides one.
  Downgrading to `flexible` or `full` allows an unauthenticated MITM between
  Cloudflare and the origin, which defeats the point of TLS.
- **Payment webhooks skip bot protection.** `/v1/payments/webhooks/*` is
  explicitly exempted from challenges. Stripe and Square are bots by definition
  and cannot solve a JS challenge — without the skip, real webhooks get dropped.
  This is safe because `payment-service` verifies the provider HMAC itself and
  fails closed (see the T303 audit); authenticity never depended on Cloudflare.
- **The API is never cached.** A cached tenant-scoped response served to a
  different tenant is a data breach. Static assets come from Vercel's CDN on a
  different hostname, so there's nothing to gain here anyway.
- **No geo-blocking.** Deliberate: contractors travel, and the product has no
  jurisdictional restriction. Recorded so the absence reads as a decision.
- **Login throttle is 10/min/IP**, on top of the gateway's own rate limiting.
  Edge-side throttling means credential-stuffing traffic never reaches (or
  bills) the origin.

## State

Local state only, for now — `*.tfstate` is gitignored. That means **one
operator at a time**, and losing the file means re-importing resources. Move to
the S3 backend (commented at the top of `main.tf`) before more than one person
touches this.

## Not covered here

- Fly.io app provisioning → `infra/services.yml` + `fly.toml` per unit
- Monitoring/alerting → `infra/monitoring/`
- Vercel project config → managed in the Vercel dashboard (not yet IaC)

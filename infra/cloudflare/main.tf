#-----------------------------------------------------------------------------
# TradeQuote AI — Cloudflare edge configuration (T309 / M24)
#
# What sits where:
#   api.<domain>  → proxied CNAME to the Fly api-gateway app (public edge)
#   app.<domain>  → proxied CNAME to Vercel (apps/web)
#
# Nothing else is public. The 11 domain services are only reachable over Fly's
# private .internal network from the gateway, so they have no DNS record here
# by design — if you find yourself adding one, that's an architecture change,
# not a config tweak.
#
# State: Terraform state contains resource IDs, not secrets, but it is still
# gitignored (*.tfstate in .gitignore). Use a remote backend for real
# environments — see the commented backend block below.
#-----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.6"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }

  # Uncomment and fill in once a shared state bucket exists. Until then this is
  # local-state only, which means: one operator at a time, and don't lose the
  # file. Documented rather than silently assumed.
  #
  # backend "s3" {
  #   bucket = "tradequote-tfstate"
  #   key    = "cloudflare/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "cloudflare" {
  # Sourced from CLOUDFLARE_API_TOKEN. Never hardcode; the token needs
  # Zone:Read, DNS:Edit, and Firewall Services:Edit on this zone only.
  api_token = var.cloudflare_api_token
}

#-----------------------------------------------------------------------------
# DNS
#-----------------------------------------------------------------------------

# Public API edge. Proxied (orange cloud) so Cloudflare terminates TLS and the
# WAF/rate-limit rules below actually apply — a grey-cloud record would bypass
# every protection in this file.
resource "cloudflare_record" "api" {
  zone_id = var.zone_id
  name    = "api"
  type    = "CNAME"
  content = var.fly_gateway_hostname
  proxied = true
  ttl     = 1 # must be 1 (automatic) when proxied
  comment = "T309: API gateway on Fly.io — public edge"
}

# Web app on Vercel.
resource "cloudflare_record" "app" {
  zone_id = var.zone_id
  name    = "app"
  type    = "CNAME"
  content = var.vercel_hostname
  proxied = true
  ttl     = 1
  comment = "T309: Next.js web app on Vercel"
}

#-----------------------------------------------------------------------------
# Zone-level TLS / security posture
#-----------------------------------------------------------------------------

resource "cloudflare_zone_settings_override" "tradequote" {
  zone_id = var.zone_id

  settings {
    # "strict" requires a valid cert on the origin. Fly issues real certs, so
    # anything weaker (flexible/full) would allow an unauthenticated MITM
    # between Cloudflare and the origin.
    ssl                      = "strict"
    always_use_https         = "on"
    min_tls_version          = "1.2"
    tls_1_3                  = "on"
    automatic_https_rewrites = "on"
    opportunistic_encryption = "on"

    # HSTS: browsers refuse plaintext for a year, including subdomains.
    security_header {
      enabled            = true
      preload            = true
      max_age            = 31536000
      include_subdomains = true
      nosniff            = true
    }

    browser_check  = "on"
    security_level = "medium"
    challenge_ttl  = 1800
  }
}

#-----------------------------------------------------------------------------
# Rate limiting (WAF ruleset)
#-----------------------------------------------------------------------------

resource "cloudflare_ruleset" "api_rate_limits" {
  zone_id     = var.zone_id
  name        = "TradeQuote API rate limits"
  description = "T309: per-IP throttles on abuse-prone endpoints"
  kind        = "zone"
  phase       = "http_ratelimit"

  # Login is the credential-stuffing target. 10/min per IP is generous for a
  # human and hostile to a script. The gateway also rate-limits, but doing it
  # at the edge means the traffic never reaches (or bills) our origin.
  rules {
    action      = "block"
    description = "Throttle auth login attempts"
    expression  = "(http.request.uri.path contains \"/v1/auth/login\")"
    enabled     = true

    ratelimit {
      characteristics     = ["ip.src", "cf.colo.id"]
      period              = 60
      requests_per_period = 10
      mitigation_timeout  = 600
    }
  }

  # Broad API ceiling — catches scrapers without touching normal app usage.
  rules {
    action      = "block"
    description = "General API ceiling per IP"
    expression  = "(http.request.uri.path contains \"/v1/\")"
    enabled     = true

    ratelimit {
      characteristics     = ["ip.src", "cf.colo.id"]
      period              = 60
      requests_per_period = 600
      mitigation_timeout  = 60
    }
  }
}

#-----------------------------------------------------------------------------
# WAF custom rules
#-----------------------------------------------------------------------------

resource "cloudflare_ruleset" "api_waf" {
  zone_id     = var.zone_id
  name        = "TradeQuote WAF"
  description = "T309: custom firewall rules for the API edge"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  # Payment provider webhooks must NOT be challenged — Stripe and Square are
  # bots by definition and cannot solve a JS challenge. Skipping here is safe
  # because payment-service verifies the provider HMAC signature itself
  # (fail-closed; see the T303 audit), so authenticity does not depend on
  # Cloudflare. Without this skip, real webhooks get challenged and dropped.
  rules {
    action      = "skip"
    description = "Allow provider webhooks to bypass bot challenges"
    expression  = "(http.request.uri.path contains \"/v1/payments/webhooks/\")"
    enabled     = true

    action_parameters {
      ruleset = "current"
      phases  = ["http_ratelimit", "http_request_firewall_managed"]
      products = ["bic", "waf"]
    }
  }

  # Block requests that aren't valid HTTP methods for this API surface.
  rules {
    action      = "block"
    description = "Block unsupported HTTP methods"
    expression  = "(not http.request.method in {\"GET\" \"POST\" \"PUT\" \"PATCH\" \"DELETE\" \"OPTIONS\" \"HEAD\"})"
    enabled     = true
  }

  # Internal/ops paths should never be reachable from the public internet.
  # Defence in depth: the gateway doesn't route these either.
  rules {
    action      = "block"
    description = "Block internal and ops paths at the edge"
    expression  = "(http.request.uri.path contains \"/internal/\" or http.request.uri.path contains \"/metrics\" or http.request.uri.path contains \"/actuator\")"
    enabled     = true
  }

  # Geo-blocking is intentionally NOT enabled: contractors travel and the
  # product has no jurisdictional restriction. Recorded so the omission reads
  # as a decision rather than an oversight.
}

#-----------------------------------------------------------------------------
# Caching
#-----------------------------------------------------------------------------

resource "cloudflare_ruleset" "api_cache" {
  zone_id     = var.zone_id
  name        = "TradeQuote cache policy"
  description = "T309: never cache authenticated API responses"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  # A cached tenant-scoped response served to another tenant is a data breach.
  # The API is uncacheable, full stop; static assets are served from Vercel's
  # own CDN, not this hostname.
  rules {
    action      = "set_cache_settings"
    description = "Bypass cache for all API traffic"
    expression  = "(http.host eq \"${var.api_hostname}\")"
    enabled     = true

    action_parameters {
      cache = false
    }
  }
}

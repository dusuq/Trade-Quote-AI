#-----------------------------------------------------------------------------
# TradeQuote AI — Cloudflare input variables (T309 / M24)
#
# No defaults for anything account-specific: a wrong-but-plausible default is
# how you accidentally point production DNS at someone else's zone.
#-----------------------------------------------------------------------------

variable "cloudflare_api_token" {
  description = "Cloudflare API token, scoped to this zone only (Zone:Read, DNS:Edit, Firewall Services:Edit). Supply via TF_VAR_cloudflare_api_token or CI secret — never a .tfvars file in git."
  type        = string
  sensitive   = true
}

variable "zone_id" {
  description = "Cloudflare Zone ID for the TradeQuote AI domain."
  type        = string
}

variable "api_hostname" {
  description = "Public FQDN of the API edge, e.g. api.tradequote.ai. Must match the cloudflare_record.api name + zone."
  type        = string
}

variable "fly_gateway_hostname" {
  description = "Fly.io hostname for the api-gateway app, e.g. tradequote-api-gateway.fly.dev."
  type        = string
}

variable "vercel_hostname" {
  description = "Vercel hostname for apps/web, e.g. cname.vercel-dns.com."
  type        = string
  default     = "cname.vercel-dns.com"
}

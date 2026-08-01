import { apiFetch } from "@/lib/api-client";

export interface AnalyticsOverview {
  tenant_id: string;
  total_quotes_count: number;
  draft_count: number;
  sent_count: number;
  accepted_count: number;
  rejected_count: number;
  total_accepted_value_minor: number;
  total_pipeline_value_minor: number;
  conversion_rate_bps: number;
  average_ticket_minor: number;
  projected_monthly_revenue_minor: number;
  currency: string;
}

export interface TradeBreakdown {
  trade: string;
  quotes_count: number;
  accepted_count: number;
  total_revenue_minor: number;
  conversion_rate_bps: number;
}

export interface CustomerLTV {
  customer_id: string;
  customer_name: string;
  total_quotes_count: number;
  accepted_quotes_count: number;
  lifetime_value_minor: number;
  is_repeat_customer: boolean;
}

export function fetchAnalyticsOverview(token: string): Promise<AnalyticsOverview> {
  return apiFetch<AnalyticsOverview>("/v1/analytics/overview", { token });
}

export function fetchTradeBreakdowns(token: string): Promise<TradeBreakdown[]> {
  return apiFetch<TradeBreakdown[]>("/v1/analytics/trades", { token });
}

export function fetchCustomerLTV(token: string, limit = 10): Promise<CustomerLTV[]> {
  return apiFetch<CustomerLTV[]>(`/v1/analytics/customers?limit=${limit}`, { token });
}

import { apiFetch } from "@/lib/api-client";

export interface Customer {
  id: string;
  display_name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
}

interface CustomerListResponse {
  items: Customer[];
  page: number;
  page_size: number;
  total: number;
}

export function listCustomers(token: string, query?: string): Promise<CustomerListResponse> {
  const qs = query ? `?q=${encodeURIComponent(query)}` : "";
  return apiFetch<CustomerListResponse>(`/v1/customers${qs}`, { token });
}

export function getCustomer(token: string, customerId: string): Promise<Customer> {
  return apiFetch<Customer>(`/v1/customers/${customerId}`, { token });
}

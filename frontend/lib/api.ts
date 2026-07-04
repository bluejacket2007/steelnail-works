const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
    : ""; // browser goes through the Next.js rewrite (same-origin cookies)

// ── Enum string-literal unions (mirror the backend Python enums exactly) ────

export type Role = "SuperAdmin" | "SalesManager" | "SalesRep" | "ClientProcurement";

export type RFQStatus =
  | "RFQ_Submitted"
  | "AI_Negotiating"
  | "Sales_Review"
  | "Approved"
  | "Contract_Generated"
  | "Fulfilled"
  | "Rejected";

export type MilestoneType = "Advance_30" | "Balance_70";
export type MilestoneStatus = "Pending" | "Initiated" | "Paid" | "Failed" | "Refunded";
export type OrderStatus =
  | "Awaiting_Advance"
  | "In_Production"
  | "Awaiting_BOL"
  | "Awaiting_Balance"
  | "Shipped"
  | "Closed"
  | "Cancelled";
export type CreditRating = "AAA" | "AA" | "A" | "BBB" | "BB" | "B" | "UNRATED";

export type Finish = "Bright" | "Electro-Galvanized" | "Hot-Dip Galvanized" | "Stainless Steel";
export type ShankType = "Smooth" | "Ring" | "Screw";
export type HeadStyle = "Flat" | "Checkered" | "Countersunk";

// ── Data shapes ───────────────────────────────────────────────────────────────

export interface ProductAttributes {
  length_mm: string;
  length_inches: string;
  wire_gauge_awg: number | null;
  wire_gauge_mm: string;
  head_style: string;
  shank_type: string;
  finish: string;
}

export interface PricingTier {
  moq_min_tons: string;
  moq_max_tons: string | null;
  price_per_kg: string;
  currency: string;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  attributes: ProductAttributes | null;
  pricing_tiers: PricingTier[];
}

export interface MeResponse {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  org_id: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface RFQ {
  id: string;
  product_id: string;
  product_sku: string;
  quantity_tons: string;
  target_price_per_kg: string | null;
  status: RFQStatus;
  agent_session_id: string | null;
  created_at: string;
}

export interface Quote {
  id: string;
  rfq_id: string;
  quoted_price_per_kg: string;
  quantity_tons: string;
  currency: string;
  margin_percent: string;
  issued_by_agent: boolean;
  valid_until: string | null;
  is_accepted: boolean;
}

export interface Milestone {
  id: string;
  milestone_type: MilestoneType;
  percentage: number;
  amount: string;
  status: MilestoneStatus;
  bol_verified: boolean;
  paid_at: string | null;
}

export interface Order {
  id: string;
  total_amount: string;
  currency: string;
  status: OrderStatus;
  milestones: Milestone[];
}

export interface Organization {
  id: string;
  legal_name: string;
  country_code: string;
  gstin: string | null;
  ein: string | null;
  credit_rating: CreditRating;
  credit_limit: string;
  parent_org_id: string | null;
  is_verified: boolean;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  tools_called: string[];
  escalation_ticket: string | null;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, ...rest } = init;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...rest.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Catalog (used from Server Components — no auth) ─────────────────────────

export interface CatalogFilters {
  min_length_mm?: number;
  max_length_mm?: number;
  wire_gauge_mm?: number;
  wire_gauge_awg?: number;
  finish?: Finish;
  shank_type?: ShankType;
  head_style?: HeadStyle;
}

export async function fetchProducts(filters: CatalogFilters = {}): Promise<Product[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return request<Product[]>(`/api/v1/catalog/products${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
}

export async function getProduct(sku: string): Promise<Product> {
  return request<Product>(`/api/v1/catalog/products/${encodeURIComponent(sku)}`, {
    cache: "no-store",
  });
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
  gstin?: string;
  ein?: string;
}

export async function registerAccount(payload: RegisterPayload): Promise<MeResponse> {
  return request<MeResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Login failed");
  }
  return res.json();
}

export async function refreshAccessToken(): Promise<TokenResponse | null> {
  try {
    return await request<TokenResponse>("/api/v1/auth/refresh", { method: "POST" });
  } catch {
    return null;
  }
}

export async function logout(): Promise<void> {
  await request<void>("/api/v1/auth/logout", { method: "POST" });
}

export async function getMe(token: string): Promise<MeResponse> {
  return request<MeResponse>("/api/v1/auth/me", { token });
}

// ── RFQs & Quotes ─────────────────────────────────────────────────────────────

export async function createRfq(
  token: string,
  payload: { product_sku: string; quantity_tons: number; target_price_per_kg?: number },
): Promise<RFQ> {
  return request<RFQ>("/api/v1/rfqs", { method: "POST", token, body: JSON.stringify(payload) });
}

export async function listRfqs(token: string): Promise<RFQ[]> {
  return request<RFQ[]>("/api/v1/rfqs", { token, cache: "no-store" });
}

export async function getRfq(token: string, id: string): Promise<RFQ> {
  return request<RFQ>(`/api/v1/rfqs/${id}`, { token, cache: "no-store" });
}

export async function transitionRfq(token: string, id: string, newStatus: RFQStatus): Promise<RFQ> {
  return request<RFQ>(`/api/v1/rfqs/${id}/transition`, {
    method: "POST",
    token,
    body: JSON.stringify({ new_status: newStatus }),
  });
}

export async function issueQuote(
  token: string,
  rfqId: string,
  payload: { quoted_price_per_kg: number; quantity_tons: number; currency?: string },
): Promise<Quote> {
  return request<Quote>(`/api/v1/rfqs/${rfqId}/quotes`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function listQuotes(token: string, rfqId: string): Promise<Quote[]> {
  return request<Quote[]>(`/api/v1/rfqs/${rfqId}/quotes`, { token, cache: "no-store" });
}

export async function acceptQuote(token: string, quoteId: string): Promise<Order> {
  return request<Order>(`/api/v1/quotes/${quoteId}/accept`, { method: "POST", token });
}

// ── Orders & payments ─────────────────────────────────────────────────────────

export async function listOrders(token: string): Promise<Order[]> {
  return request<Order[]>("/api/v1/payments/orders", { token, cache: "no-store" });
}

export async function getOrder(token: string, id: string): Promise<Order> {
  return request<Order>(`/api/v1/payments/orders/${id}`, { token, cache: "no-store" });
}

export async function initiatePayment(
  token: string,
  milestoneId: string,
  provider: "stripe" | "razorpay",
): Promise<{
  milestone_id: string;
  provider: string;
  provider_payment_id: string;
  client_secret: string | null;
  amount: string;
  currency: string;
}> {
  const idempotencyKey =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  return request(`/api/v1/payments/initiate`, {
    method: "POST",
    token,
    headers: { "X-Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ milestone_id: milestoneId, provider }),
  });
}

export async function uploadBol(
  token: string,
  milestoneId: string,
  documentRef: string,
): Promise<Milestone> {
  return request<Milestone>(`/api/v1/payments/milestones/${milestoneId}/bol`, {
    method: "POST",
    token,
    body: JSON.stringify({ document_ref: documentRef }),
  });
}

export async function verifyBol(token: string, milestoneId: string): Promise<Milestone> {
  return request<Milestone>(`/api/v1/payments/milestones/${milestoneId}/bol/verify`, {
    method: "POST",
    token,
  });
}

// ── Agent chat ───────────────────────────────────────────────────────────────

export async function chatWithAgent(
  token: string,
  sessionId: string,
  message: string,
  skuContext?: string,
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/v1/agent/chat", {
    method: "POST",
    token,
    body: JSON.stringify({ session_id: sessionId, message, sku_context: skuContext }),
  });
}

export async function resetAgentSession(token: string, sessionId: string): Promise<void> {
  await request<void>(`/api/v1/agent/chat/${sessionId}`, { method: "DELETE", token });
}

// ── Organizations ─────────────────────────────────────────────────────────────

export async function listOrganizations(token: string): Promise<Organization[]> {
  return request<Organization[]>("/api/v1/orgs", { token, cache: "no-store" });
}

export async function getOrganization(token: string, id: string): Promise<Organization> {
  return request<Organization>(`/api/v1/orgs/${id}`, { token, cache: "no-store" });
}

export async function updateCreditRating(
  token: string,
  orgId: string,
  payload: { credit_rating: CreditRating; credit_limit: number },
): Promise<Organization> {
  return request<Organization>(`/api/v1/orgs/${orgId}/credit`, {
    method: "PATCH",
    token,
    body: JSON.stringify(payload),
  });
}

// ── Public contact form ───────────────────────────────────────────────────────

export interface ContactPayload {
  name: string;
  email: string;
  company?: string;
  phone?: string;
  message: string;
}

export interface ContactInquiry {
  id: string;
  name: string;
  email: string;
  company: string | null;
  phone: string | null;
  message: string;
  handled: boolean;
  created_at: string;
}

export async function submitContactInquiry(payload: ContactPayload): Promise<ContactInquiry> {
  return request<ContactInquiry>("/api/v1/contact", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listContactInquiries(token: string): Promise<ContactInquiry[]> {
  return request<ContactInquiry[]>("/api/v1/contact", { token, cache: "no-store" });
}

export async function markInquiryHandled(token: string, id: string): Promise<ContactInquiry> {
  return request<ContactInquiry>(`/api/v1/contact/${id}/handled`, { method: "POST", token });
}

export { ApiError };

/** Legacy helper retained for any direct-fetch call sites. */
export async function apiFetch(
  path: string,
  accessToken: string | null,
  init: RequestInit = {},
): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init.headers,
    },
  });
}

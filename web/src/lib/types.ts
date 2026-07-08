export type Asset = "TON" | "USDT" | "XTR";
export type InvoiceStatus = "pending" | "partially_paid" | "paid" | "expired" | "canceled";
export type Mode = "test" | "live";
export type Channel = "web" | "telegram_mini_app" | "telegram_bot";
export type ProductKind = "digital" | "physical" | "offline_service";
export type EventType =
  | "invoice.created"
  | "invoice.partially_paid"
  | "invoice.paid"
  | "invoice.expired"
  | "invoice.canceled"
  | "payment.unmatched";
export type DeliveryState = "pending" | "succeeded" | "failed";

export interface TransferView {
  tx_hash: string;
  asset: Asset;
  amount: string;
  sender: string;
  comment: string | null;
  source: "chain" | "sandbox" | "stars";
  occurred_at: string;
  explorer_url: string | null;
}

export interface PayOption {
  asset: Asset;
  amount: string;
  units: string;
  due_units: string;
  due: string;
  rate: string | null;
  deeplink: string | null;
  payload: string | null;
  jetton_master: string | null;
  decimals: number;
}

export interface PublicInvoice {
  id: string;
  status: InvoiceStatus;
  mode: Mode;
  network: "testnet" | "mainnet";
  merchant: string;
  description: string;
  fiat_amount: string;
  fiat_currency: string;
  reference: string;
  recipient: string;
  asset: Asset | null;
  options: PayOption[];
  received: string;
  overpaid: string;
  late: boolean;
  expires_at: string;
  paid_at: string | null;
  return_url: string | null;
  transfers: TransferView[];
  server_time: string;
}

export interface Quote {
  asset: Asset;
  amount: string;
  units: string;
  rate: string | null;
}

export interface Invoice {
  id: string;
  mode: Mode;
  status: InvoiceStatus;
  reference: string;
  description: string;
  order_id: string | null;
  product_kind: ProductKind;
  channel: Channel;
  fiat_amount: string;
  fiat_currency: string;
  quotes: Quote[];
  asset: Asset | null;
  received: string;
  overpaid: string;
  late: boolean;
  recipient: string;
  payer: string | null;
  pay_url: string;
  return_url: string | null;
  metadata: Record<string, unknown>;
  expires_at: string;
  paid_at: string | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Profile {
  id: string;
  name: string;
  wallet: string;
  owner: string | null;
  demo: boolean;
  accept_ton: boolean;
  accept_usdt: boolean;
  accept_stars: boolean;
  invoice_ttl_minutes: number;
  network: string;
  usdt_master: string | null;
  provider: string;
  bot_username: string | null;
}

export interface DayPoint {
  day: string;
  fiat: string;
  ton: string;
  usdt: string;
  stars: string;
  paid: number;
}

export interface Stats {
  days: DayPoint[];
  gross_fiat: string;
  paid_count: number;
  created_count: number;
  expired_count: number;
  conversion: number;
  average_order: string;
  volume: Record<Asset, string>;
  unmatched_transfers: number;
  webhook_success_rate: number | null;
}

export interface Delivery {
  id: string;
  event_id: string;
  event_type: EventType;
  invoice_id: string | null;
  endpoint_url: string;
  state: DeliveryState;
  attempts: number;
  last_status_code: number | null;
  last_error: string | null;
  next_attempt_at: string | null;
  created_at: string;
}

export interface Attempt {
  number: number;
  status_code: number | null;
  duration_ms: number;
  error: string | null;
  response_excerpt: string | null;
  created_at: string;
}

export interface DeliveryDetail {
  delivery: Delivery;
  payload: Record<string, unknown>;
  attempts: Attempt[];
}

export interface InvoiceDetail {
  invoice: Invoice;
  transfers: TransferView[];
  events: { id: string; type: EventType; created_at: string }[];
  deliveries: Delivery[];
}

export interface UnmatchedTransfer {
  id: number;
  transfer: TransferView;
  note: string | null;
}

export interface ApiKey {
  id: string;
  label: string;
  mode: Mode;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

export interface Endpoint {
  id: string;
  url: string;
  enabled: boolean;
  secret: string;
  created_at: string;
}

export interface Product {
  id: string;
  title: string;
  subtitle: string;
  kind: ProductKind;
  badge: string;
  price: string;
  stars: number | null;
  methods: Asset[];
  policy_note: string;
}

export interface ShopOrder {
  id: string;
  status: "awaiting_payment" | "fulfilled";
  product: Product;
  invoice_id: string;
  pay_url: string;
  access_code: string | null;
  fulfilled_at: string | null;
}

export interface SessionInfo {
  merchant_id: string;
  name: string;
  demo: boolean;
}

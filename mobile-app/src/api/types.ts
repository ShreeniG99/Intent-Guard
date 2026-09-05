// Contract shared with firewall/main.py. Keep in sync with the backend --
// this file is the single source of truth for event/response shapes on
// the app side.

export type Decision = 'ALLOW' | 'BLOCK' | 'REVALIDATE';

export interface AgentStepEvent {
  event: 'agent_step';
  run_id: string;
  step_number: number;
  title: string;
  duration_s: number;
  description: string;
  url?: string | null;
  screenshot_base64?: string | null;
  highlight_box?: { x: number; y: number; width: number; height: number } | null;
}

export interface CheckoutDecisionEvent {
  event: 'checkout_decision';
  run_id: string;
  decision: Decision;
  risk_score: number;
  hard_block_reasons?: string[] | null;
  razorpay_order_id?: string;
}

export interface PaymentCapturedEvent {
  event: 'payment_captured';
  run_id: string;
  order_id: string;
  amount: number;
}

export interface PaymentRefundedEvent {
  event: 'payment_refunded';
  run_id: string;
  order_id: string;
  reason: string[];
}

export type FirewallEvent =
  | AgentStepEvent
  | CheckoutDecisionEvent
  | PaymentCapturedEvent
  | PaymentRefundedEvent;

export const KNOWN_PRODUCTS = [
  { id: 'DERM-SUN-SE50-100', name: 'DermShield Sunscreen', keywords: ['dermshield', 'sunscreen', 'sun'] },
  { id: 'GAMDISK-C64', name: 'GamDisk USB Drive', keywords: ['gamdisk', 'drive', 'usb', 'pendrive'] },
  { id: 'MODHAK-MS-800-6-STL', name: 'Modhak Jars', keywords: ['modhak', 'jar', 'jars'] },
] as const;

export interface RunRequest {
  product: string;
  quantity: number;
  max_price: number;
}

export interface RunResponse {
  run_id: string;
}

export interface RunSummary {
  run_id: string;
  product_id: string;
  decision: Decision | null;
  payment_status: 'captured' | 'refunded' | 'pending' | null;
  order_id: string | null;
  created_at: string;
}

// The raw shape of one agent_run_steps row (GET /runs/{id}) -- deliberately
// distinct from AgentStepEvent: it has no `event` discriminant, since it's
// a DB record, not something that arrived over the WebSocket.
export interface RunStepRecord {
  run_id: string;
  step_number: number;
  title: string;
  duration_s: number;
  description: string;
  url?: string | null;
  screenshot_base64?: string | null;
  highlight_box?: { x: number; y: number; width: number; height: number } | null;
}

export interface RunDetail extends RunSummary {
  steps: RunStepRecord[];
  risk_score: number | null;
  hard_block_reasons: string[] | null;
  amount: number | null;
}

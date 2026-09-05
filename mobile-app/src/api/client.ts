import { RunRequest, RunResponse, RunSummary, RunDetail, KNOWN_PRODUCTS } from './types';

// IMPORTANT: set this to your PC's LAN IP when testing via Expo Go on a
// physical phone -- "localhost" resolves to the PHONE itself, not your PC.
// Find your PC's IP with `ipconfig` (Windows) and both devices must be on
// the same Wi-Fi network. Simulators on the same machine can use localhost.
export const BASE_HOST = '192.168.1.6'; // your PC's current Wi-Fi IP -- re-run `ipconfig` if it changes
export const BASE_URL = `http://${BASE_HOST}:8000`;
export const WS_URL = `ws://${BASE_HOST}:8000/ws`;

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${path} failed: HTTP ${res.status} ${text}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`${path} failed: HTTP ${res.status}`);
  return res.json();
}

/** Naive keyword + number extraction against the 3 known demo products --
 * no real NLP/catalog exists behind this, by design (see mobile-app prompt). */
export function parseOrderText(text: string): { product: string; quantity: number; max_price: number } | null {
  const lower = text.toLowerCase();
  const match = KNOWN_PRODUCTS.find((p) => p.keywords.some((k) => lower.includes(k)));
  if (!match) return null;

  // "range of 500 to 1000" / "between 500 and 1000" -- take the UPPER bound
  // as max_price. Checked first: it's more specific than the single-number
  // pattern below, and takes priority when both would otherwise match.
  const rangeMatch = lower.match(
    /(?:range of|between)\s*(?:₹|rs\.?)?\s*\d+(?:\.\d+)?\s*(?:to|-|and)\s*(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?)/
  );
  // Single-number trigger, tolerant of filler words in between ("price must
  // be under 500", "price must be in range of..." handled above already,
  // "max price 500") -- confirmed live: the original version required the
  // trigger word to sit immediately next to the digits with only
  // whitespace, so "price must be in range of 500 to 1000" matched nothing
  // at all and silently fell back to the 99999 default.
  const priceMatch =
    !rangeMatch &&
    lower.match(/(?:max|price|under|upto|up to|₹|rs\.?)[a-z\s]{0,25}?(\d+(?:\.\d+)?)/);

  // "Buy 2 GamDisk..." -- a bare number right after "buy" is a very common
  // phrasing this should not silently default away from.
  const qtyMatch =
    lower.match(/\bbuy\s+(\d+)\b/) ||
    lower.match(/(?:qty|quantity|x)\s*(\d+)/) ||
    lower.match(/\b(\d+)\s*(?:units?|pieces?|pcs?)\b/);

  return {
    product: match.id,
    quantity: qtyMatch ? parseInt(qtyMatch[1], 10) : 1,
    max_price: rangeMatch ? parseFloat(rangeMatch[1]) : priceMatch ? parseFloat(priceMatch[1]) : 99999,
  };
}

export function startAgentRun(req: RunRequest): Promise<RunResponse> {
  return post<RunResponse>('/agent/run', req);
}

export function triggerAgentPayment(runId: string): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>(`/agent/run/${runId}/pay`, {});
}

export function fetchRuns(): Promise<RunSummary[]> {
  return get<RunSummary[]>('/runs');
}

export function fetchRunDetail(runId: string): Promise<RunDetail> {
  return get<RunDetail>(`/runs/${runId}`);
}

export function payUrl(orderId: string): string {
  return `${BASE_URL}/pay?order_id=${orderId}`;
}

import { useEffect, useRef, useState } from 'react';
import { WS_URL } from './client';
import { fetchRunDetail } from './client';
import { CheckoutDecisionEvent, FirewallEvent } from './types';

/** Converts a GET /runs/{id} snapshot into the same event shapes the
 * WebSocket streams live -- used as a catch-up seed so a screen that
 * mounts its own fresh socket (every screen does, on every navigation)
 * never misses an event that already happened before it connected. The
 * broadcaster has zero history/replay (see firewall/broadcaster.py), so
 * without this, an event fired in the gap between the previous screen's
 * socket closing and this one connecting would be lost forever -- a real
 * risk across LiveRun -> Verdict -> Payment -> Receipt/Refund, where a
 * fast REVALIDATE-to-ALLOW retry or a fast capture could easily land in
 * that gap. Duplicates against live WS events are harmless: every screen
 * that reads these events uses "latest" or "first occurrence" logic. */
function seedEventsFromDetail(detail: Awaited<ReturnType<typeof fetchRunDetail>>): FirewallEvent[] {
  const seeded: FirewallEvent[] = [];
  for (const s of detail.steps) {
    seeded.push({ event: 'agent_step', ...s });
  }
  if (detail.decision) {
    seeded.push({
      event: 'checkout_decision',
      run_id: detail.run_id,
      decision: detail.decision,
      risk_score: detail.risk_score ?? 0,
      hard_block_reasons: detail.hard_block_reasons ?? [],
      razorpay_order_id: detail.order_id ?? undefined,
    } as CheckoutDecisionEvent);
  }
  if (detail.payment_status === 'captured' && detail.order_id && detail.amount != null) {
    seeded.push({ event: 'payment_captured', run_id: detail.run_id, order_id: detail.order_id, amount: detail.amount });
  }
  if (detail.payment_status === 'refunded' && detail.order_id) {
    seeded.push({
      event: 'payment_refunded', run_id: detail.run_id, order_id: detail.order_id,
      reason: detail.hard_block_reasons ?? [],
    });
  }
  return seeded;
}

export function useFirewallSocket(runId: string | null) {
  const [events, setEvents] = useState<FirewallEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    let retryTimeout: ReturnType<typeof setTimeout>;

    fetchRunDetail(runId)
      .then((detail) => {
        if (cancelled) return;
        const seeded = seedEventsFromDetail(detail);
        if (seeded.length) setEvents((prev) => [...seeded, ...prev]);
      })
      .catch(() => {
        // best-effort catch-up; the live socket below is still the primary path
      });

    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        retryRef.current = 0;
      };
      ws.onmessage = (msg) => {
        if (cancelled) return;
        try {
          const data: FirewallEvent = JSON.parse(msg.data);
          if ((data as any).run_id === runId) {
            setEvents((prev) => [...prev, data]);
          }
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        const delay = Math.min(1000 * 2 ** retryRef.current, 8000);
        retryRef.current += 1;
        retryTimeout = setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimeout);
      wsRef.current?.close();
    };
  }, [runId]);

  const latestOfType = <T extends FirewallEvent>(type: T['event']): T | undefined =>
    [...events].reverse().find((e) => e.event === type) as T | undefined;

  return { events, connected, latestOfType };
}

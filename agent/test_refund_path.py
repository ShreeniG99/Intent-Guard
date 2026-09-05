"""
test_refund_path.py

Real, live exercise of the EXTENSION path (POST /payments/capture), with the
actual browser_use agent driving BOTH legs -- not just raw HTTP calls the way
firewall/test_capture_e2e.py does it:

  Leg 1 (shopping_agent.run_shopping_task): the real agent browses page 1
  (clean DermShield page), decides what to buy, and checks out -> ALLOW,
  which creates a real Razorpay TEST-mode order.

  Leg 2 (a second, focused browser_use.Agent below): drives the real
  Razorpay Checkout.js test-mode payment popup at /pay?order_id=... to mint
  an actual `authorized` payment. Kept as a separate Agent instance from
  leg 1 -- it's a genuinely different task (fill a fixed payment form vs.
  read a product page and decide), and keeping them separate keeps each
  leg's reasoning log legible as its own phase rather than one Agent
  awkwardly context-switching between two unrelated jobs.

Two cases, mirroring firewall/test_capture_e2e.py exactly (same DB-tamper
technique, so this is provably the same guarantee, just exercised through
the real agent instead of synthetic HTTP):
  A. consistent -> order still matches intent at capture time -> {"status": "captured"}
  B. drifted    -> a race AFTER checkout tampers orders.proposed_price to
                   far above the customer's max_price (simulating a
                   stale-price order slipping through between checkout and
                   capture) -> {"status": "refunded"} -- refund is the
                   fallback, never the first move (plan doc Section 1).

Usage (from agent/, firewall server already up on :8000):
    python test_refund_path.py            # case A -> expect captured
    python test_refund_path.py --refund   # case B -> expect refunded
"""
import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time

import requests

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from shopping_agent import FIREWALL_BASE, complete_payment_with_agent, run_shopping_task

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "firewall_state.db")
PAGE1 = dict(
    page="1_dermshield_sunscreen.html", product_id="DERM-SUN-SE50-100",
    variant_label="100 ml", quantity=1, max_price=450.0,
)
PAGE3 = dict(
    page="3_modhak_jars.html", product_id="MODHAK-MS-800-6-STL",
    variant_label="Steel lid, 800 ml, set of 6", quantity=1, max_price=1499.0,
)


def tamper_order_price(order_id: str, new_price: float) -> None:
    """Simulate a race condition: catalog/order state drifts AFTER checkout
    approved it but BEFORE capture runs -- e.g. a second concurrent request
    changed the price. Direct DB write because that's genuinely external to
    anything the agent (or a legitimate customer) does; it's the failure
    mode the capture-time consistency recheck exists to catch."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE orders SET proposed_price = ? WHERE order_id = ?", (new_price, order_id))
    conn.commit()
    conn.close()
    print(f"  [race simulation] tampered orders.proposed_price -> INR{new_price} for {order_id}")


def wait_for_capture_outcome(order_id: str, timeout_s: int = 150) -> dict:
    """Poll /audit for the terminal capture/refund event that
    main.py's pay_callback auto-triggers for any agent-run order (it calls
    _capture_and_check itself once Checkout.js posts the authorized
    payment -- see firewall/main.py). Returns {"status": "captured" |
    "refunded", "detail": ...}. Raises on capture_auto_trigger_failed or
    timeout.

    This replaces an earlier explicit `POST /payments/capture` call here,
    which raced pay_callback's own auto-trigger for the same payment_id
    and lost the atomic capture CAS about half the time (HTTP 409
    already_captured). Observing the outcome is race-free and mirrors
    exactly what the mobile app does.
    """
    outcomes = {"payment_captured": "captured", "payment_refunded": "refunded"}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rows = requests.get(f"{FIREWALL_BASE}/audit", params={"limit": 50}).json()
        for row in rows:
            if row.get("order_id") != order_id:
                continue
            if row["event_type"] == "capture_auto_trigger_failed":
                raise RuntimeError(
                    f"pay_callback's auto capture/refund failed for {order_id}: {row['detail']}"
                )
            if row["event_type"] in outcomes:
                return {"status": outcomes[row["event_type"]], "detail": row["detail"]}
        time.sleep(2)
    raise TimeoutError(f"no capture/refund outcome for {order_id} within {timeout_s}s")


def finish_with_payment(run_id: str, order_id: str, steps_so_far: list, expect: str, decision_dump: dict, fw: dict):
    """Shared tail: complete the real payment via the agent, observe the
    capture/refund outcome pay_callback produces, assert it, print the
    full reasoning timeline, and write the transcript."""
    pay_result = asyncio.run(complete_payment_with_agent(order_id, run_id=run_id))
    body = wait_for_capture_outcome(order_id)
    print(f"\ncapture/refund outcome (via pay_callback auto-trigger): {body}")
    assert body.get("status") == expect, f"expected {expect}, got {body}"
    print(f"\nPASS: {'inconsistent post-capture state was refunded, not kept' if expect == 'refunded' else 'consistent payment captured end-to-end'}.")

    all_steps = steps_so_far + pay_result["steps"]
    print("\n--- full reasoning timeline ---")
    for i, s in enumerate(all_steps, 1):
        print(f"  [{s['duration_s']:>5.1f}s] {i}. {s['title']}\n         {s['description']}")

    out_path = os.path.join(os.path.dirname(__file__), f"run_refund_{run_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"case": expect, "decision": decision_dump, "checkout_response": fw,
                    "capture_response": body, "steps": all_steps}, f, indent=2, ensure_ascii=False)
    print(f"\nFull transcript written to {out_path}")


def scenario_1_page1_allow():
    print("=" * 70); print("SCENARIO 1: page 1, clean -> ALLOW -> paid"); print("=" * 70)
    page_url = f"{FIREWALL_BASE}/store/{PAGE1['page']}"
    result = asyncio.run(run_shopping_task(page_url=page_url, product_id=PAGE1["product_id"],
                                variant_label=PAGE1["variant_label"], quantity=PAGE1["quantity"],
                                max_price=PAGE1["max_price"]))
    fw = result["firewall_response"]
    assert fw["decision"] == "ALLOW", f"expected ALLOW, got {fw}"
    order_id = fw["razorpay_order_id"]
    print(f"\ncheckout ALLOW -> razorpay order {order_id}\n")
    finish_with_payment(result["run_id"], order_id, result["steps"], "captured",
                         result["decision"].model_dump(), fw)


def scenario_2_page3_revalidate_then_refund():
    print("=" * 70); print("SCENARIO 2: page 3 -> REVALIDATE -> GENUINE 2nd browse -> ALLOW -> race -> REFUND"); print("=" * 70)
    page_url = f"{FIREWALL_BASE}/store/{PAGE3['page']}"
    result = asyncio.run(run_shopping_task(page_url=page_url, product_id=PAGE3["product_id"],
                                variant_label=PAGE3["variant_label"], quantity=PAGE3["quantity"],
                                max_price=PAGE3["max_price"]))
    fw1 = result["firewall_response"]
    assert fw1["decision"] == "REVALIDATE", f"expected REVALIDATE, got {fw1}"
    print(f"\nleg 1: page 3 read -> REVALIDATE (risk={fw1['risk_score']:.2f})\n")

    # Genuine second browse: a real Agent.run() against ?stage=recheck, which
    # firewall/main.py serves with the injected content stripped server-side
    # (so the deterministic catalog-extraction step sees the same clean
    # content the agent's own browser does) -- models the merchant's
    # compliance team pulling the flagged listing text after leg 1 caught it.
    result2 = asyncio.run(run_shopping_task(
        page_url=f"{page_url}?stage=recheck", product_id=PAGE3["product_id"],
        variant_label=PAGE3["variant_label"], quantity=PAGE3["quantity"],
        max_price=PAGE3["max_price"], run_id=result["run_id"],
    ))
    fw2 = result2["firewall_response"]
    assert fw2["decision"] == "ALLOW", f"expected ALLOW on genuine second browse, got {fw2}"
    order_id = fw2["razorpay_order_id"]
    print(f"leg 2: genuine second browse of the re-checked listing -> ALLOW -> razorpay order {order_id}\n")

    tamper_order_price(order_id, new_price=99999.0)
    print("leg 3: race simulated (order price drifted after ALLOW, before capture)\n")

    all_steps = result["steps"] + result2["steps"]
    finish_with_payment(result["run_id"], order_id, all_steps, "refunded",
                         result2["decision"].model_dump(), fw2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["1", "2"], help="1 = page1 ALLOW+pay, 2 = page3 REVALIDATE->ALLOW->race->refund")
    args = ap.parse_args()
    if args.scenario == "1":
        scenario_1_page1_allow()
    else:
        scenario_2_page3_revalidate_then_refund()

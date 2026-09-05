"""
test_capture_e2e.py

End-to-end exercise of the EXTENSION path (`POST /payments/capture`) against
REAL Razorpay test mode, including a real `authorized` payment.

Why this script exists: Razorpay S2S / Direct APIs (`createPaymentJson`,
`createUpi`) are NOT enabled on this test account (confirmed: both return
"URL not found"), so the only way to produce an `authorized` payment is the
Checkout.js browser flow. This script drives the CORE flow to create the
order, then waits for a human (or a browser automation) to complete payment
at  http://localhost:8000/pay?order_id=<id>  with Razorpay's DOMESTIC test
card 4100 2800 0000 1007 (an international test card like 4111 1111 1111 1111
is rejected on this account), then runs capture and asserts the outcome.

Two cases:
  A. consistent  -> order still matches intent  -> expect  {"status":"captured"}
  B. drifted     -> orders.proposed_price tampered above intent.max_price
                    between checkout and capture -> expect {"status":"refunded"}

Run (from firewall/, server already up on :8000):
    python test_capture_e2e.py            # runs case A, prints the /pay URL, waits
    python test_capture_e2e.py --refund   # runs case B
"""
import sys
import time
import sqlite3
import os

import requests

BASE = "http://localhost:8000"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "firewall_state.db")
POLL_SECONDS = 240


def run_core_flow(max_price=1500.0, proposed_price=1200.0):
    """intent -> snapshot -> checkout(ALLOW). Returns (razorpay_order_id, token)."""
    r = requests.post(f"{BASE}/intent", json={
        "product_id": "SKU-CAP", "quantity": 1, "max_price": max_price})
    r.raise_for_status()
    token = r.json()["token"]

    r = requests.post(f"{BASE}/catalog/snapshot", json={
        "token": token, "product_id": "SKU-CAP", "surface": "description",
        "raw_text": "Stainless steel water bottle, 750ml, vacuum insulated.",
        "price": proposed_price, "sku": "SKU-CAP", "quantity_available": 10})
    r.raise_for_status()
    snap_id = r.json()["id"]

    r = requests.post(f"{BASE}/checkout", json={
        "token": token, "snapshot_id": snap_id,
        "proposed_price": proposed_price, "proposed_sku": "SKU-CAP", "proposed_qty": 1,
        "current_raw_text": "Stainless steel water bottle, 750ml, vacuum insulated.",
        "current_price": proposed_price, "current_sku": "SKU-CAP",
        "current_quantity_available": 10})
    r.raise_for_status()
    body = r.json()
    assert body["decision"] == "ALLOW", f"expected ALLOW, got {body}"
    return body["razorpay_order_id"], token


def wait_for_authorized_payment(order_id):
    print(f"\n  >>> Open this and pay with test card 4111 1111 1111 1111:")
    print(f"  >>> {BASE}/pay?order_id={order_id}\n")
    deadline = time.time() + POLL_SECONDS
    while time.time() < deadline:
        rows = requests.get(f"{BASE}/audit", params={"limit": 50}).json()
        for row in rows:
            if row["event_type"] == "test_payment_authorized" and row["order_id"] == order_id:
                print(f"  payment authorized: {row['payment_id']}")
                return row["payment_id"]
        time.sleep(3)
    raise TimeoutError(f"no authorized payment for {order_id} within {POLL_SECONDS}s")


def tamper_order_price(razorpay_order_id, new_price):
    """Simulate catalog/order drift AFTER checkout but BEFORE capture:
    push the stored order's proposed_price above the intent's max_price."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE orders SET proposed_price = ? WHERE order_id = ?",
                 (new_price, razorpay_order_id))
    conn.commit()
    conn.close()
    print(f"  tampered orders.proposed_price -> {new_price} for {razorpay_order_id}")


def main():
    refund_case = "--refund" in sys.argv
    print("=" * 70)
    print(f"CAPTURE E2E  --  case {'B (drift -> refund)' if refund_case else 'A (consistent -> capture)'}")
    print("=" * 70)

    order_id, token = run_core_flow()
    print(f"  checkout ALLOW -> razorpay order {order_id}")

    if refund_case:
        tamper_order_price(order_id, new_price=99999.0)  # far above max_price 1500

    payment_id = wait_for_authorized_payment(order_id)

    r = requests.post(f"{BASE}/payments/capture", json={
        "order_id": order_id, "payment_id": payment_id})
    print(f"\n  /payments/capture -> HTTP {r.status_code}: {r.json()}")

    body = r.json()
    if refund_case:
        assert r.status_code == 200 and body.get("status") == "refunded", \
            f"expected refunded, got {body}"
        print("\n  PASS: inconsistent post-capture state was refunded, not kept.")
    else:
        assert r.status_code == 200 and body.get("status") == "captured", \
            f"expected captured, got {body}"
        print("\n  PASS: consistent payment captured end-to-end.")

    # show the audit trail for this order
    print("\n  audit trail for this order:")
    for row in requests.get(f"{BASE}/audit", params={"limit": 60}).json():
        if row["order_id"] == order_id:
            print(f"    [{row['id']}] {row['event_type']:24s} {row.get('detail','')[:80]}")


if __name__ == "__main__":
    main()

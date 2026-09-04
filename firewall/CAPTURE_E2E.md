# End-to-end `/payments/capture` test

`/payments/capture` (the EXTENSION: post-capture consistency recheck + refund
fallback) needs a **real `authorized` Razorpay payment** to run against. Two
things make the payment step manual:

1. Razorpay **S2S / Direct APIs** (`createPaymentJson`, `createUpi`) are **not
   enabled** on this test account — both return *"URL not found"* (confirmed
   2026-09-04). Without S2S there is no server-side way to mint a payment.
2. The only remaining path is **Checkout.js in a browser**, and Razorpay's
   checkout modal renders in a CSS-transform-scaled iframe that headless
   click-automation cannot dispatch into. So a human has to tap the test card.

**No real money moves** — `rzp_test_` keys only (the SDK hard-refuses anything
else), test card `4111 1111 1111 1111` is a public Razorpay fixture.

## What's built and automated

| piece | status |
|---|---|
| `GET /pay?order_id=…` — hosted Checkout.js page for one order | built; modal verified loading with correct amount + order id |
| `POST /pay/callback` — records the `authorized` payment_id to `audit_log` + WS broadcast | built |
| `firewall/test_capture_e2e.py` — runs CORE flow → real order, polls `/audit` for the authorized payment, calls `/payments/capture`, asserts outcome | built; CORE flow verified producing a real order |

Only the card tap in the middle is manual.

## Run it (case A — consistent → capture)

```bash
# terminal 1 — server (from firewall/)
../.venv/Scripts/python -m uvicorn main:app --port 8000

# terminal 2 — test runner (from firewall/)
../.venv/Scripts/python test_capture_e2e.py
```

The runner prints a URL like `http://localhost:8000/pay?order_id=order_XXXX`.
Open it in a normal browser, the Razorpay modal is already open:

1. Contact details are prefilled (`9999999999`) → **Continue**
2. Card: `4111 1111 1111 1111`, expiry any future date (`12 / 30`), CVV `123`,
   name anything → **Pay ₹1200**
3. Test mode shows a "Success"/"Complete Payment" mock page → click it.

The runner detects the authorized payment within ~3s and calls
`/payments/capture`. Expected:

```
/payments/capture -> HTTP 200: {'status': 'captured', 'amount': 1200.0}
PASS: consistent payment captured end-to-end.
```

## Run it (case B — drift → refund)

```bash
../.venv/Scripts/python test_capture_e2e.py --refund
```

Same steps, but the runner first tampers the stored `orders.proposed_price`
to ₹99999 (above the intent's ₹1500 max) *after* checkout, simulating
order/catalog drift between order-creation and capture. Expected:

```
/payments/capture -> HTTP 200: {'status': 'refunded', 'reason': [...]}
PASS: inconsistent post-capture state was refunded, not kept.
```

This exercises the branch in `main.py` where `consistent` is `False`:
`check_hard_blocks(intent, order.proposed_price, …)` returns a non-empty
reason list → `refund_payment(...)` (never `capture_payment` first) → audit
`payment_refunded` + WS broadcast.

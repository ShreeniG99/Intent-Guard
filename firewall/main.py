"""
main.py

FastAPI firewall middleware. All layers are built:
  CORE gate       -- intent capture -> catalog snapshot -> checkout
                     decision (freshness + risk formula + hard blocks).
  EXTENSION       -- post-capture consistency recheck + refund fallback,
                     auto-triggered from /pay/callback for agent runs.
  Audit + WebSocket -- every decision writes an immutable audit_log row
                     and broadcasts over the in-process broadcaster.
  Mobile-app API  -- /agent/run (server-side browser_use run), /agent/step
                     (live step feed), /agent/run/{id}/pay, /runs[/{id}].

Every decision, allowed or not, writes an audit_log row -- must-have per
the plan doc's judging-rubric requirement for an immutable decision
envelope.
"""
import asyncio
import json
import re
import sys
import os
import uuid

# Since POST /agent/run runs the real browser_use agent in-process (a
# background thread, see _execute_agent_run_sync below), this server's own
# stdout needs the same UTF-8 fix agent/run_demo.py already applies --
# browser-use logs the Rupee sign on every step, which crashes on Windows'
# default cp1252 console encoding ("'charmap' codec can't encode character
# '₹'"), confirmed live the first time a run executed inside this process.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from broadcaster import broadcaster

from db import init_db, get_connection
from tokens import issue_token, validate_token, consume_token, TokenError
from catalog import take_snapshot, check_freshness
from risk import evaluate, check_hard_blocks
from razorpay_client import (create_order, fetch_payment, capture_payment,
                             refund_payment, get_client)

app = FastAPI(title="Checkout Integrity Firewall")

# Local demo only -- the mobile app calls this API from a different device/
# origin (Expo Go on a phone), so CORS must be open. Not meant for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- demo merchant pages -------------------------------------------------
# The 3 Simply Shop product pages the demo agent browses, served straight
# from demo/merchant/. Relative asset links (assets/simplyshop.css) resolve
# under this same prefix. html=True lets /store/<name>.html work directly.
#   /store/1_dermshield_sunscreen.html   — CLEAN
#   /store/2_gamdisk_drive.html          — hidden injection in a review (+ ?reveal=1)
#   /store/3_modhak_jars.html            — visible coupon injection (+ ?stage=checkout)
_DEMO_DIR = os.path.join(os.path.dirname(__file__), "..", "demo", "merchant")

# Page 3's browse->checkout price flip (?stage=checkout, 1499 -> 2499) was
# originally client-side JS only, which a plain HTTP fetch never executes --
# so any non-browser client (including this project's own agent/
# orchestrator, which fetches "the current page state" with plain requests.get)
# always saw the stale 1499, silently defeating the whole drift demo. Fixed
# by rendering the flip server-side for that one file; the client JS still
# runs too (same result, redundant but harmless) so a human opening the page
# in a real browser sees no change.
_MODHAK_PATH = os.path.join(_DEMO_DIR, "3_modhak_jars.html")


@app.get("/store/3_modhak_jars.html", response_class=HTMLResponse)
def store_modhak_jars(stage: str | None = None):
    html = open(_MODHAK_PATH, encoding="utf-8").read()
    if stage == "checkout":
        html = (
            html.replace('"price": "1499"', '"price": "2499"')
                .replace('<span class="price" id="price">₹1,499</span>',
                         '<span class="price" id="price">₹2,499</span>')
                .replace('<span class="mrp">₹2,199</span>', '<span class="mrp" style="display:none">₹2,199</span>')
                .replace('<span class="off" id="off">32% off</span>',
                         '<span class="off" id="off" style="display:none">32% off</span>')
        )
    elif stage == "recheck":
        # Server-side removal, not just the page's own client-side JS toggle:
        # shopping_agent.py's deterministic catalog-extraction step fetches
        # this page with plain requests.get() (no JS execution), so a
        # client-side-only hide would still leave the injected text in what
        # the firewall's classifier actually sees -- confirmed this exact
        # class of bug once already for the price flip above. Stripping the
        # elements here means a genuine second browse (real agent, real
        # fetch) legitimately finds a clean listing, not just a visually
        # different one.
        html = re.sub(r'<div class="offer agent" id="agent-injection">.*?</div>', '', html)
        html = re.sub(r'<p id="rebate-injection">.*?</p>', '', html)
    return html


if os.path.isdir(_DEMO_DIR):
    app.mount("/store", StaticFiles(directory=_DEMO_DIR, html=True), name="store")


@app.on_event("startup")
def _startup():
    init_db()


def write_audit(event_type: str, token: str = None, order_id: str = None,
                 payment_id: str = None, decision: str = None,
                 risk_score: float = None, flags: dict = None, detail: str = None):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO audit_log
               (event_type, token, order_id, payment_id, decision, risk_score, flags_json, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, token, order_id, payment_id, decision, risk_score,
             json.dumps(flags or {}), detail),
        )
        conn.commit()
    finally:
        conn.close()


def update_agent_run(run_id: str | None, **fields) -> None:
    """Best-effort update of an agent_runs row from any endpoint that
    receives a run_id (checkout, capture). No-op if run_id is None (i.e.
    the caller wasn't a mobile-app-triggered run, e.g. a raw script)."""
    if not run_id or not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE agent_runs SET {cols} WHERE run_id = ?", (*fields.values(), run_id))
        conn.commit()
    finally:
        conn.close()


# --- POST /intent -----------------------------------------------------------

class IntentRequest(BaseModel):
    product_id: str
    quantity: int
    max_price: float
    variant: str | None = None
    currency: str = "INR"
    customer_ref: str | None = None


@app.post("/intent")
def post_intent(req: IntentRequest):
    result = issue_token(
        product_id=req.product_id, quantity=req.quantity, max_price=req.max_price,
        variant=req.variant, currency=req.currency, customer_ref=req.customer_ref,
    )
    write_audit("intent_captured", token=result["token"],
                detail=f"product={req.product_id} qty={req.quantity} max_price={req.max_price}")
    return result


# --- POST /catalog/snapshot --------------------------------------------------

class SnapshotRequest(BaseModel):
    token: str
    product_id: str
    surface: str  # "description" | "coupon" | "review"
    raw_text: str
    price: float | None = None
    sku: str | None = None
    quantity_available: int | None = None


@app.post("/catalog/snapshot")
def post_snapshot(req: SnapshotRequest):
    snapshot = take_snapshot(
        token=req.token, product_id=req.product_id, surface=req.surface,
        raw_text=req.raw_text, price=req.price, sku=req.sku,
        quantity_available=req.quantity_available,
    )
    write_audit("catalog_snapshot", token=req.token,
                risk_score=None,
                flags={"deterministic_score": snapshot["deterministic_score"],
                       "injection_confidence": snapshot["injection_confidence"]},
                detail=f"snapshot_id={snapshot['id']} surface={req.surface}")
    return snapshot


# --- POST /checkout -----------------------------------------------------------

class CheckoutRequest(BaseModel):
    token: str
    snapshot_id: int          # the ORIGINAL browse-time snapshot, for freshness comparison
    proposed_price: float
    proposed_sku: str
    proposed_qty: int
    current_raw_text: str     # what the agent observes right NOW, one more look before finalizing
    current_price: float | None = None
    current_sku: str | None = None
    current_quantity_available: int | None = None
    run_id: str | None = None  # correlates this decision to a mobile-app-triggered agent run, if any


@app.post("/checkout")
async def post_checkout(req: CheckoutRequest):
    # 1. validate capability token -- unknown/expired/consumed is a hard
    #    block, checked before anything else touches the risk formula
    try:
        intent = validate_token(req.token)
    except TokenError as e:
        write_audit("checkout_blocked", token=req.token, decision="BLOCK",
                    detail=f"token_error={e}")
        raise HTTPException(status_code=403, detail=f"invalid_token: {e}")

    # 2. CORE freshness check: re-sanitize/classify what the agent observes
    #    RIGHT NOW and compare its hash against the browse-time snapshot.
    #    This is the "product state changed" check -- previously built in
    #    catalog.py but never wired in; fixed here.
    conn = get_connection()
    try:
        snap_exists = conn.execute(
            "SELECT id FROM catalog_snapshots WHERE id = ? AND token = ?",
            (req.snapshot_id, req.token),
        ).fetchone()
    finally:
        conn.close()
    if snap_exists is None:
        write_audit("checkout_blocked", token=req.token, decision="BLOCK",
                    detail="snapshot_not_found_or_token_mismatch")
        raise HTTPException(status_code=400, detail="snapshot_not_found_for_token")

    freshness = check_freshness(
        previous_snapshot_id=req.snapshot_id,
        current_raw_text=req.current_raw_text,
        current_price=req.current_price,
        current_sku=req.current_sku,
        current_quantity_available=req.current_quantity_available,
    )

    # 3. evaluate: hard blocks + risk formula, using the FRESH scores
    #    (not the possibly-stale browse-time ones) -- risk.py, single source of truth
    decision = evaluate(
        intent=intent,
        proposed_price=req.proposed_price,
        proposed_sku=req.proposed_sku,
        proposed_qty=req.proposed_qty,
        deterministic_score=freshness["current_deterministic_score"],
        injection_confidence=freshness["current_injection_confidence"],
    )

    # catalog drift alone upgrades ALLOW -> REVALIDATE (never downgrades an
    # independent BLOCK) and, when it does, the token is NOT consumed --
    # the agent can re-browse and retry, per Section 1's stated behavior
    if not freshness["fresh"] and decision.decision == "ALLOW":
        decision.decision = "REVALIDATE"
        decision.hard_block_reasons = decision.hard_block_reasons + ["catalog_state_changed_since_browse"]

    flags = {
        "deterministic_score": decision.deterministic_score,
        "injection_confidence": decision.injection_confidence,
        "hard_block_reasons": decision.hard_block_reasons,
        "catalog_fresh": freshness["fresh"],
    }

    if decision.decision != "ALLOW":
        write_audit("checkout_decision", token=req.token, decision=decision.decision,
                    risk_score=decision.risk_score, flags=flags,
                    detail="not allowed -- no Razorpay order created")
        await broadcaster.broadcast({
            "event": "checkout_decision", "run_id": req.run_id, "decision": decision.decision,
            "risk_score": decision.risk_score, "hard_block_reasons": decision.hard_block_reasons,
        })
        update_agent_run(req.run_id, decision=decision.decision, risk_score=decision.risk_score,
                          hard_block_reasons_json=json.dumps(decision.hard_block_reasons))
        return {
            "decision": decision.decision,
            "risk_score": decision.risk_score,
            "hard_block_reasons": decision.hard_block_reasons,
        }

    # 4. ALLOW: consume the token (single-use, atomic) and create the real order
    try:
        consume_token(req.token)
    except TokenError as e:
        # lost a race to another concurrent checkout attempt on the same token
        write_audit("checkout_blocked", token=req.token, decision="BLOCK",
                    detail=f"token_consume_race: {e}")
        raise HTTPException(status_code=409, detail=f"token_race_lost: {e}")

    order = create_order(
        amount_rupees=req.proposed_price,
        receipt=f"intent-{req.token[:12]}",
        notes={"firewall_token": req.token, "risk_score": str(decision.risk_score)},
    )

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO orders
               (order_id, token, snapshot_id, proposed_price, proposed_sku, proposed_qty,
                risk_score, decision, razorpay_order_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order["id"], req.token, req.snapshot_id, req.proposed_price, req.proposed_sku,
             req.proposed_qty, decision.risk_score, decision.decision, order["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    write_audit("checkout_decision", token=req.token, order_id=order["id"],
                decision="ALLOW", risk_score=decision.risk_score, flags=flags,
                detail="razorpay order created")
    await broadcaster.broadcast({
        "event": "checkout_decision", "run_id": req.run_id, "decision": "ALLOW",
        "risk_score": decision.risk_score, "razorpay_order_id": order["id"],
    })
    update_agent_run(req.run_id, decision="ALLOW", risk_score=decision.risk_score, order_id=order["id"])

    return {
        "decision": "ALLOW",
        "risk_score": decision.risk_score,
        "razorpay_order_id": order["id"],
        "amount": order["amount"],
    }


# --- POST /payments/capture --------------------------------------------------
# EXTENSION: post-capture consistency recheck, refund as last-resort fallback.
# Atomic compare-and-swap on payments.captured, per plan doc Section 6a.

class CaptureRequest(BaseModel):
    order_id: str
    payment_id: str
    run_id: str | None = None


async def _capture_and_check(order_id: str, payment_id: str, run_id: str | None) -> dict:
    """Core EXTENSION logic: verify + atomically claim capture, recheck
    consistency, refund as fallback if it fails. Shared by POST
    /payments/capture (explicit caller-driven capture, e.g. scripts) and
    pay_callback's auto-trigger (the mobile app flow, where the human pays
    via an embedded WebView with no orchestrating script watching for it)."""
    conn = get_connection()
    try:
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    finally:
        conn.close()
    if order is None:
        raise HTTPException(status_code=404, detail="order_not_found")

    # 1. fetch the payment from Razorpay directly -- never trust a caller-
    #    supplied amount, always verify against Razorpay's own record
    payment = fetch_payment(payment_id)
    if payment["status"] != "authorized":
        write_audit("capture_rejected", order_id=order_id, payment_id=payment_id,
                    detail=f"payment_status={payment['status']}, expected authorized")
        raise HTTPException(status_code=400, detail=f"payment_not_authorized: {payment['status']}")

    amount_rupees = payment["amount"] / 100.0

    # 2. atomic compare-and-swap: insert-if-absent, then claim capture with
    #    UPDATE...WHERE captured=0. Losing this race means someone else
    #    already captured this exact payment_id.
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO payments (payment_id, order_id, amount, captured)
               VALUES (?, ?, ?, 0)""",
            (payment_id, order_id, amount_rupees),
        )
        conn.commit()
        cur = conn.execute(
            "UPDATE payments SET captured = 1 WHERE payment_id = ? AND captured = 0",
            (payment_id,),
        )
        conn.commit()
        won_race = cur.rowcount == 1
    finally:
        conn.close()

    if not won_race:
        write_audit("capture_race_lost", order_id=order_id, payment_id=payment_id,
                    detail="payment already captured by a prior request")
        raise HTTPException(status_code=409, detail="already_captured")

    # 3. consistency recheck: does the order STILL match the original intent?
    #    (defense in depth -- checkout already verified this once, but state
    #    could have drifted between order-creation and capture-time)
    conn = get_connection()
    try:
        intent = conn.execute("SELECT * FROM intents WHERE token = ?", (order["token"],)).fetchone()
    finally:
        conn.close()

    consistency_reasons = check_hard_blocks(
        dict(intent), order["proposed_price"], order["proposed_sku"], order["proposed_qty"]
    )
    consistent = len(consistency_reasons) == 0 and abs(amount_rupees - order["proposed_price"]) < 0.01

    conn = get_connection()
    try:
        if consistent:
            capture_payment(payment_id, amount_rupees)
            conn.execute(
                """UPDATE payments SET consistency_recheck_passed = 1, captured_at = datetime('now')
                   WHERE payment_id = ?""",
                (payment_id,),
            )
            conn.commit()
            write_audit("payment_captured", order_id=order_id, payment_id=payment_id,
                        detail=f"amount={amount_rupees}")
            await broadcaster.broadcast({
                "event": "payment_captured", "run_id": run_id, "order_id": order_id, "amount": amount_rupees,
            })
            update_agent_run(run_id, payment_status="captured", amount=amount_rupees)
            return {"status": "captured", "amount": amount_rupees}
        else:
            # 4. inconsistent post-capture state -- refund is the fallback,
            #    never the first response (Section 1, EXTENSION). Razorpay's
            #    refund API requires a payment to already be `captured` --
            #    refunding straight from `authorized` is rejected ("payment
            #    status should be captured for action to be taken"), so
            #    capture the authorized amount first, then immediately
            #    refund it in full. Confirmed live: this branch had never
            #    actually been exercised against a real payment before.
            #
            # If the ONLY inconsistency is the amount (the order price
            # drifted after creation but no hard-block rule fired -- e.g.
            # the customer's max_price was generous enough to still cover
            # the drifted price), synthesize a readable reason so the audit
            # log and the app's Refund screen aren't left blank.
            if not consistency_reasons:
                consistency_reasons = [
                    f"amount_mismatch: captured=₹{amount_rupees:.2f} "
                    f"but order now ₹{order['proposed_price']:.2f}"
                ]
            capture_payment(payment_id, amount_rupees)
            refund_payment(payment_id, notes={"reason": "post_capture_consistency_failed"})
            conn.execute(
                """UPDATE payments SET consistency_recheck_passed = 0, refunded = 1,
                   captured_at = datetime('now') WHERE payment_id = ?""",
                (payment_id,),
            )
            conn.commit()
            write_audit("payment_refunded", order_id=order_id, payment_id=payment_id,
                        detail=f"consistency_failed: {consistency_reasons}")
            await broadcaster.broadcast({
                "event": "payment_refunded", "run_id": run_id, "order_id": order_id, "reason": consistency_reasons,
            })
            update_agent_run(run_id, payment_status="refunded", amount=amount_rupees,
                              hard_block_reasons_json=json.dumps(consistency_reasons))
            return {"status": "refunded", "reason": consistency_reasons}
    finally:
        conn.close()


@app.post("/payments/capture")
async def post_capture(req: CaptureRequest):
    return await _capture_and_check(req.order_id, req.payment_id, req.run_id)


# --- GET /pay  +  POST /pay/callback ----------------------------------------
# Minimal hosted-checkout page for authorizing a real TEST-MODE payment
# against a manual-capture order, so /payments/capture can be exercised
# end-to-end (Razorpay S2S/Direct APIs are not enabled on the test account,
# so a Checkout.js browser flow is the only way to mint an `authorized`
# payment). Doubles as the demo's mini merchant checkout.
# Test card: 4100 2800 0000 1007 (Razorpay's DOMESTIC test Visa -- an
# international test card like 4111 1111 1111 1111 is rejected on this
# account), any future expiry, any CVV; OTP step is mocked (any digits).

@app.get("/pay", response_class=HTMLResponse)
def pay_page(order_id: str):
    key_id = os.environ["RAZORPAY_KEY_ID"]
    order = get_client().order.fetch(order_id)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Firewall test checkout</title>
<style>
/* Razorpay's Checkout.js sometimes applies a CSS transform (scale) to its
   own overlay container/iframe for responsive fit. That transform breaks
   CDP-based synthetic click coordinate mapping for automated browsers
   (confirmed: "frame owner is CSS-transformed (scaled)" dispatch error).
   Force it back to identity so click coordinates land where they visually
   appear. !important here beats a non-important inline style Razorpay's
   own JS may set; the companion observer below re-asserts this against
   any later *important* inline style Razorpay's JS re-applies. */
iframe[src*="razorpay" i], iframe[name*="razorpay" i],
div[class*="razorpay" i], div[id*="razorpay" i] {{
  transform: none !important;
}}
</style>
</head><body style="font-family:system-ui;padding:2rem">
<h3>Checkout Integrity Firewall &mdash; TEST checkout</h3>
<p>Order <code>{order_id}</code> &middot; amount &#8377;{order['amount']/100:.2f} &middot; manual capture</p>
<p>Pay with test card <b>4100 2800 0000 1007</b> (domestic), any future expiry, any CVV.</p>
<pre id="result" style="background:#f4f4f4;padding:1rem;border-radius:6px">waiting for payment&hellip;</pre>
<button id="paybtn">Open payment</button>
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
// Belt-and-suspenders against Razorpay's JS re-applying an inline
// `!important` transform (which would otherwise beat the stylesheet rule
// above): watch the DOM for its injected container/iframe and force-clear
// any transform on it and its ancestors, on every mutation AND on a short
// interval as a fallback for transforms set outside a mutation (e.g. on
// window resize).
function stripRazorpayTransforms() {{
  document.querySelectorAll(
    'iframe[src*="razorpay" i], iframe[name*="razorpay" i], ' +
    'div[class*="razorpay" i], div[id*="razorpay" i]'
  ).forEach(function(el) {{
    var node = el;
    while (node && node !== document.body) {{
      if (node.style && node.style.transform && node.style.transform !== 'none') {{
        node.style.setProperty('transform', 'none', 'important');
      }}
      node = node.parentElement;
    }}
  }});
}}
new MutationObserver(stripRazorpayTransforms).observe(document.body, {{childList: true, subtree: true, attributes: true, attributeFilter: ['style']}});
setInterval(stripRazorpayTransforms, 200);

var rzp = new Razorpay({{
  key: "{key_id}",
  order_id: "{order_id}",
  amount: {order['amount']},
  currency: "INR",
  name: "Checkout Integrity Firewall (TEST)",
  description: "end-to-end capture harness",
  prefill: {{ name: "Test Buyer", contact: "+919442722399", email: "test@example.com" }},
  handler: function(resp) {{
    document.getElementById('result').textContent =
      "AUTHORIZED payment_id=" + resp.razorpay_payment_id +
      " order_id=" + resp.razorpay_order_id;
    fetch('/pay/callback', {{method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify(resp)}});
  }},
  modal: {{ ondismiss: function() {{
    document.getElementById('result').textContent = 'payment dismissed';
  }} }}
}});
document.getElementById('paybtn').onclick = function() {{ rzp.open(); }};
// NOTE: do NOT auto-call rzp.open() here. Razorpay's own docs: popups must
// be opened from a genuine user action; an on-load auto-open chained through
// further synthetic interaction can silently exhaust the page's user-
// activation state, which is the likely cause of a payment that never
// progresses past "Sending OTP" (no error, just an eternal stall). Requiring
// the button click as the ONLY trigger keeps one clean activation per open.
</script>
</body></html>"""


@app.post("/pay/callback")
async def pay_callback(payload: dict = Body(...)):
    """Checkout.js posts {razorpay_order_id, razorpay_payment_id,
    razorpay_signature} here on success. We record it in the audit log so a
    test/poller can pick up the authorized payment_id, and broadcast it."""
    order_id = payload.get("razorpay_order_id")
    payment_id = payload.get("razorpay_payment_id")
    write_audit("test_payment_authorized", order_id=order_id, payment_id=payment_id,
                detail=json.dumps(payload))
    await broadcaster.broadcast({
        "event": "test_payment_authorized", "order_id": order_id, "payment_id": payment_id,
    })

    # Mobile-app flow: the human pays via an embedded WebView with no
    # orchestrating script watching for the authorized payment (unlike
    # agent/test_refund_path.py, which polls /audit itself) -- so if this
    # order belongs to a known agent_runs row, auto-trigger the capture/
    # consistency-recheck leg right here instead of waiting on one.
    conn = get_connection()
    try:
        run = conn.execute(
            "SELECT run_id, product_id FROM agent_runs WHERE order_id = ?", (order_id,)
        ).fetchone()
    finally:
        conn.close()
    if run is not None:
        # DEMO race-condition simulation (page 3 / Modhak only): between the
        # firewall ALLOWing this order and this settlement callback, the
        # catalog price drifts up to its checkout-stage value -- 2,499, the
        # exact figure the page's own "pending rebate" injection names, and
        # what ?stage=checkout renders. agent/test_refund_path.py injects
        # this with an explicit tamper_order_price() call because a script
        # is orchestrating it there; in the mobile-app flow nothing is, so
        # it happens here. _capture_and_check's post-capture consistency
        # recheck then catches the drift (captured amount != current order
        # price) and refunds as the last-resort fallback -- exercising the
        # EXTENSION's refund path end to end. No other page is affected:
        # page 1 never drifts, page 2 never reaches an authorized payment.
        if (run["product_id"] or "").startswith("MODHAK"):
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE orders SET proposed_price = 2499.0 WHERE order_id = ?",
                    (order_id,),
                )
                conn.commit()
            finally:
                conn.close()
            write_audit("demo_race_simulated", order_id=order_id,
                        detail="orders.proposed_price drifted to 2499.0 (checkout-stage price) "
                               "after ALLOW, before capture")
        try:
            await _capture_and_check(order_id, payment_id, run["run_id"])
        except HTTPException as e:
            write_audit("capture_auto_trigger_failed", order_id=order_id, payment_id=payment_id,
                        detail=f"{e.status_code}: {e.detail}")

    return {"ok": True, "order_id": order_id, "payment_id": payment_id}


# --- POST /agent/step ---------------------------------------------------------
# Live step feed for the demo shopping agent (agent/step_logger.py). The
# agent's LLM reasoning never touches the firewall directly (see
# agent/shopping_agent.py's module docstring) -- this is purely an observer
# channel so a client can show "what the agent is doing right now" the same
# way it already shows checkout/capture decisions, over the same
# broadcaster proven in firewall/test_broadcaster.py. No decision here.

class HighlightBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class AgentStepPayload(BaseModel):
    run_id: str
    step_number: int
    title: str
    duration_s: float
    description: str
    url: str | None = None
    screenshot_base64: str | None = None
    highlight_box: HighlightBox | None = None


@app.post("/agent/step")
async def agent_step(step: AgentStepPayload):
    write_audit("agent_step", detail=json.dumps({k: v for k, v in step.model_dump().items() if k != "screenshot_base64"}))
    conn = get_connection()
    try:
        # agent_run_steps FK-references agent_runs. Standalone scripts
        # (run_demo.py, test_refund_path.py) generate their own run_id
        # without ever calling POST /agent/run, so lazily create a
        # placeholder row here -- keeps every real run visible in history
        # regardless of how it was started, and satisfies the FK either way.
        conn.execute(
            """INSERT OR IGNORE INTO agent_runs (run_id, product_id, quantity, max_price)
               VALUES (?, 'unknown', 1, 0)""",
            (step.run_id,),
        )
        conn.execute(
            """INSERT INTO agent_run_steps
               (run_id, step_number, title, duration_s, description, url, screenshot_base64, highlight_box_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (step.run_id, step.step_number, step.title, step.duration_s, step.description, step.url,
             step.screenshot_base64, json.dumps(step.highlight_box.model_dump()) if step.highlight_box else None),
        )
        conn.commit()
    finally:
        conn.close()
    await broadcaster.broadcast({"event": "agent_step", **step.model_dump()})
    return {"ok": True}


# --- POST /agent/run  +  GET /runs  +  GET /runs/{run_id} --------------------
# Mobile-app entry point: starts a real browser_use agent run server-side
# and returns immediately with a run_id, which the app then watches over
# the WebSocket (filtering by run_id) exactly like agent/run_demo.py's CLI
# already proves works. The LLM-vs-firewall boundary is unchanged -- this
# endpoint only ever calls shopping_agent.run_shopping_task, which itself
# never lets the LLM touch the firewall directly (see that module's
# docstring); everything below is deterministic Python.

from shopping_agent import run_shopping_task, complete_payment_with_agent  # noqa: E402  (needs agent/ on sys.path, done above)

_KNOWN_RUN_PRODUCTS = {
    "DERM-SUN-SE50-100": dict(page="1_dermshield_sunscreen.html", variant_label="100 ml"),
    "GAMDISK-C64": dict(page="2_gamdisk_drive.html", variant_label="64 GB"),
    "MODHAK-MS-800-6-STL": dict(page="3_modhak_jars.html", variant_label="Steel lid, 800 ml, set of 6"),
}


class AgentRunRequest(BaseModel):
    product: str
    quantity: int = 1
    max_price: float


class AgentRunResponse(BaseModel):
    run_id: str


def _execute_agent_run_sync(run_id: str, product_id: str, variant_label: str, quantity: int, max_price: float, page: str):
    """Thread entry point: run_shopping_task makes blocking `requests.*`
    calls internally (see its own docstring) -- scheduling it as a plain
    asyncio.create_task on the server's MAIN event loop would block that
    loop for the whole run's duration, stalling every other request AND
    the WebSocket broadcasts the mobile app is watching for. Running it in
    its own thread, with its own fresh event loop via asyncio.run(), keeps
    the main loop free (confirmed live: without this, POST /agent/run's
    own response was stuck behind the run it had just kicked off)."""
    asyncio.run(_execute_agent_run(run_id, product_id, variant_label, quantity, max_price, page))


async def _execute_agent_run(run_id: str, product_id: str, variant_label: str, quantity: int, max_price: float, page: str):
    base_url = "http://localhost:8000"
    page_url = f"{base_url}/store/{page}"
    try:
        result = await run_shopping_task(
            page_url=page_url, product_id=product_id, variant_label=variant_label,
            quantity=quantity, max_price=max_price, run_id=run_id,
        )
    except Exception as e:
        write_audit("agent_run_failed", detail=f"run_id={run_id}: {e}")
        update_agent_run(run_id, decision="ERROR")
        return

    fw = result["firewall_response"]
    if fw.get("decision") != "REVALIDATE":
        return  # ALLOW/BLOCK already broadcast + persisted by /checkout itself

    # REVALIDATE: the token is NOT consumed (see /checkout), and a genuine
    # SECOND real agent browse now happens against a "?stage=recheck" URL
    # (server-side stripped of the injected content in firewall/main.py's
    # store_modhak_jars -- models the merchant's compliance team pulling the
    # flagged listing content after the first pass caught it). This is a
    # real Agent.run() over a real page, not a scripted resubmission -- the
    # decision this second pass reports is genuinely its own. Only one
    # retry; if the recheck page ALSO comes back REVALIDATE, stop rather
    # than loop.
    write_audit("agent_run_revalidate_retry", detail=f"run_id={run_id}: genuine second browse at ?stage=recheck")
    recheck_url = f"{page_url}?stage=recheck"
    try:
        await run_shopping_task(
            page_url=recheck_url, product_id=product_id, variant_label=variant_label,
            quantity=quantity, max_price=max_price, run_id=run_id,
        )
    except Exception as e:
        write_audit("agent_run_failed", detail=f"run_id={run_id} (recheck pass): {e}")
        update_agent_run(run_id, decision="ERROR")


@app.post("/agent/run", response_model=AgentRunResponse)
async def post_agent_run(req: AgentRunRequest):
    cfg = _KNOWN_RUN_PRODUCTS.get(req.product)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"unknown product {req.product!r}; "
                             f"known: {list(_KNOWN_RUN_PRODUCTS)}")

    run_id = uuid.uuid4().hex[:10]
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO agent_runs (run_id, product_id, quantity, max_price) VALUES (?, ?, ?, ?)",
            (run_id, req.product, req.quantity, req.max_price),
        )
        conn.commit()
    finally:
        conn.close()

    asyncio.create_task(asyncio.to_thread(
        _execute_agent_run_sync, run_id, req.product, cfg["variant_label"], req.quantity, req.max_price, cfg["page"],
    ))
    return AgentRunResponse(run_id=run_id)


def _execute_agent_payment_sync(order_id: str, run_id: str):
    """Thread entry point mirroring _execute_agent_run_sync -- see that
    function's docstring for why this needs its own thread + fresh event
    loop rather than a plain asyncio.create_task on the main loop."""
    asyncio.run(complete_payment_with_agent(order_id, run_id, report_steps=True))


@app.post("/agent/run/{run_id}/pay")
async def post_agent_run_pay(run_id: str):
    """Triggers the SAME real payment-completing agent used by
    agent/test_refund_path.py -- a second browser_use.Agent drives the
    actual Razorpay TEST-mode checkout at /pay?order_id=... in its own
    real Chrome tab. Whether a human taps through that page (the WebView
    path) or this agent does, Checkout.js's handler fires identically and
    posts to /pay/callback, which already auto-triggers capture/refund for
    any order_id tied to a known agent_runs row (see pay_callback below) --
    so nothing else needs to change for the agent-pays path to work."""
    conn = get_connection()
    try:
        run = conn.execute("SELECT order_id FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    if not run["order_id"]:
        raise HTTPException(status_code=400, detail="run has no order yet -- checkout must ALLOW first")

    asyncio.create_task(asyncio.to_thread(_execute_agent_payment_sync, run["order_id"], run_id))
    return {"ok": True}


@app.get("/runs")
def get_runs(limit: int = 50):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/runs/{run_id}")
def get_run_detail(run_id: str):
    conn = get_connection()
    try:
        run = conn.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        steps = conn.execute(
            "SELECT * FROM agent_run_steps WHERE run_id = ? ORDER BY step_number", (run_id,)
        ).fetchall()
    finally:
        conn.close()

    run_dict = dict(run)
    run_dict["hard_block_reasons"] = json.loads(run_dict["hard_block_reasons_json"]) if run_dict.get("hard_block_reasons_json") else []
    run_dict.pop("hard_block_reasons_json", None)
    step_list = []
    for s in steps:
        sd = dict(s)
        if sd.get("highlight_box_json"):
            sd["highlight_box"] = json.loads(sd["highlight_box_json"])
        sd.pop("highlight_box_json", None)
        step_list.append(sd)
    run_dict["steps"] = step_list
    return run_dict


# --- GET /audit ---------------------------------------------------------------

@app.get("/audit")
def get_audit(limit: int = 50):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# --- WebSocket /ws --------------------------------------------------------------
# Live decision push for the mobile app. Client-side should keep a polling
# fallback (GET /audit) in case the socket drops mid-demo (Section 6).

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            await ws.receive_text()  # client doesn't need to send anything; just keep the connection open
    except WebSocketDisconnect:
        broadcaster.disconnect(ws)

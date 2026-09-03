"""
main.py

FastAPI firewall middleware -- CORE gate (this pass): intent capture ->
catalog snapshot -> checkout decision. EXTENSION (post-capture recheck +
refund fallback) and the audit/WebSocket layer come in the next pass.

Every decision, allowed or not, writes an audit_log row -- must-have per
the plan doc's judging-rubric requirement for an immutable decision
envelope.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from broadcaster import broadcaster

from db import init_db, get_connection
from tokens import issue_token, validate_token, consume_token, TokenError
from catalog import take_snapshot, check_freshness
from risk import evaluate, check_hard_blocks
from razorpay_client import create_order, fetch_payment, capture_payment, refund_payment

app = FastAPI(title="Checkout Integrity Firewall")


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
            "event": "checkout_decision", "decision": decision.decision,
            "risk_score": decision.risk_score, "hard_block_reasons": decision.hard_block_reasons,
        })
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
        "event": "checkout_decision", "decision": "ALLOW",
        "risk_score": decision.risk_score, "razorpay_order_id": order["id"],
    })

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


@app.post("/payments/capture")
async def post_capture(req: CaptureRequest):
    conn = get_connection()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (req.order_id,)
        ).fetchone()
    finally:
        conn.close()
    if order is None:
        raise HTTPException(status_code=404, detail="order_not_found")

    # 1. fetch the payment from Razorpay directly -- never trust a caller-
    #    supplied amount, always verify against Razorpay's own record
    payment = fetch_payment(req.payment_id)
    if payment["status"] != "authorized":
        write_audit("capture_rejected", order_id=req.order_id, payment_id=req.payment_id,
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
            (req.payment_id, req.order_id, amount_rupees),
        )
        conn.commit()
        cur = conn.execute(
            "UPDATE payments SET captured = 1 WHERE payment_id = ? AND captured = 0",
            (req.payment_id,),
        )
        conn.commit()
        won_race = cur.rowcount == 1
    finally:
        conn.close()

    if not won_race:
        write_audit("capture_race_lost", order_id=req.order_id, payment_id=req.payment_id,
                    detail="payment already captured by a prior request")
        raise HTTPException(status_code=409, detail="already_captured")

    # 3. consistency recheck: does the order STILL match the original intent?
    #    (defense in depth -- checkout already verified this once, but state
    #    could have drifted between order-creation and capture-time)
    conn = get_connection()
    try:
        intent = conn.execute(
            "SELECT * FROM intents WHERE token = ?", (order["token"],)
        ).fetchone()
    finally:
        conn.close()

    consistency_reasons = check_hard_blocks(
        dict(intent), order["proposed_price"], order["proposed_sku"], order["proposed_qty"]
    )
    consistent = len(consistency_reasons) == 0 and abs(amount_rupees - order["proposed_price"]) < 0.01

    conn = get_connection()
    try:
        if consistent:
            capture_payment(req.payment_id, amount_rupees)
            conn.execute(
                """UPDATE payments SET consistency_recheck_passed = 1, captured_at = datetime('now')
                   WHERE payment_id = ?""",
                (req.payment_id,),
            )
            conn.commit()
            write_audit("payment_captured", order_id=req.order_id, payment_id=req.payment_id,
                        detail=f"amount={amount_rupees}")
            await broadcaster.broadcast({
                "event": "payment_captured", "order_id": req.order_id, "amount": amount_rupees,
            })
            return {"status": "captured", "amount": amount_rupees}
        else:
            # 4. inconsistent post-capture state -- refund is the fallback,
            #    never the first response (Section 1, EXTENSION)
            refund_payment(req.payment_id, notes={"reason": "post_capture_consistency_failed"})
            conn.execute(
                """UPDATE payments SET consistency_recheck_passed = 0, refunded = 1,
                   captured_at = datetime('now') WHERE payment_id = ?""",
                (req.payment_id,),
            )
            conn.commit()
            write_audit("payment_refunded", order_id=req.order_id, payment_id=req.payment_id,
                        detail=f"consistency_failed: {consistency_reasons}")
            await broadcaster.broadcast({
                "event": "payment_refunded", "order_id": req.order_id, "reason": consistency_reasons,
            })
            return {"status": "refunded", "reason": consistency_reasons}
    finally:
        conn.close()


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

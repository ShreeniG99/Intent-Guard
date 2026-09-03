"""
tokens.py

Capability tokens: bind a customer's captured purchase intent (product,
variant, qty, max_price) to one checkout attempt. Issued when the
customer states intent, validated (and consumed, single-use) when the
agent attempts checkout. An expired, unknown, or already-consumed token
is a hard block per the risk formula (plan doc Section 3/11) -- it
bypasses scoring entirely, it's not "risky but allowed".
"""
import secrets
from datetime import datetime, timedelta, timezone

from db import get_connection

DEFAULT_TTL_MINUTES = 30


def issue_token(product_id: str, quantity: int, max_price: float,
                 variant: str = None, currency: str = "INR",
                 customer_ref: str = None,
                 ttl_minutes: int = DEFAULT_TTL_MINUTES) -> dict:
    """Called when the customer states intent, before the agent starts
    shopping. Returns the token and its expiry."""
    token = secrets.token_urlsafe(24)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO intents
               (token, product_id, variant, quantity, max_price, currency,
                customer_ref, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (token, product_id, variant, quantity, max_price, currency,
             customer_ref, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {"token": token, "expires_at": expires_at}


class TokenError(Exception):
    """Raised for any invalid-token condition. The caller (checkout
    endpoint) treats ANY TokenError as a hard block, no scoring."""
    pass


def validate_token(token: str) -> dict:
    """Look up the intent for a token. Raises TokenError if unknown,
    expired, or already consumed. Does NOT consume it -- call
    consume_token() separately, only once the checkout actually proceeds,
    so a failed/retried request doesn't burn the one-time use."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM intents WHERE token = ?", (token,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise TokenError("unknown_token")
    if row["consumed"]:
        raise TokenError("token_already_consumed")

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise TokenError("token_expired")

    return dict(row)


def consume_token(token: str) -> None:
    """Mark a token used. Single-use: an atomic UPDATE...WHERE, same
    compare-and-swap pattern as the payments table (plan doc Section 6a)
    -- prevents a race where two concurrent checkout attempts both pass
    validate_token() before either consumes it."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE intents SET consumed = 1 WHERE token = ? AND consumed = 0",
            (token,),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise TokenError("token_already_consumed")
    finally:
        conn.close()


if __name__ == "__main__":
    from db import init_db
    init_db()

    result = issue_token(product_id="SKU123", quantity=2, max_price=1500.0, variant="Blue / L")
    print("Issued:", result)

    intent = validate_token(result["token"])
    print("Validated OK:", {k: intent[k] for k in ("product_id", "quantity", "max_price", "variant")})

    consume_token(result["token"])
    print("Consumed OK")

    try:
        validate_token(result["token"])
        print("ERROR: should have raised TokenError")
    except TokenError as e:
        print(f"Correctly rejected reuse: {e}")

    try:
        validate_token("not-a-real-token")
        print("ERROR: should have raised TokenError")
    except TokenError as e:
        print(f"Correctly rejected unknown token: {e}")

"""
razorpay_client.py

Thin wrapper around the official `razorpay` Python SDK, using the
manual-capture flow per plan doc Section 5/6:
  1. create_order()   -- POST /v1/orders with payment_capture=0
  2. capture_payment() -- POST /v1/payments/{id}/capture (only after our
                           post-capture consistency check, EXTENSION)
  3. fetch_payment()   -- GET /v1/payments/{id}
  4. refund_payment()  -- POST /v1/payments/{id}/refund -- fallback of
                           last resort for race conditions, never the
                           first response (Section 1, EXTENSION)

Reads credentials from environment variables (via .env, never hardcoded
or logged): RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET. Test-mode keys
(rzp_test_...) only -- this project never touches live payments.
"""
import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client() -> razorpay.Client:
    global _client
    if _client is not None:
        return _client

    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set. Copy .env.example to "
            ".env and fill in your TEST MODE keys from the Razorpay dashboard."
        )
    if not key_id.startswith("rzp_test_"):
        raise RuntimeError(
            f"Refusing to proceed: key '{key_id[:12]}...' does not look like a "
            "test-mode key (expected rzp_test_ prefix). This project must never "
            "touch live payments."
        )

    _client = razorpay.Client(auth=(key_id, key_secret))
    return _client


def create_order(amount_rupees: float, currency: str = "INR", receipt: str = None,
                  notes: dict = None) -> dict:
    """amount_rupees is in whole rupees; Razorpay's API wants paise (integer)."""
    client = get_client()
    order = client.order.create({
        "amount": int(round(amount_rupees * 100)),
        "currency": currency,
        "receipt": receipt,
        "payment_capture": 0,  # manual capture -- our checkpoint
        "notes": notes or {},
    })
    return order


def capture_payment(payment_id: str, amount_rupees: float, currency: str = "INR") -> dict:
    client = get_client()
    return client.payment.capture(payment_id, int(round(amount_rupees * 100)), {"currency": currency})


def fetch_payment(payment_id: str) -> dict:
    client = get_client()
    return client.payment.fetch(payment_id)


def refund_payment(payment_id: str, amount_rupees: float = None, notes: dict = None) -> dict:
    """amount_rupees=None means full refund."""
    client = get_client()
    data = {"notes": notes or {}}
    if amount_rupees is not None:
        data["amount"] = int(round(amount_rupees * 100))
    return client.payment.refund(payment_id, data)


if __name__ == "__main__":
    print("Testing Razorpay test-mode connectivity...")
    order = create_order(amount_rupees=100.0, receipt="test-receipt-001",
                          notes={"purpose": "firewall connectivity smoke test"})
    print(f"Created test order: id={order['id']} amount={order['amount']} status={order['status']}")
    print("\nThis order has NO payment yet (that requires a checkout UI or test card flow -- ")
    print("normal for this smoke test, which only confirms create_order() reaches Razorpay).")

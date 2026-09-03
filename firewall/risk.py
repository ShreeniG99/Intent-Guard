"""
risk.py

The risk-score formula and hard-block checks, as one reusable module --
single source of truth for both run_eval.py (offline eval) and main.py
(live firewall middleware). Formula and thresholds per plan doc Section
3/11; provenance of the specific weights is documented there honestly
(untuned heuristic, not drawn from a published source).
"""
from dataclasses import dataclass, field


def compute_risk_score(deterministic_score: int, injection_confidence: float) -> float:
    return min(100.0, deterministic_score + 0.3 * injection_confidence * 100)


def decide(risk_score: float) -> str:
    if risk_score >= 60:
        return "BLOCK"
    if risk_score >= 20:
        return "REVALIDATE"
    return "ALLOW"


def check_hard_blocks(intent: dict, proposed_price: float,
                       proposed_sku: str, proposed_qty: int) -> list:
    """intent is a row from the intents table (or equivalent dict) with
    product_id, variant, quantity, max_price. Returns a list of hard-block
    reason strings -- empty list means none triggered. ANY non-empty
    result means BLOCK, full stop, regardless of risk_score."""
    reasons = []

    if proposed_price is not None and proposed_price > intent["max_price"]:
        reasons.append(
            f"price_exceeds_max: proposed={proposed_price} max={intent['max_price']}"
        )

    intent_sku = intent.get("product_id") if isinstance(intent, dict) else intent["product_id"]
    if proposed_sku is not None and intent_sku is not None and proposed_sku != intent_sku:
        reasons.append(f"sku_mismatch: proposed={proposed_sku} intent={intent_sku}")

    intent_qty = intent.get("quantity") if isinstance(intent, dict) else intent["quantity"]
    if proposed_qty is not None and intent_qty is not None and proposed_qty != intent_qty:
        reasons.append(f"quantity_mismatch: proposed={proposed_qty} intent={intent_qty}")

    return reasons


@dataclass
class Decision:
    decision: str               # ALLOW | REVALIDATE | BLOCK
    risk_score: float
    hard_block_reasons: list = field(default_factory=list)
    deterministic_score: int = 0
    injection_confidence: float = 0.0

    @property
    def flagged(self) -> bool:
        return self.decision != "ALLOW"


def evaluate(intent: dict, proposed_price: float, proposed_sku: str,
             proposed_qty: int, deterministic_score: int,
             injection_confidence: float) -> Decision:
    """The single entry point both run_eval.py and main.py should call.
    Hard blocks are checked FIRST and short-circuit the score entirely --
    they are facts, not probabilities, so there's nothing to weigh."""
    hard_blocks = check_hard_blocks(intent, proposed_price, proposed_sku, proposed_qty)
    risk_score = compute_risk_score(deterministic_score, injection_confidence)

    if hard_blocks:
        final_decision = "BLOCK"
    else:
        final_decision = decide(risk_score)

    return Decision(
        decision=final_decision,
        risk_score=risk_score,
        hard_block_reasons=hard_blocks,
        deterministic_score=deterministic_score,
        injection_confidence=injection_confidence,
    )


if __name__ == "__main__":
    intent = {"product_id": "SKU123", "quantity": 2, "max_price": 1500.0}

    print("--- case 1: clean, matches intent exactly ---")
    d = evaluate(intent, proposed_price=1200.0, proposed_sku="SKU123", proposed_qty=2,
                 deterministic_score=0, injection_confidence=0.02)
    print(d)
    assert d.decision == "ALLOW"

    print("\n--- case 2: price exceeds max_price (hard block) ---")
    d = evaluate(intent, proposed_price=1800.0, proposed_sku="SKU123", proposed_qty=2,
                 deterministic_score=0, injection_confidence=0.02)
    print(d)
    assert d.decision == "BLOCK" and "price_exceeds_max" in d.hard_block_reasons[0]

    print("\n--- case 3: SKU swapped mid-checkout (hard block) ---")
    d = evaluate(intent, proposed_price=1200.0, proposed_sku="SKU999", proposed_qty=2,
                 deterministic_score=0, injection_confidence=0.02)
    print(d)
    assert d.decision == "BLOCK"

    print("\n--- case 4: no hard block, but content flagged mid-range (REVALIDATE) ---")
    d = evaluate(intent, proposed_price=1200.0, proposed_sku="SKU123", proposed_qty=2,
                 deterministic_score=25, injection_confidence=0.1)
    print(d)
    assert d.decision == "REVALIDATE"

    print("\n--- case 5: no hard block, high injection confidence (BLOCK via score) ---")
    d = evaluate(intent, proposed_price=1200.0, proposed_sku="SKU123", proposed_qty=2,
                 deterministic_score=40, injection_confidence=0.95)
    print(d)
    assert d.decision == "BLOCK"

    print("\nAll 5 cases passed.")

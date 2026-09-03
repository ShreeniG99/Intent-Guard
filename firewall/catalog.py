"""
catalog.py

Catalog snapshotting + freshness checking. A "snapshot" is the sanitized/
classified content the agent saw for a product, plus a hash of its
structured fields (price/sku/qty) and normalized text. At checkout time
we take a FRESH snapshot and compare hashes against the one taken when
the agent first browsed -- a mismatch means the catalog state changed
(or was manipulated) between browse and checkout, which is the "product
state changed" check from Section 1's CORE description.
"""
import hashlib
import json


def compute_content_hash(normalized_text: str, price: float = None,
                          sku: str = None, quantity_available: int = None) -> str:
    """Pure function: canonical serialization -> sha256 hex digest.
    Deliberately includes price/sku/qty in the hash, not just the text --
    a page whose visible copy is identical but whose price silently
    changed must still hash differently."""
    canonical = json.dumps({
        "text": normalized_text.strip(),
        "price": price,
        "sku": sku,
        "quantity_available": quantity_available,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def take_snapshot(token: str, product_id: str, surface: str, raw_text: str,
                   price: float = None, sku: str = None,
                   quantity_available: int = None) -> dict:
    """Full orchestration: sanitize -> classify -> hash -> persist.
    Needs the ProtectAI v2 classifier and a live DB connection, so this
    function can only run in an environment with both (your terminal,
    not the bridge shell)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from sanitizer import sanitize
    from classifier import classify
    from db import get_connection

    san = sanitize(raw_text)
    clf = classify(san["normalized_text"])
    content_hash = compute_content_hash(san["normalized_text"], price, sku, quantity_available)

    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO catalog_snapshots
               (token, product_id, surface, raw_text, normalized_text, content_hash,
                deterministic_score, injection_confidence, price, sku, quantity_available)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (token, product_id, surface, raw_text, san["normalized_text"], content_hash,
             san["deterministic_score"], clf["injection_confidence"], price, sku, quantity_available),
        )
        conn.commit()
        snapshot_id = cur.lastrowid
    finally:
        conn.close()

    return {
        "id": snapshot_id,
        "content_hash": content_hash,
        "deterministic_score": san["deterministic_score"],
        "injection_confidence": clf["injection_confidence"],
        "normalized_text": san["normalized_text"],
    }


def check_freshness(previous_snapshot_id: int, current_raw_text: str,
                     current_price: float = None, current_sku: str = None,
                     current_quantity_available: int = None) -> dict:
    """Re-sanitizes/classifies CURRENT content and compares its hash
    against the stored snapshot from browse-time. Returns whether the
    catalog state drifted, plus the fresh scores (so a drifted-but-still-
    clean page isn't automatically treated as an attack -- drift alone
    triggers a re-browse/retry per Section 1, not an automatic block)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from sanitizer import sanitize
    from classifier import classify
    from db import get_connection

    conn = get_connection()
    try:
        prev = conn.execute(
            "SELECT * FROM catalog_snapshots WHERE id = ?", (previous_snapshot_id,)
        ).fetchone()
    finally:
        conn.close()

    if prev is None:
        raise ValueError(f"no snapshot with id {previous_snapshot_id}")

    san = sanitize(current_raw_text)
    clf = classify(san["normalized_text"])
    current_hash = compute_content_hash(
        san["normalized_text"], current_price, current_sku, current_quantity_available
    )

    return {
        "fresh": current_hash == prev["content_hash"],
        "previous_hash": prev["content_hash"],
        "current_hash": current_hash,
        "current_deterministic_score": san["deterministic_score"],
        "current_injection_confidence": clf["injection_confidence"],
    }


if __name__ == "__main__":
    # pure-function test, no DB/classifier needed
    h1 = compute_content_hash("Wireless earbuds, 24h battery.", price=1200.0, sku="SKU123", quantity_available=5)
    h2 = compute_content_hash("Wireless earbuds, 24h battery.", price=1200.0, sku="SKU123", quantity_available=5)
    h3 = compute_content_hash("Wireless earbuds, 24h battery.", price=999.0, sku="SKU123", quantity_available=5)
    print(f"identical inputs -> same hash: {h1 == h2}")
    print(f"price changed -> different hash: {h1 != h3}")
    assert h1 == h2
    assert h1 != h3
    print("Pure-function hash tests passed.")
    print("\n(take_snapshot/check_freshness need the classifier + DB -- run via a")
    print(" separate script in your terminal once main.py exists to exercise them.)")

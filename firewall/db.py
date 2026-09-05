"""
db.py

SQLite state store for the checkout integrity firewall. WAL mode +
UPDATE...WHERE compare-and-swap, per plan doc Section 6a (no Redis --
this is sufficient, validated by AIP-Bench's own Experiment D).

Five tables:
  intents           - customer's stated purchase intent, captured before
                       the agent starts shopping. One row per checkout
                       attempt, keyed by a capability token.
  catalog_snapshots - hashed + sanitized/classified product content the
                       agent actually saw, for freshness comparison.
  orders             - what got submitted to Razorpay: proposed vs intent,
                       the risk score, and the ALLOW/REVALIDATE/BLOCK decision.
  payments           - capture state. `captured` starts at 0; the atomic
                       compare-and-swap is `UPDATE payments SET captured=1
                       WHERE payment_id=? AND captured=0`.
  audit_log          - append-only. Every decision the firewall makes,
                       with full flags and scores, immutable once written.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "firewall_state.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS intents (
    token           TEXT PRIMARY KEY,
    product_id      TEXT NOT NULL,
    variant         TEXT,
    quantity        INTEGER NOT NULL,
    max_price       REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    customer_ref    TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at       TEXT NOT NULL,
    consumed         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    token               TEXT NOT NULL REFERENCES intents(token),
    product_id          TEXT NOT NULL,
    surface             TEXT NOT NULL,
    raw_text            TEXT NOT NULL,
    normalized_text     TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    deterministic_score INTEGER NOT NULL,
    injection_confidence REAL NOT NULL,
    price               REAL,
    sku                 TEXT,
    quantity_available  INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    token           TEXT NOT NULL REFERENCES intents(token),
    snapshot_id     INTEGER REFERENCES catalog_snapshots(id),
    proposed_price  REAL NOT NULL,
    proposed_sku    TEXT,
    proposed_qty    INTEGER NOT NULL,
    risk_score      REAL NOT NULL,
    decision        TEXT NOT NULL,
    razorpay_order_id TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id      TEXT PRIMARY KEY,
    order_id        TEXT NOT NULL REFERENCES orders(order_id),
    amount          REAL NOT NULL,
    captured        INTEGER NOT NULL DEFAULT 0,
    consistency_recheck_passed INTEGER,
    refunded        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    captured_at     TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    token           TEXT,
    order_id        TEXT,
    payment_id      TEXT,
    decision        TEXT,
    risk_score      REAL,
    flags_json      TEXT,
    detail          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Mobile-app-facing run tracking. One row per POST /agent/run, updated as
-- the run progresses (checkout_decision, payment_captured/refunded) so
-- GET /runs and GET /runs/{run_id} have a single place to read from
-- instead of joining across intents/orders/payments by hand.
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id          TEXT PRIMARY KEY,
    product_id      TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    max_price       REAL NOT NULL,
    decision        TEXT,
    risk_score      REAL,
    hard_block_reasons_json TEXT,
    order_id        TEXT,
    payment_status  TEXT,
    amount          REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_run_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES agent_runs(run_id),
    step_number     INTEGER NOT NULL,
    title           TEXT NOT NULL,
    duration_s      REAL NOT NULL,
    description     TEXT NOT NULL,
    url             TEXT,
    screenshot_base64 TEXT,
    highlight_box_json TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {os.path.abspath(DB_PATH)}")
    conn = get_connection()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", [t["name"] for t in tables])
    conn.close()

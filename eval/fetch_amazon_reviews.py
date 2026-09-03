"""
fetch_amazon_reviews.py

Pulls real product-review text from McAuley-Lab/Amazon-Reviews-2023 for our
eval set's CLEAN baseline class. This needs Hugging Face access, which is
why you're running it yourself instead of me running it.

v2 (Sept 3 2026): expanded from 1 category/30 rows to 3 categories/~120 rows,
per the "expand the clean pool" decision -- same real source, just less
arbitrarily capped. This OVERWRITES amazon_reviews_sample.json; the prior
30-row file is fully superseded (all rows in it were real, nothing lost in
kind, just regenerated larger).

v3 (Sept 3 2026): `datasets` 4.x dropped support for loading scripts, and
McAuley-Lab/Amazon-Reviews-2023 is script-based, so load_dataset() no longer
works for it. Switched to streaming the raw category jsonl files directly over
HTTP (huggingface.co/.../resolve/main/raw/review_categories/<Category>.jsonl)
and stopping early. Same real dataset, same fields, different transport.

Run from the eval/ folder:  python fetch_amazon_reviews.py
"""
import json

import requests
from huggingface_hub import hf_hub_url

OUT_PATH = "amazon_reviews_sample.json"

# 3 categories for thematic variety in the mock merchant's catalog.
# Full category list: huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023
CATEGORIES = ["All_Beauty", "Electronics", "Home_and_Kitchen"]
TARGET_PER_CATEGORY = 40  # ~120 total across 3 categories


def fetch_category(category: str, target: int) -> list:
    url = hf_hub_url(
        "McAuley-Lab/Amazon-Reviews-2023",
        f"raw/review_categories/{category}.jsonl",
        repo_type="dataset",
    )
    rows = []
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            ex = json.loads(line)
            title = (ex.get("title") or "").strip()
            text = (ex.get("text") or "").strip()
            # skip empty, tiny, or huge reviews -- want realistic
            # catalog-adjacent length
            if 40 < len(text) < 600:
                rows.append({
                    "title": title,
                    "text": text,
                    "rating": ex.get("rating"),
                    "category": category,
                })
            if len(rows) >= target:
                break
    return rows


def main():
    all_rows = []
    for category in CATEGORIES:
        print(f"Fetching {category} ...")
        rows = fetch_category(category, TARGET_PER_CATEGORY)
        print(f"  got {len(rows)} rows")
        all_rows.extend(rows)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_rows)} real reviews to {OUT_PATH}")
    print("Per-category counts:")
    counts = {}
    for r in all_rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    for cat, n in counts.items():
        print(f"  {cat}: {n}")


if __name__ == "__main__":
    main()

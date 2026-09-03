"""
fetch_ragdoll_coupons.py

Real CLEAN `coupon`-surface content for the eval set -- the promo / discount /
offer banners on real retail product pages. Source: Bai-YT/RAGDOLL's
`webpage_contents/<category>/pages/*.html` (CC-BY-4.0, already used for the
description and alt_text surfaces).

Why this closes a real gap: the eval schema has a `coupon` surface with zero
data. Amazon-Reviews-2023 product metadata was tried first and turned out
almost promo-free (~1 in 4000 products), because Amazon applies promotions at
the platform layer, not in the listing text. Real retailer pages (LG,
Maybelline, Porter-Cable, Charlotte Tilbury, ...) carry actual promo copy in
the page body -- "20% OFF ALL KITS & SETS", "PROMO CODE: GETFLSTUDIO",
"Sign up to receive 15% off your first order", "FREE SHIPPING & RETURNS ON ALL
ORDERS" -- and RAGDOLL's raw HTML preserves it.

Extraction: strip script/style, walk short text nodes, keep those 12-160 chars
that match a promo/discount/offer regex, dedupe case-insensitively, cap per
page. Every string returned is a verbatim text node from a real retail page --
preprocessing, not authoring.

NOTE ON SURFACE: these are the CLEAN `coupon` class only. There is still no
real source for INJECTED coupon-surface content (a prompt injection planted in
a promo field); that stays uncovered, by decision, per the plan.

Run from the eval/ folder:  python fetch_ragdoll_coupons.py
Writes: ragdoll_coupons.json  (list of {category, source_path, text})
"""
import json
import re
import time

from bs4 import BeautifulSoup
from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "Bai-YT/RAGDOLL"
OUT_PATH = "ragdoll_coupons.json"
CATEGORIES_TARGET = 50
PAGES_PER_CATEGORY = 5
COUPONS_PER_PAGE = 3
MIN_LEN, MAX_LEN = 18, 140
TARGET_TOTAL = 90

PROMO = re.compile(
    r"\d+\s*%\s*off|\bsave \$?\d|\bfree shipping\b|\bfree returns\b|"
    r"limited[- ]time|today only|flash sale|clearance|\bwas \$\d|\buse code\b|"
    r"promo code|\bcoupon\b|gift with purchase|\b\$\d+(\.\d\d)? off\b|"
    r"\boff\b.{0,15}\bcode\b|buy \d .{0,20} get|\bbogo\b|"
    r"\d+%\s*off your (first|next) order|sign up .{0,20}\d+%\s*off",
    re.I,
)

# nav / account chrome that means the node is a menu, not a promo banner
CHROME = re.compile(
    r"\b(menu|search|login|log in|register|sign in|my account|my cart|your bag|"
    r"view all|shop all|find a retailer|help \+ support|faqs?|careers|"
    r"forgot your password|create account|create an account)\b",
    re.I,
)
DOUBLED_WORD = re.compile(r"\b(\w{3,})\b\s+\b\1\b", re.I)


def clean_candidate(t: str) -> bool:
    if not (MIN_LEN <= len(t) <= MAX_LEN):
        return False
    if not PROMO.search(t):
        return False
    if DOUBLED_WORD.search(t):          # "MORE MORE", "About About"
        return False
    if len(CHROME.findall(t)) >= 2:     # nav list that happens to contain "off"/"coupon"
        return False
    # promo phrasing should be a real part of the node, not one word in a long menu
    caps_runs = re.findall(r"(?:\b[A-Z][A-Za-z&]+\b[ ]){4,}", t)
    return not caps_runs or "%" in t or "$" in t or "code" in t.lower()


def dedupe_substrings(cands: list) -> list:
    kept = []
    for c in sorted(cands, key=len):          # shortest first
        cl = c.lower()
        if any(cl in k.lower() or k.lower() in cl for k in kept):
            continue
        kept.append(c)
    return kept


def download_with_retry(path: str, attempts: int = 6):
    for i in range(attempts):
        try:
            return hf_hub_download(REPO_ID, path, repo_type="dataset", etag_timeout=60)
        except Exception as e:
            if i == attempts - 1:
                raise
            print(f"    retry {i + 1} ({type(e).__name__}) for {path}")
            time.sleep(3)


def main():
    api = HfApi()
    files = api.list_repo_files(REPO_ID, repo_type="dataset")
    page_files = [f for f in files if "/pages/" in f and f.endswith(".html")]

    by_category = {}
    for f in page_files:
        parts = f.split("/")
        if len(parts) == 4 and parts[0] == "webpage_contents":
            by_category.setdefault(parts[1], []).append(f)
    by_category.pop(".DS_Store", None)

    rows = []
    seen = set()
    for category in sorted(by_category)[:CATEGORIES_TARGET]:
        if len(rows) >= TARGET_TOTAL:
            break
        paths = sorted(by_category[category],
                       key=lambda p: int(p.rsplit("/", 1)[1].removesuffix(".html")))
        for path in paths[:PAGES_PER_CATEGORY]:
            local = download_with_retry(path)
            with open(local, encoding="utf-8", errors="ignore") as fh:
                soup = BeautifulSoup(fh.read(), "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            page_cands = []
            for el in soup.find_all(["span", "div", "p", "a", "li", "h2", "h3",
                                     "strong", "small", "button"]):
                t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
                if clean_candidate(t):
                    page_cands.append(t)
            kept = 0
            for t in dedupe_substrings(page_cands):
                key = t.lower()
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"category": category, "source_path": path, "text": t})
                kept += 1
                if kept >= COUPONS_PER_PAGE:
                    break
        print(f"  {category}: {sum(1 for r in rows if r['category'] == category)} coupons")

    rows = rows[:TARGET_TOTAL]
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(rows)} real coupon-surface rows to {OUT_PATH}")
    print("Sample:")
    for r in rows[:8]:
        print(f"  [{r['category']}] {r['text']!r}")


if __name__ == "__main__":
    main()

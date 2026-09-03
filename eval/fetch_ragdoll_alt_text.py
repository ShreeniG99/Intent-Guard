"""
fetch_ragdoll_alt_text.py

Real CLEAN `alt_text`-surface content for the eval set -- the image `alt`
attributes on real retail product pages. Source: Bai-YT/RAGDOLL's
`webpage_contents/<category>/pages/*.html` (raw scraped product pages,
CC-BY-4.0, already used for the description surface).

Why this closes a real gap: the eval schema has always had an `alt_text`
surface with zero data. `alt` attributes are exactly the "text an agent reads
that a sighted user doesn't" channel, and real ones (product names, brand
slogans, promo-banner captions) are sitting in the RAGDOLL page HTML already.

Extraction: parse every `<img alt="...">`, keep alts that look like real
caption text (15-200 chars, >55% alphabetic), drop pure UI chrome via a small
substring blocklist (cart/menu/icon/logo/etc.), dedupe case-insensitively.
This is ordinary preprocessing, not authoring -- every string returned is a
verbatim `alt` value from a real page.

Run from the eval/ folder:  python fetch_ragdoll_alt_text.py
Writes: ragdoll_alt_text.json  (list of {category, source_path, text})
"""
import json
import re
import time

from bs4 import BeautifulSoup
from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "Bai-YT/RAGDOLL"
OUT_PATH = "ragdoll_alt_text.json"
CATEGORIES_TARGET = 50     # all categories
PAGES_PER_CATEGORY = 3
ALTS_PER_PAGE = 4          # cap per page so no single page dominates
MIN_LEN, MAX_LEN = 15, 200
TARGET_TOTAL = 200

# pure UI-chrome alt text we don't want as "product page alt_text" samples
CHROME = re.compile(
    r"\b(cart|menu|icon|logo|search|close|arrow|caret|chevron|spinner|loading|"
    r"placeholder|thumbnail|swatch|breadcrumb|hamburger|facebook|twitter|"
    r"instagram|youtube|pinterest|linkedin|tiktok|social|share this|"
    r"back to top|scroll|previous|next slide|play video|pause)\b",
    re.I,
)


def download_with_retry(path: str, attempts: int = 6):
    for i in range(attempts):
        try:
            return hf_hub_download(REPO_ID, path, repo_type="dataset", etag_timeout=60)
        except Exception as e:
            if i == attempts - 1:
                raise
            print(f"    retry {i + 1} ({type(e).__name__}) for {path}")
            time.sleep(3)


URLISH = re.compile(r"https?://|//\S+/|\.(png|jpe?g|gif|svg|webp|bmp)\b", re.I)


def usable(alt: str) -> bool:
    if not (MIN_LEN <= len(alt) <= MAX_LEN):
        return False
    if CHROME.search(alt) or URLISH.search(alt):
        return False
    if " " not in alt and ("_" in alt or "-" in alt):   # bare filename/slug
        return False
    alpha = sum(c.isalpha() for c in alt) / max(len(alt), 1)
    return alpha > 0.55


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
        pages_used = 0
        for path in paths:
            if pages_used >= PAGES_PER_CATEGORY:
                break
            local = download_with_retry(path)
            with open(local, encoding="utf-8", errors="ignore") as fh:
                soup = BeautifulSoup(fh.read(), "lxml")
            kept = 0
            for img in soup.find_all("img"):
                alt = re.sub(r"\s+", " ", (img.get("alt") or "")).strip()
                key = alt.lower()
                if not usable(alt) or key in seen:
                    continue
                seen.add(key)
                rows.append({"category": category, "source_path": path, "text": alt})
                kept += 1
                if kept >= ALTS_PER_PAGE:
                    break
            if kept:
                pages_used += 1
        print(f"  {category}: {sum(1 for r in rows if r['category'] == category)} alts")

    rows = rows[:TARGET_TOTAL]
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(rows)} real alt_text rows to {OUT_PATH}")
    print("Sample:")
    for r in rows[:6]:
        print(f"  [{r['category']}] {r['text']!r}")


if __name__ == "__main__":
    main()

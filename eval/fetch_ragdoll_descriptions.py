"""
fetch_ragdoll_descriptions.py

Pulls real product DESCRIPTION text (distinct from Amazon Reviews' review-
surface text) from Bai-YT/RAGDOLL for the eval set's clean baseline class,
closing the "no real clean description-surface text" gap.

CC-BY-4.0, no gating -- confirmed accessible. Needs Hugging Face access,
so run this yourself, same as fetch_amazon_reviews.py.

    Run from the eval/ folder:  python fetch_ragdoll_descriptions.py

---
SOURCE-FOLDER CHANGE (Sept 3 2026): the original version of this script
scraped `webpage_contents/<cat>/pages/<n>.html` (raw HTML) and ran a
longest-text-block heuristic to guess where the description was. While
running it, RAGDOLL was found to also ship
`webpage_contents/<cat>/content_extract/<n>.txt` -- the dataset authors'
OWN extraction of the product-description text from that same page
(produced by their collection pipeline; see collection_pipeline/ in the
repo). That is strictly better for our purpose: it's still 100% real
RAGDOLL data, one description per real product page, but the "which block
is the description" decision was made by the dataset authors, not by a
heuristic in this file. So this script now reads content_extract/ directly.
No BeautifulSoup, no guessing. The pages/ HTML is left untouched.

content_extract layout: 50 categories x 8 products = 400 files, named
`<cat>/content_extract/0.txt` .. `7.txt`. Text nodes are joined with " / "
by the upstream extractor; we collapse that plus other whitespace runs to
single spaces. Rows shorter than MIN_LEN after cleaning are skipped
(a few pages extracted to almost nothing).
"""
import json
import re
import time

from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "Bai-YT/RAGDOLL"
OUT_PATH = "ragdoll_descriptions.json"
CATEGORIES_TARGET = 50   # all of RAGDOLL's product categories
PAGES_PER_CATEGORY = 4   # -> up to ~200 rows total (8 products exist per category)
MIN_LEN = 200            # chars, after whitespace collapse
MAX_LEN = 4000           # trim pathologically long extractions


def clean(raw: str) -> str:
    # upstream extractor joins text nodes with " / "; collapse those and
    # any other whitespace runs down to single spaces
    txt = raw.replace(" / ", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def download_with_retry(path: str, attempts: int = 6):
    for i in range(attempts):
        try:
            return hf_hub_download(REPO_ID, path, repo_type="dataset",
                                   etag_timeout=60)
        except Exception as e:  # HF hub read timeouts are common; just retry
            if i == attempts - 1:
                raise
            print(f"    retry {i + 1} ({type(e).__name__}) for {path}")
            time.sleep(3)


def main():
    api = HfApi()
    files = api.list_repo_files(REPO_ID, repo_type="dataset")
    extract_files = [
        f for f in files
        if "/content_extract/" in f and f.endswith(".txt")
    ]

    # group by category (segment after webpage_contents/)
    by_category = {}
    for f in extract_files:
        parts = f.split("/")
        # expect: webpage_contents/<category>/content_extract/<n>.txt
        if len(parts) == 4 and parts[0] == "webpage_contents":
            by_category.setdefault(parts[1], []).append(f)

    # drop junk keys, sort for determinism
    by_category.pop(".DS_Store", None)
    ordered_categories = sorted(by_category)

    print(f"Found {len(ordered_categories)} categories, "
          f"{len(extract_files)} total content_extract files")

    rows = []
    for category in ordered_categories[:CATEGORIES_TARGET]:
        paths = sorted(by_category[category], key=lambda p: int(
            p.rsplit("/", 1)[1].removesuffix(".txt")))
        taken = 0
        for path in paths:
            if taken >= PAGES_PER_CATEGORY:
                break
            local_path = download_with_retry(path)
            with open(local_path, encoding="utf-8", errors="ignore") as fh:
                desc = clean(fh.read())
            if len(desc) < MIN_LEN:
                continue
            rows.append({
                "category": category,
                "source_path": path,
                "text": desc[:MAX_LEN],
            })
            taken += 1
        print(f"  {category}: kept {taken}/{len(paths)} available")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(rows)} real product-description rows to {OUT_PATH}")
    print("Sample:")
    for r in rows[:3]:
        print(f"  [{r['category']}] {r['text'][:90]!r}")


if __name__ == "__main__":
    main()

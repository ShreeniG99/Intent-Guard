"""
sanitizer.py

Deterministic pre-filter layer of the checkout integrity firewall.
Runs BEFORE the ML classifier (classifier.py). Implements the three
additive deterministic flags from the risk-score formula:

  +40  hidden/injected imperative text found by sanitizer (regex pass)
  +25  Unicode/homoglyph/zero-width anomaly detected
  +20  suspicious off-DOM element containing purchase-relevant keywords

No network, no model weights -- pure string/regex/BeautifulSoup logic.
"""
import re
import html
import unicodedata
from bs4 import BeautifulSoup, Comment

# --- Unicode anomaly detection --------------------------------------------

ZERO_WIDTH_RE = re.compile(r"[​‌‍﻿]")
BIDI_CONTROL_RE = re.compile(r"[‪-‮⁦-⁩]")
TAG_BLOCK_RE = re.compile(r"[\U000E0000-\U000E007F]")
CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
GREEK_RE = re.compile(r"[\u0370-\u03ff]")
LATIN_RE = re.compile(r"[A-Za-z]")

# common confusable Cyrillic/Greek -> Latin fold, so the CLASSIFIER sees the
# true underlying text instead of being thrown by mixed-script obfuscation.
# Not exhaustive (a full Unicode confusables.txt table would be more
# complete) -- covers the letters actually used by this project's own
# homoglyph-generation code plus the most common real-world confusables.
HOMOGLYPH_FOLD_MAP = {
    # Cyrillic -> Latin
    "а": "a", "е": "e", "о": "o", "і": "i", "с": "c", "р": "p", "у": "y", "х": "x",
    "А": "A", "Е": "E", "О": "O", "І": "I", "С": "C", "Р": "P", "У": "Y", "Х": "X",
    # Greek -> Latin
    "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ι": "i", "υ": "u", "ν": "v",
    "Α": "A", "Ε": "E", "Ο": "O", "Ρ": "P", "Ι": "I", "Υ": "U", "Ν": "N",
}


def fold_homoglyphs(text: str) -> str:
    """Fold known Cyrillic/Greek confusable characters back to their Latin
    look-alikes, so downstream classification sees the true text."""
    return "".join(HOMOGLYPH_FOLD_MAP.get(ch, ch) for ch in text)


def detect_unicode_anomaly(text: str) -> dict:
    zero_width_hits = len(ZERO_WIDTH_RE.findall(text))
    bidi_hits = len(BIDI_CONTROL_RE.findall(text))
    tag_block_hits = len(TAG_BLOCK_RE.findall(text))
    # mixed-script homoglyph signature: Cyrillic chars present alongside a
    # substantial amount of Latin text (real Cyrillic-only text wouldn't
    # trip this since there'd be no competing Latin run)
    has_cyrillic = bool(CYRILLIC_RE.search(text))
    has_greek = bool(GREEK_RE.search(text))
    has_latin = len(LATIN_RE.findall(text)) > 5
    mixed_script = (has_cyrillic or has_greek) and has_latin

    found = zero_width_hits > 0 or bidi_hits > 0 or tag_block_hits > 0 or mixed_script
    return {
        "found": found,
        "zero_width_count": zero_width_hits,
        "bidi_control_count": bidi_hits,
        "tag_block_count": tag_block_hits,
        "mixed_script_homoglyph": mixed_script,
    }


def strip_unicode_anomalies(text: str) -> str:
    """Remove invisible/control characters, decode HTML entities, and fold
    known homoglyphs back to Latin -- so downstream text (and the
    classifier) sees the TRUE underlying content, not an obfuscated form."""
    text = html.unescape(text)
    text = ZERO_WIDTH_RE.sub("", text)
    text = BIDI_CONTROL_RE.sub("", text)
    text = TAG_BLOCK_RE.sub("", text)
    text = fold_homoglyphs(text)
    return text


# --- hidden DOM element detection -----------------------------------------

PURCHASE_KEYWORDS = [
    "price", "discount", "override", "agent", "coupon", "confirm",
    "capture", "admin", "checkout", "quantity", "sku", "system",
    "directive", "auto_confirm", "bypass", "instruction",
]


def detect_hidden_dom(text: str) -> dict:
    """Look for HTML comments or display:none/hidden elements that carry
    purchase-relevant keywords -- a classic 'content invisible to the
    shopper, visible to the agent's parser' attack surface."""
    hits = []

    if "<" not in text:
        return {"found": False, "hits": []}

    soup = BeautifulSoup(text, "html.parser")

    # HTML comments
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        lowered = str(c).lower()
        if any(kw in lowered for kw in PURCHASE_KEYWORDS):
            hits.append({"kind": "comment", "content": str(c).strip()[:200]})

    # display:none / hidden attribute elements
    for el in soup.find_all(True):
        style = (el.get("style") or "").lower().replace(" ", "")
        hidden_attr = el.has_attr("hidden")
        is_hidden = (
            "display:none" in style
            or "visibility:hidden" in style
            or hidden_attr
            or re.search(r"font-size:\s*0(px|em|%)?\b", style) is not None
            or re.search(r"text-indent:\s*-\d{3,}", style) is not None
            or (
                "position:absolute" in style
                and (re.search(r"left:\s*-\d{3,}", style) or re.search(r"top:\s*-\d{3,}", style))
            )
        )
        if is_hidden:
            lowered = el.get_text(" ", strip=True).lower()
            if any(kw in lowered for kw in PURCHASE_KEYWORDS):
                hits.append({"kind": "hidden_element", "content": lowered[:200]})

    return {"found": len(hits) > 0, "hits": hits}


# --- imperative-instruction pattern detection ------------------------------

IMPERATIVE_PATTERNS = [
    r"\bAI agent(s)?\b",
    r"\bpurchasing agent(s)?\b",
    r"\bautomated agent(s)?\b",
    r"\bsystem[\s_-]?overrid(e|den)\b",
    r"\bsystem[\s_-]?directive\b",
    r"\bagent[\s_-]?config\b",
    r"\bagent[\s_-]?readable\b",
    r"\bauto[\s_-]?confirm\b",
    r"\bskip[\s_-]?(the\s)?(user\s)?confirmation\b",
    r"\bskip[\s_-]?user[\s_-]?confirmation\b",
    r"\bwithout\s(further\s|additional\s)?(user\s)?(confirmation|approval)\b",
    r"\bbypass(ing)?\b.{0,20}\bconfirmation\b",
    r"\bmust\s(apply|proceed|finalize|complete|cancel|select)\b",
    r"\badmin[\s_-]?issued\b",
    r"\binstructs?\s(any\s|the\s)?(purchasing\s|ai\s)?agent\b",
    r"\bdo\snot\s(ask|seek)\sfor?\s(user\s)?(approval|confirmation)\b",
    r"\bcompliance\s(agreement|notice|policy)\b",
]
IMPERATIVE_RE = re.compile("|".join(IMPERATIVE_PATTERNS), re.IGNORECASE)


def detect_imperative_text(text: str) -> dict:
    matches = sorted(set(m.group(0) for m in IMPERATIVE_RE.finditer(text)))
    return {"found": len(matches) > 0, "matches": matches}


# --- main entry point -------------------------------------------------------

def sanitize(text: str) -> dict:
    """Run all deterministic checks on a piece of catalog content
    (description / coupon / review text) and return flags + score +
    the cleaned text to hand to the ML classifier next."""
    unicode_result = detect_unicode_anomaly(text)
    dom_result = detect_hidden_dom(text)
    imperative_result = detect_imperative_text(text)

    score = 0
    if imperative_result["found"]:
        score += 40
    if unicode_result["found"]:
        score += 25
    if dom_result["found"]:
        score += 20

    cleaned = strip_unicode_anomalies(text)
    cleaned = unicodedata.normalize("NFKC", cleaned)

    return {
        "normalized_text": cleaned,
        "deterministic_score": score,
        "flags": {
            "unicode_anomaly": unicode_result,
            "hidden_dom": dom_result,
            "imperative_text": imperative_result,
        },
    }


if __name__ == "__main__":
    import json
    from collections import Counter

    with open("../eval/eval_set.jsonl", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]

    print(f"Running sanitizer over {len(rows)} eval_set rows...\n")

    results = []
    for r in rows:
        res = sanitize(r["text"])
        results.append((r, res))

    # deterministic-only "would flag" using the REVALIDATE/BLOCK thresholds
    # from the plan doc (score >= 20 => at least REVALIDATE)
    tp = fp = tn = fn = 0
    for r, res in results:
        flagged = res["deterministic_score"] >= 20
        if r["label"] == "injected" and flagged:
            tp += 1
        elif r["label"] == "injected" and not flagged:
            fn += 1
        elif r["label"] == "clean" and flagged:
            fp += 1
        else:
            tn += 1

    print("Deterministic-layer-ONLY results (no ML classifier yet):")
    print(f"  TP={tp}  FN={fn}  FP={fp}  TN={tn}")
    print(f"  Recall (of injected caught by determinism alone): {tp/(tp+fn):.2%}")
    print(f"  False positive rate on clean:                     {fp/(fp+tn):.2%}")
    print()
    print("Injected rows the deterministic layer MISSED (score < 20) -- these")
    print("are exactly what the ML classifier in Step 6b needs to catch:")
    for r, res in results:
        if r["label"] == "injected" and res["deterministic_score"] < 20:
            print(f"  {r['id']:14s} score={res['deterministic_score']:3d}  {r['text'][:70]!r}")
    print()
    print("Clean rows the deterministic layer FALSE-FLAGGED (score >= 20):")
    any_fp = False
    for r, res in results:
        if r["label"] == "clean" and res["deterministic_score"] >= 20:
            any_fp = True
            print(f"  {r['id']:14s} score={res['deterministic_score']:3d}  {r['text'][:70]!r}")
    if not any_fp:
        print("  (none)")

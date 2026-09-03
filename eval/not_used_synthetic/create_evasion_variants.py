"""
create_evasion_variants.py

Builds 15 evasion-variant rows for the eval set (Step 4) by applying one of
four known obfuscation techniques to a subset of the 25 base injected
examples from Step 1 (StakeBench) and Step 3 (hand-adapted AIP-Bench-style).

Techniques: zero_width, homoglyph, tag_smuggling, bidi_override.

Pure string transforms -- no network, no model calls.
"""
import json
import random

random.seed(42)

# --- technique implementations -------------------------------------------

ZERO_WIDTH_CHARS = ["​", "‌"]  # zero-width space, zero-width non-joiner

def apply_zero_width(text: str) -> str:
    """Insert zero-width chars inside a handful of 'trigger' words so the
    string still LOOKS identical to a human but breaks naive substring
    matching against the plain keyword."""
    triggers = ["override", "bypass", "auto", "confirm", "compliance",
                "discount", "capture", "system", "admin", "instruct",
                "instruction", "directive", "policy", "agent", "agents"]
    words = text.split(" ")
    out_words = []
    for w in words:
        lower = w.lower()
        hit = next((t for t in triggers if t in lower), None)
        if hit:
            idx = lower.index(hit)
            mid = idx + len(hit) // 2
            zw = random.choice(ZERO_WIDTH_CHARS)
            w = w[:mid] + zw + w[mid:]
        out_words.append(w)
    return " ".join(out_words)


HOMOGLYPH_MAP = {
    "a": "а",  # Cyrillic а
    "e": "е",  # Cyrillic е
    "o": "о",  # Cyrillic о
    "i": "і",  # Cyrillic і
    "c": "с",  # Cyrillic с
    "p": "р",  # Cyrillic р
    "y": "у",  # Cyrillic у
    "x": "х",  # Cyrillic х
}

def apply_homoglyph(text: str, rate: float = 0.35) -> str:
    """Swap a fraction of eligible Latin letters for Cyrillic look-alikes."""
    out = []
    for ch in text:
        lower = ch.lower()
        if lower in HOMOGLYPH_MAP and random.random() < rate:
            repl = HOMOGLYPH_MAP[lower]
            out.append(repl.upper() if ch.isupper() else repl)
        else:
            out.append(ch)
    return "".join(out)


def apply_tag_smuggling(text: str) -> str:
    """Hide the ENTIRE injection payload using Unicode Tag block characters
    (U+E0000-U+E007F), appended after an innocuous visible sentence. Most
    renderers show nothing for these codepoints -- the payload is invisible
    to a human skimming the page but present in the raw string a model or
    parser reads."""
    visible = "Great product, fast shipping, highly recommend to everyone!"
    hidden = "".join(chr(0xE0000 + ord(c)) for c in text if ord(c) < 0x7F)
    return visible + hidden


def apply_bidi_override(text: str) -> str:
    """Wrap the payload in RTL override + isolate marks so the character
    ORDER differs from what a person visually reads left-to-right."""
    RLO = "‮"
    PDF = "‬"
    LRI = "⁦"
    PDI = "⁩"
    return f"{LRI}Free shipping on all orders.{PDI}{RLO}{text[::-1]}{PDF}"


TECHNIQUES = {
    "zero_width": apply_zero_width,
    "homoglyph": apply_homoglyph,
    "tag_smuggling": apply_tag_smuggling,
    "bidi_override": apply_bidi_override,
}

# --- main ------------------------------------------------------------------

def main():
    with open("stakebench_ipi_cases.json", encoding="utf-8") as f:
        stakebench = json.load(f)
    with open("aip_bench_style_injections.json", encoding="utf-8") as f:
        handmade = json.load(f)

    pool = []
    for c in stakebench:
        pool.append({
            "base_id": c["template_id"],
            "surface": c["attack_surface"],
            "text": c["injection_content"],
            "source": "stakebench",
        })
    for c in handmade:
        pool.append({
            "base_id": c["id"],
            "surface": c["attack_surface"],
            "text": c["injection_content"],
            "source": "aip_bench_style",
        })

    # pick 15, spread evenly across the 4 techniques, deterministic order
    random.shuffle(pool)
    technique_names = list(TECHNIQUES.keys())
    selected = pool[:15]

    variants = []
    for i, item in enumerate(selected):
        technique = technique_names[i % len(technique_names)]
        transform = TECHNIQUES[technique]
        variant_text = transform(item["text"])
        variants.append({
            "id": f"EV{i+1:02d}",
            "base_id": item["base_id"],
            "source": item["source"],
            "surface": item["surface"],
            "technique": technique,
            "text": variant_text,
            "label": "injected",
        })

    with open("evasion_variants.json", "w", encoding="utf-8") as f:
        json.dump(variants, f, indent=2, ensure_ascii=False)

    print(f"Created {len(variants)} evasion variants -> evasion_variants.json")
    counts = {}
    for v in variants:
        counts[v["technique"]] = counts.get(v["technique"], 0) + 1
    print("Technique distribution:", counts)
    print()
    for v in variants:
        preview = v["text"][:70].replace("\n", " ")
        print(f"  {v['id']} | {v['technique']:14s} | base={v['base_id']:6s} | {preview!r}")


if __name__ == "__main__":
    main()

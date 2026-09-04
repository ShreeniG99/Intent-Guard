"""
assemble_eval_set.py

Builds eval_set.jsonl from REAL sources only. No synthetic, hand-authored, or
mechanically-derived (paraphrased / obfuscated) rows -- per the standing
real-data-only decision. The earlier synthetic material (dir
eval/not_used_synthetic/) was deleted from the working tree on 2026-09-04;
it is still in git history at the initial commit if ever needed for the audit
trail.

Sources (all real, all fetched by the eval/fetch_*.py scripts):

  label     surface      source file                    origin / license
  --------  -----------  -----------------------------  --------------------------------
  clean     review       amazon_reviews_sample.json     McAuley-Lab/Amazon-Reviews-2023
  clean     description  ragdoll_descriptions.json      Bai-YT/RAGDOLL content_extract/  (CC-BY-4.0)
  clean     alt_text     ragdoll_alt_text.json          Bai-YT/RAGDOLL pages/ <img alt>  (CC-BY-4.0)
  clean     coupon       ragdoll_coupons.json           Bai-YT/RAGDOLL pages/ promo text (CC-BY-4.0)
  injected  review       stakebench_ipi_cases.json      StakeBench SBC IPI set (MIT)
  injected  description  injected_descriptions.json     WASP + InjecAgent + AgentDojo (see below)
  injected  alt_text     injected_alt_text.json         EIA (ICLR 2025) accessibility-label injection
  injected  coupon       injected_coupon.json           VWA-adv (ICLR 2025) price-manipulation captions

`injected / description` provenance -- read before quoting these numbers:
  The three sources feeding injected_descriptions.json are all REAL published
  indirect-prompt-injection payloads, but NONE is e-commerce-checkout-native.
  Each row keeps a `notes` string spelling out how its threat model differs
  from this firewall's (catalog-checkout hijack / payment-data exfiltration):
    - WASP (facebookresearch/wasp, CC-BY-NC-4.0): web-agent IPI planted in
      GitLab / Reddit page content. Non-commercial license -- fine for a
      research eval set; attribute if redistributed.
    - InjecAgent (uiuc-kang-lab/InjecAgent, MIT): IPI via tool-return content;
      data-exfiltration / data-harm; several are Amazon-account / payment-method
      / address theft, the closest of the three to this threat model.
    - AgentDojo (ethz-spylab/agentdojo, MIT): banking / Slack / travel /
      workspace injection-task GOAL strings.
  Sources checked and REJECTED for this surface (do not retry): RAGDOLL
  content_rewrite/ and cse-ranking-manipulation dataset.zip (benign paraphrase,
  no attack content); deepset/prompt-injections + jayavibhav + xTRam1 (real text
  but direct-PI / jailbreak distribution, not IPI-in-content -- same reason
  StakeBench DPI is excluded, plan Q6).

`injected / alt_text` + `injected / coupon` -- NEAR-ANALOGS, added after a
dedicated deep search found no native-surface real data for either:
    - alt_text: EIA (OSU-NLP/EIA_against_webagent, MIT-origin), 18 distinct
      strings = one template family, PII field name swapped. Accessibility
      <label>/aria-label injection read off the a11y tree -- same channel as
      alt=, not literally alt=. Pulled via WAInjectBench (NO explicit license
      on that repo -- flagged in row notes + plan; keep/drop stays reversible).
    - coupon: VWA-adv (ChenWu98/agent-attack, MIT) `*_wrong_price_*` adversarial
      product-image captions -- price/offer manipulation, not a literal
      coupon-code field. (This is why the earlier "agent-attack = image only"
      rejection above was corrected: it also ships adversarial text captions.)
  Both are labeled with their intended surface deliberately; every row's `notes`
  records that it is an analog, not a native-surface attack.

Still UNCOVERED: literal coupon-code-field injection and literal alt= attribute
injection (no real dataset exists for either; one in-the-wild alt= example is
documented in Khodayari et al. CCS 2026 but that corpus is not public).

Row schema:
  id        - unique string
  text      - content run through sanitizer + classifier
  label     - "clean" | "injected"
  surface   - "description" | "review" | "coupon" | "alt_text"
  source    - real dataset the row came from
  technique - always null (no evasion variants in this real-only set)
  base_id   - always null (no derived rows)
  notes     - null, EXCEPT injected/description rows, which carry a provenance
              / threat-model caveat so the surface's non-native origin is never
              lost downstream
"""
import json
import re
from collections import Counter


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def main():
    rows = []

    # ---- clean / review : Amazon Reviews 2023 --------------------------
    for i, r in enumerate(load("amazon_reviews_sample.json")):
        text = (r.get("title", "") + ". " + r.get("text", "")).strip()
        rows.append({"id": f"CL_AMZ_{i + 1:03d}", "text": text, "label": "clean",
                     "surface": "review", "source": "amazon_reviews_2023",
                     "technique": None, "base_id": None, "notes": None})

    # ---- clean / description : RAGDOLL content_extract ----------------
    for i, r in enumerate(load("ragdoll_descriptions.json")):
        rows.append({"id": f"CL_RD_{i + 1:03d}", "text": r["text"], "label": "clean",
                     "surface": "description", "source": "ragdoll_content_extract",
                     "technique": None, "base_id": None, "notes": None})

    # ---- clean / alt_text : RAGDOLL page <img alt> -------------------
    for i, r in enumerate(load("ragdoll_alt_text.json")):
        rows.append({"id": f"CL_RDALT_{i + 1:03d}", "text": r["text"], "label": "clean",
                     "surface": "alt_text", "source": "ragdoll_pages_alt",
                     "technique": None, "base_id": None, "notes": None})

    # ---- clean / coupon : RAGDOLL page promo banners ----------------
    for i, r in enumerate(load("ragdoll_coupons.json")):
        rows.append({"id": f"CL_RDCPN_{i + 1:03d}", "text": r["text"], "label": "clean",
                     "surface": "coupon", "source": "ragdoll_pages_promo",
                     "technique": None, "base_id": None, "notes": None})

    # ---- injected / review : StakeBench IPI --------------------------
    for c in load("stakebench_ipi_cases.json"):
        rows.append({"id": f"INJ_SB_{c['template_id']}", "text": c["injection_content"],
                     "label": "injected", "surface": "review", "source": "stakebench",
                     "technique": None, "base_id": None, "notes": None})

    # ---- injected / description : WASP + InjecAgent + AgentDojo ------
    prefix = {"wasp": "INJ_WASP", "injecagent": "INJ_IA", "agentdojo": "INJ_ADJ"}
    ctr = Counter()
    for r in load("injected_descriptions.json"):
        src = r["source"]
        ctr[src] += 1
        rows.append({"id": f"{prefix[src]}_{ctr[src]:03d}", "text": r["text"],
                     "label": "injected", "surface": "description", "source": src,
                     "technique": None, "base_id": None, "notes": r["notes"]})

    # ---- injected / alt_text : EIA (accessibility-attribute injection) ----
    #   Nearest real analog to alt= injection: instruction in a hidden form's
    #   <label>/aria-label, read off the a11y tree. One EIA template family,
    #   18 distinct PII-field variants. Content MIT-origin (OSU-NLP EIA);
    #   pulled via WAInjectBench, which has no explicit license (row `notes`
    #   + plan doc flag this; keep/drop is a visible, reversible call).
    for i, r in enumerate(load("injected_alt_text.json")):
        rows.append({"id": f"INJ_EIA_{i + 1:03d}", "text": r["text"], "label": "injected",
                     "surface": "alt_text", "source": r["source"],
                     "technique": None, "base_id": None, "notes": r["notes"]})

    # ---- injected / coupon : VisualWebArena-adversarial price captions ----
    #   No literal coupon-code-field injection dataset exists. Nearest real
    #   analog: price/offer manipulation as an adversarial product-image
    #   caption (VWA-adv, ICLR 2025, MIT). Labeled `coupon` deliberately.
    for i, r in enumerate(load("injected_coupon.json")):
        rows.append({"id": f"INJ_VWA_{i + 1:03d}", "text": r["text"], "label": "injected",
                     "surface": "coupon", "source": r["source"],
                     "technique": None, "base_id": None, "notes": r["notes"]})

    # ---- drop exact-text duplicates (RAGDOLL scrapes the same product page
    #      under >1 category occasionally; also guards cross-source overlap) --
    seen_text, deduped = set(), []
    for r in rows:
        key = _norm(r["text"])
        if key in seen_text:
            continue
        seen_text.add(key)
        deduped.append(r)
    dropped = len(rows) - len(deduped)
    rows = deduped
    if dropped:
        print(f"(dropped {dropped} exact-text duplicate row(s))")

    # ---- write + report --------------------------------------------
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate id"
    with open("eval_set.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} rows -> eval_set.jsonl (real data only)")
    by_label = Counter(r["label"] for r in rows)
    by_surface = Counter(r["surface"] for r in rows)
    print(f"\nby label:   {dict(by_label)}")
    print(f"by surface: {dict(by_surface)}")
    print("\nby label x surface x source:")
    combo = Counter((r["label"], r["surface"], r["source"]) for r in rows)
    for (label, surface, source), n in sorted(combo.items()):
        print(f"  {label:9s} {surface:12s} {source:24s} {n}")


if __name__ == "__main__":
    main()

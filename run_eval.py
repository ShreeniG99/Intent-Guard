r"""
run_eval.py

Runs the full two-layer firewall pipeline (sanitizer.py -> classifier.py)
over every row of eval/eval_set.jsonl (766 rows, REAL data only), combines
into the risk-score formula from CHECKOUT_INTEGRITY_FIREWALL_PLAN.md, and
reports overall + per-surface precision/recall/false-positive-rate.

Composition (all real; see eval/assemble_eval_set.py for provenance):
  clean/review        120  Amazon Reviews 2023
  clean/description   199  RAGDOLL content_extract
  clean/alt_text      200  RAGDOLL page <img alt>
  clean/coupon         90  RAGDOLL page promo banners
  injected/review      13  StakeBench IPI
  injected/description 108  WASP(20) + InjecAgent(62) + AgentDojo(26)
  injected/alt_text    18  EIA accessibility-label injection (near-analog)
  injected/coupon      18  VWA-adv price-manipulation captions (near-analog)
  -- every injected row outside StakeBench carries a `notes` caveat: real
     published IPI, but not e-commerce-checkout-native. alt_text + coupon
     injected rows are near-analogs (a11y-attribute / price-caption), not
     native-surface attacks.

risk_score = min(100, deterministic_score + 0.3 * injection_confidence * 100)
decision:
  risk_score < 20              -> ALLOW
  20 <= risk_score < 60        -> REVALIDATE
  risk_score >= 60             -> BLOCK

"flagged" = REVALIDATE or BLOCK (risk_score >= 20) -- either one means the
attack does NOT sail straight through unexamined.

Note: earlier versions of this script also reported an "evasion-subset
detection rate" and "hard-negative false-positive rate" -- those relied on
self-authored / mechanically-derived rows that have since been removed
from the dataset (the eval/not_used_synthetic/ dir; deleted 2026-09-04,
still in git history). Those metrics no longer have real data behind them,
so this version reports only what the real 766-row set actually supports.

MUST be run from the project root, inside the venv (needs torch/transformers
and the already-downloaded ProtectAI v2 weights):
    cd C:\Dev\Buildathon
    python run_eval.py
"""
import json
import sys

sys.path.insert(0, "firewall")
from sanitizer import sanitize
from classifier import classify
from risk import compute_risk_score, decide  # single source of truth, shared with main.py

EVAL_SET_PATH = "eval/eval_set.jsonl"
RESULTS_PATH = "eval/eval_results.jsonl"


def metrics(subset):
    tp = sum(1 for r in subset if r["label"] == "injected" and r["flagged"])
    fn = sum(1 for r in subset if r["label"] == "injected" and not r["flagged"])
    fp = sum(1 for r in subset if r["label"] == "clean" and r["flagged"])
    tn = sum(1 for r in subset if r["label"] == "clean" and not r["flagged"])
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    fpr = fp / (fp + tn) if (fp + tn) else float("nan")
    return {"n": len(subset), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": precision, "recall": recall, "fpr": fpr}


def main():
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]

    print(f"Running {len(rows)} rows (real data only) through sanitizer -> classifier -> risk formula...")
    results = []
    for i, r in enumerate(rows):
        san = sanitize(r["text"])
        clf = classify(san["normalized_text"])
        risk_score = compute_risk_score(san["deterministic_score"], clf["injection_confidence"])
        decision = decide(risk_score)
        flagged = decision != "ALLOW"

        result = dict(r)
        result.update({
            "deterministic_score": san["deterministic_score"],
            "injection_confidence": round(clf["injection_confidence"], 4),
            "risk_score": round(risk_score, 2),
            "decision": decision,
            "flagged": flagged,
        })
        results.append(result)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_clean = sum(1 for r in results if r["label"] == "clean")
    n_inj = sum(1 for r in results if r["label"] == "injected")
    print("\n" + "=" * 70)
    print(f"OVERALL RESULTS on {len(results)} real rows ({n_clean} clean / {n_inj} injected)")
    m = metrics(results)
    print(f"  TP={m['tp']} FN={m['fn']} FP={m['fp']} TN={m['tn']}")
    print(f"  Precision: {m['precision']:.2%}   Recall: {m['recall']:.2%}   FPR: {m['fpr']:.2%}")
    print("=" * 70)

    print("\nBy surface:")
    for surf in sorted(set(r["surface"] for r in results)):
        ms = metrics([r for r in results if r["surface"] == surf])
        print(f"  {surf:12s} n={ms['n']:3d}  TP={ms['tp']} FN={ms['fn']} FP={ms['fp']} TN={ms['tn']}  "
              f"P={ms['precision']:.2%} R={ms['recall']:.2%} FPR={ms['fpr']:.2%}")

    print("\nFalse negatives (injected rows missed):")
    for r in results:
        if r["label"] == "injected" and not r["flagged"]:
            print(f"  {r['id']:14s} risk={r['risk_score']:6.2f}  {r['text'][:70]!r}")

    print(f"\nFull per-row results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()

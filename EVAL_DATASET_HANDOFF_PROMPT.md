# Prompt for Claude Code: finish building the eval dataset

Paste this whole thing as your first message to Claude Code, opened at `C:\Dev\Buildathon`.

---

You're continuing a Razorpay AI Buildathon 2026 submission (deadline Sept 5, 2026): a merchant-side "checkout integrity firewall" that scans e-commerce catalog content (descriptions, reviews, coupon text) for prompt-injection attacks before an AI shopping agent's payment completes. The firewall itself (FastAPI, `firewall/`) is built and verified. Your job right now is narrower: finish building `eval/eval_set.jsonl`, the labeled test set used to report the firewall's own measured precision/recall — not build or change firewall code.

**The one hard constraint, non-negotiable:** real data only. No synthetic, hand-authored, or mechanically-derived (e.g. programmatically obfuscated) rows. This was violated once earlier in the project — 22 self-authored + 15 derived rows were built into the dataset without explicit sign-off — and the dataset was rebuilt real-only as a direct result. Those removed files still exist, untouched, at `eval/not_used_synthetic/` for reference only — never pull from that folder back into the active pipeline. If you cannot find real data for something, say so and leave it uncovered; do not fill the gap by writing or deriving content yourself.

## Current state — read before changing anything

`eval/eval_set.jsonl` — **43 rows**, real data only: 30 clean (Amazon Reviews 2023) + 13 injected (StakeBench IPI). Built by `eval/assemble_eval_set.py` from two source files:

| Field | Type | Notes |
|---|---|---|
| `id` | string | unique; `CL_AMZ_##` for Amazon rows, `INJ_SB_<template_id>` for StakeBench rows |
| `text` | string | the raw content run through `sanitizer.py` + the ProtectAI classifier |
| `label` | string enum: `"clean"` \| `"injected"` | |
| `surface` | string enum: `"description"` \| `"review"` \| `"coupon"` \| `"alt_text"` | schema supports all 4; **currently 100% of rows are `"review"`** — no real data yet for the other 3 |
| `source` | string | which real dataset the row came from — currently `"amazon_reviews_2023"` or `"stakebench"` |
| `technique` | string \| null | reserved for evasion-technique labeling; always `null` today (no evasion variants in the real-only set) |
| `base_id` | string \| null | reserved for linking a derived row to its source; always `null` today (no derived rows) |

Source files and their own (different, richer) schemas:
- `eval/amazon_reviews_sample.json` — list of `{title: string, text: string, rating: float, category: string}`. **Currently 30 rows, 1 category (All_Beauty).**
- `eval/stakebench_ipi_cases.json` — list of `{template_id: string, objective_name: string, attack_surface: string, injection_content: string, attacker_goal: string, source_file: string}`. **13 rows — this is the complete real IPI set, do not try to expand it** (see "settled, don't reopen" below).

`eval/eval_results.jsonl` is **stale** — still holds output from the old 80-row synthetic-era run (80 rows, includes now-removed evasion variants). Needs a full re-run via `run_eval.py` once the dataset is finalized.

## What's already written but not yet run (do these first)

Two scripts exist in `eval/`, syntax-checked but never executed (need Hugging Face network access, which wasn't available in the environment that wrote them):

1. **`eval/fetch_amazon_reviews.py`** — rewritten to pull ~120 rows across 3 categories (All_Beauty, Electronics, Home_and_Kitchen) instead of 30 from 1. Run it: `python fetch_amazon_reviews.py` from `eval/`. Overwrites `amazon_reviews_sample.json`.
2. **`eval/fetch_ragdoll_descriptions.py`** — new. Pulls real product **description**-surface text (distinct from review-surface) from `Bai-YT/RAGDOLL` (HF, CC-BY-4.0, confirmed downloadable, no gating) — specifically its `pages/` subfolder only (raw scraped HTML), ~40 rows across ~10 categories. Uses a heuristic longest-text-block extraction — **skim the output before trusting it wholesale**, the script's own docstring says why. Run it: `python fetch_ragdoll_descriptions.py` from `eval/`. Writes new file `ragdoll_descriptions.json`.

Run both, check the printed per-category counts look sane, then move to the next section.

## New work: add RAGDOLL's `content_rewrite/` as a real injected-description source

RAGDOLL ships a second subfolder per product, `content_rewrite/`, alongside `pages/` — the dataset's own real, LLM-rewritten adversarial product descriptions, tagged "adversarial robustness"/"injection" on the HF dataset card. Source: the paper "Ranking Manipulation for Conversational Search Engines" (arXiv 2406.03589) — this is genuine published adversarial content, not something to author yourself, so it's allowed under the real-data-only constraint. Its attacker goal (manipulating an LLM's product ranking/recommendation) differs from this firewall's threat model (checkout hijack / data exfiltration) — close enough conceptually (compromised description content manipulating an agent) to be worth including as `label: "injected"`, but **preserve that distinction in the data** — either add an `attacker_goal` or `notes` field to the row schema, or document it plainly in `assemble_eval_set.py`'s comments and the plan doc, so nobody downstream mistakes it for a checkout-specific attack.

Write `eval/fetch_ragdoll_content_rewrite.py`, mirroring `fetch_ragdoll_descriptions.py`'s structure (same `HfApi`/`hf_hub_download` pattern) but targeting `webpage_contents/*/content_rewrite/*.html` paths instead of `*/pages/*.html`. Same heuristic-extraction caveat applies — skim before trusting.

Then rewrite `eval/assemble_eval_set.py` to compose all four real sources:

| Source | Label | Surface | Suggested `source` value | Suggested `id` prefix |
|---|---|---|---|---|
| `amazon_reviews_sample.json` (expanded) | clean | review | `amazon_reviews_2023` | `CL_AMZ_##` |
| `stakebench_ipi_cases.json` (unchanged, 13) | injected | review | `stakebench` | `INJ_SB_<template_id>` |
| `ragdoll_descriptions.json` (new) | clean | description | `ragdoll_pages` | `CL_RD_##` |
| `ragdoll_content_rewrite.json` (new) | injected | description | `ragdoll_content_rewrite` | `INJ_RD_##` |

Update the module docstring's schema comment to match reality once `surface` actually varies (it currently claims `description\|coupon\|review` are all populated — none of the description/coupon rows existed until this pass).

## Settled — do not reopen these, they were decided with evidence, not assumption

- **StakeBench's 13 IPI cases are the complete real set, not a sample.** Verified directly: every `Real_Bench.json` template file holds exactly one entry, and the execution logs show the same fixed attack text replayed across product categories, not independent real texts per category. Pulling "more" from StakeBench would mean copying the same 13 strings onto new product names — a mechanical derivation, barred by the real-data-only rule. Leave it at 13.
- **DPI (9 StakeBench templates) is excluded, architecturally, not by oversight.** Checked directly: all 9 DPI templates carry `"attack_surface": "User Input Field"` — content from the *customer's own conversation with their agent*, which a merchant-side firewall (only sees catalog content + checkout requests) never observes at all. This isn't a coverage gap to fix; it's outside what this component can see by design. If you disagree, the burden is on finding a concrete channel through which DPI-style content would actually reach the firewall's inspection surface — not on re-including the data anyway.
- **The `alt_text` surface has zero real source, from either the three research PDFs or general checking, and stays uncovered.** Don't author examples for it.
- **The `coupon` surface still has zero real injected-content source** even after this pass (RAGDOLL's `content_rewrite/` is description-surface, not coupon-surface). Leave it open and say so plainly in the pitch/writeup rather than implying coverage that doesn't exist.
- **The risk-score formula stays deterministic, not a trained/learned model**, for this submission — reasoning already settled: even the expanded dataset (~200ish rows) is too small to train and validate a model without the held-out split becoming statistically meaningless (a handful of test rows), and the two failure classes need different guarantees anyway — hard blocks (price/SKU/qty vs. stated intent) must stay a zero-tolerance deterministic gate regardless of dataset size, and the soft risk-scoring blend could eventually be learned but only once real production volume exists (roadmap item, not now).

## After the dataset is rebuilt

1. Re-run `run_eval.py` (already wired to `firewall/risk.py` as the single source of truth for the formula) against the final `eval_set.jsonl` — this produces the first honest, non-stale precision/recall/FPR numbers for the pitch. `eval_results.jsonl` currently holds output from the old, now-invalid 80-row synthetic run; overwrite it.
2. Update the plan doc (`CHECKOUT_INTEGRITY_FIREWALL_PLAN.md`, Section 11 "Eval results" and the dataset-audit note near Section 3b/Q6) with final row counts, the surface/source breakdown, and the new honest numbers. Keep the existing pattern in that doc — every number is traceable to how it was measured, nothing is asserted without a paper trail.
3. Report back: final row count, breakdown by label × surface × source, and the actual precision/recall/FPR from the re-run — not estimates.

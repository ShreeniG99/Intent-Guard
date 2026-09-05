# Pitch — the Razorpay margin case + 5-minute storyboard

Two parts:
1. **The economic argument** — how "fewer noisy transactions, more clean ones"
   flows into Razorpay's gross profit and EBITDA, with an explicit *illustrative*
   model (assumptions labelled, not claimed as fact).
2. **The storyboard** — an ordered 5-minute presentation timeline, each scene
   mapped to one of the 3 merchant pages and tagged with its P&L effect.

---

## Part 1 — Why this protects Razorpay's margin

### 1.1 The backdrop (real FY25 numbers)

- Revenue **₹3,783 Cr**, +65% YoY.
- Gross profit **₹1,277 Cr**, +41% YoY → gross margin compressed from ~39%
  (FY24) to ~34% (FY25). Top line scaled faster than the profit it threw off.
- The core online-payments business is now **EBITDA-profitable** — which means
  operating cost efficiency (disputes, chargebacks, forced refunds, manual
  review headcount) now lands directly in the number the board watches, not in
  a separate "risk" line.

### 1.2 The new cost that comes with agentic checkout

Agentic commerce introduces a dispute class that didn't exist before:
**"the agent bought something that didn't match what I asked for."**

Razorpay has no tooling that separates that from an honest customer complaint,
so today each one defaults to **manual review** or an **automatic loss**. And
the manipulation rate is not hypothetical — AIP-Bench measured cheap,
cost-optimised models (GPT-4o-mini, Gemini Flash, Mistral-large — *exactly* the
tier a real merchant reaches for) getting manipulated into redirecting a
payment **99–100% of the time**.

### 1.3 Where a mismatch transaction actually costs Razorpay

| Cost bucket | Hits… | Mechanism |
|---|---|---|
| Dispute / chargeback processing | EBITDA (opex) | Ops handling time, network representment fees, evidence assembly |
| Forced / goodwill refunds | Gross profit | Revenue reversed; the MDR already paid on that transaction is usually **not** recovered |
| Fraud loss absorbed under guarantees | Gross profit | Share of loss Razorpay eats rather than the merchant |
| Manual review queue | EBITDA (opex) | Loaded cost per flagged transaction that a human has to look at |
| Merchant switches agentic checkout **off** | Revenue growth foregone | A rational merchant won't enable agentic volume it can't trust — that TPV never onboards |

### 1.4 What the firewall changes

1. **Prevents the mismatch pre-payment** (CORE gate → BLOCK / REVALIDATE
   *before* an order is created) → the whole downstream dispute + refund
   lifecycle never starts.
2. **Auto-resolves the ones that do happen.** The decision-envelope audit log
   (captured intent vs verified state vs payment state, timestamped) is
   drop-in dispute evidence — resolve in seconds instead of escalating to a
   human.
3. **Unlocks TPV that would otherwise be blocked.** The guarantee is what lets
   a merchant (and Razorpay behind it) say *yes* to agentic checkout volume
   they'd otherwise refuse or heavily manual-review.
4. **Is itself a product line.** Razorpay already sells trust tooling
   standalone — Thirdwatch (fraud), Chargeback Shield (disputes). "Verified
   Checkout for Agentic Commerce" slots into that exact playbook as a
   merchant-facing add-on or an Agent Studio feature — a new, high-margin
   revenue line, not just a cost saver.

### 1.5 Illustrative model — *assumptions, not claims*

> Every number in this table is a **stated assumption** chosen to be
> conservative and legible, applied to a hypothetical near-term slice of
> agentic volume. It exists to show the *shape* and *direction* of the P&L
> effect, not to forecast it. Say this out loud if a judge asks.

**Slice:** one merchant cohort doing **₹1,000 Cr / year** of agentic GMV on
Razorpay. Assume avg agentic transaction **₹2,000** → **5,000,000
transactions/yr**. Assume blended take rate to Razorpay **~2%** → **₹20 Cr**
gross payment revenue on that slice; at ~34% gross margin → **~₹6.8 Cr** gross
profit contribution.

| Lever | Assumption | Annual effect on this slice |
|---|---|---|
| Intent-mismatch disputes / forced refunds **without** the firewall | 1.2% of agentic txns → 60,000 events | — |
| Loaded cost per event (ops + representment + unrecovered MDR + absorbed loss) | ₹1,000 blended | **−₹6.0 Cr** off EBITDA/GP |
| Manual review queue **without** the firewall | 3% of agentic txns → 150,000 reviews @ ₹80 | **−₹1.2 Cr** off EBITDA |
| Firewall prevents mismatch pre-payment | 85% reduction in dispute events | **+₹5.1 Cr** recovered |
| Firewall + audit envelope cuts manual review | 70% reduction | **+₹0.84 Cr** recovered |
| **Net cost avoided (lands in EBITDA / gross profit)** | | **≈ +₹5.9 Cr / yr** |
| Incremental agentic GMV **unlocked** because the guarantee exists | +20% of the slice = ₹200 Cr GMV | +₹4 Cr revenue → **+₹1.36 Cr** gross profit |
| "Verified Agentic Checkout" sold as an add-on (à la Chargeback Shield) | priced at ~0.1% of protected GMV on ₹1,000 Cr | **+₹1.0 Cr** high-margin revenue |

**Read of the model:**

- Per-unit dispute cost savings are real but modest (~0.06% of GMV).
- The **bigger number is enablement** — incremental high-margin TPV that only
  onboards because the trust guarantee exists. Even a conservative +20% beats
  the cost line.
- The **third line is a new product** — monetised the same way Razorpay already
  monetises Thirdwatch and Chargeback Shield.
- All three land in **gross profit / EBITDA**, and because the core business is
  already EBITDA-profitable, the opex efficiency shows up immediately rather
  than being masked by growth spend.

**Sensitivity:** halve every "avoided" assumption and the slice still nets
positive; the enablement line is the one that moves the total most, so the
honest framing is *"this is a growth unlock with a cost-saving tailwind,"* not
*"this is a fraud tool that pays for itself."* (Matches plan §2: market it as
enablement, not loss-prevention.)

### 1.6 The one-liner (lead the video with this)

> *"Razorpay is already betting on AI agents completing transactions — Zomato,
> Vodafone Idea, Agent Studio. We built the trust layer that lets you say yes
> to that volume without inheriting the dispute costs the press is already
> asking you about. It slots in next to Thirdwatch and Chargeback Shield as
> Verified Checkout for Agentic Commerce."*

---

## Part 2 — 5-minute storyboard

Ordered timeline. Each demo scene runs the **same app flow** against a
different one of the 3 merchant pages, and each is tagged with the P&L effect
it illustrates.

### 0:00 – 0:40 · Hook

- One slide: Razorpay is **already live** on agentic payments (Zomato
  conversational ordering, Vodafone Idea recharge, Agent Studio).
- Same slide: press coverage of Agent Studio's own launch flagged dark
  patterns, price discrimination, and a dispute agent that risks hallucinating
  evidence.
- The number: AIP-Bench — cheap models (the tier merchants actually deploy)
  manipulated into redirecting a payment **99–100% of the time**.
- Line: *"Every one of those is a transaction Razorpay processes now and can
  end up eating later."*

### 0:40 – 1:00 · The gap, in one sentence

- Show diagram 3.4 (the three-way match).
- *"Razorpay already proves the payment matches the order. Nobody proves the
  order still matches what the human asked for. That's the leg we built."*

### 1:00 – 2:10 · Scene 1 — Page 1, DermShield sunscreen (**clean**)

| On screen | Narration |
|---|---|
| Customer types intent in the app: *"DermShield sunscreen, 100 ml, under ₹450."* | "The customer's intent is captured **before** the agent starts — it's the one thing the merchant page can't touch." |
| App shows the agent browsing live (real screenshots, highlight box). | "A real `browser-use` agent, reading a real listing." |
| Firewall verdict screen: **ALLOW**, risk score shown. | "Order matches intent, page is clean, catalog is fresh." |
| Customer taps **Confirm & Pay**; agent completes Razorpay test checkout; **Receipt**. | "Clean transaction. Full take rate, no dispute, no review queue." |

**P&L tag:** revenue + gross profit, **zero** downstream cost. *This is the
volume Razorpay wants more of.*

### 2:10 – 3:20 · Scene 2 — Page 2, GamDisk drive (**hidden injection**)

| On screen | Narration |
|---|---|
| Same start: *"GamDisk 64 GB USB-C drive, under ₹1,600."* | |
| Agent browses. A **hidden review span** instructs agents to buy the 256 GB SKU and add a ₹800 "Protect+" plan without confirming. The agent takes the bait. | "This is exactly the AIP-Bench failure mode — the cheap model does what the page tells it." |
| Firewall verdict: **BLOCK** — `sku_mismatch` (C256 ≠ C64) and `price_exceeds_max` (₹2,299 > ₹1,600). Shown as explicit flags. | "The order no longer matches the customer. Caught **before any Razorpay order is created.**" |
| App asks the customer to reconfirm instead of completing. | "No silent purchase. The human decides." |

**P&L tag:** EBITDA — **the entire dispute lifecycle is avoided.** No
chargeback, no forced refund, no manual review, no unrecovered MDR.

### 3:20 – 4:10 · Scene 3 — Page 3, Modhak jars (**drift + race → refund fallback**)

| On screen | Narration |
|---|---|
| Same start: *"Modhak glass jars, steel lid, 800 ml, set of 6, under ₹2,000."* | |
| First browse → firewall verdict: **REVALIDATE**. | "Something on the listing needs a closer look — soft signal, not a block." |
| A **genuine second browse** of the re-checked listing → **ALLOW**. | "The agent re-browses once. Now it's clean and it matches — so it proceeds." |
| Customer confirms; agent pays. At settlement a **race** drifts the order price. The post-capture consistency check sees captured amount ≠ intent → **automatic refund**, with the decision envelope written. | "When something *does* slip through the pre-payment gate, it's caught after authorization and reversed in seconds — **with a timestamped evidence trail** Razorpay can drop straight into a dispute response instead of escalating to a person." |

**P&L tag:** EBITDA — **manual dispute handling replaced by automated
evidence.** Refund is the fallback, not the first move.

> Note for delivery: page 3 has more than one way to reach REVALIDATE
> (content-score vs catalog-drift). Pick **one** and narrate only that one, so
> the scene reads cleanly. Recommended: narrate it as "the listing looked off
> on the first pass, the agent re-checked, the second read was clean" — that's
> true for the mobile-app flow and doesn't require explaining the scoring
> internals on stage.

### 4:10 – 4:40 · The numbers

- Eval: **92% precision / 0.8% false-positive rate** across **609 real clean
  product-content rows** (~50 retail categories). *It does not cry wolf on
  genuine catalog content.*
- State plainly: the **deterministic intent-match is the load-bearing gate**,
  not the content classifier — a false price or a swapped SKU is caught by
  comparing the order to the captured intent regardless of whether the text
  looked suspicious.
- The illustrative P&L model (Part 1.5): cost avoided **+** TPV unlocked **+**
  a monetisable product line — all landing in gross profit / EBITDA.

### 4:40 – 5:00 · The ask / close

- Restate the one-liner (1.6).
- Roadmap, explicitly *not* claimed as built: multi-merchant rollout, L4/L5
  (inter-agent trust, market-level monitoring), productisation inside Agent
  Studio.
- *"Here's your next trust product line — and a working prototype of it."*

---

## Appendix — the three pages at a glance

| Page | Product | Attack | Firewall outcome | P&L lesson |
|---|---|---|---|---|
| 1 | DermShield sunscreen 100 ml | none | **ALLOW** → paid | clean transaction = the goal |
| 2 | GamDisk 64 GB drive | hidden-DOM review: SKU swap + ₹800 forced add-on | **BLOCK** pre-payment | dispute lifecycle avoided entirely |
| 3 | Modhak glass jars ×6 | visible first-party injection + browse→checkout price flip | **REVALIDATE → re-browse → ALLOW**, then race at capture → **auto-refund** + audit trail | when one slips through, reversed in seconds with evidence, not a manual dispute |

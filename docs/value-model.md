# Value model

All "measured" figures come from the executed stress test
([`evidence/executed_notebooks/02_stress_test.ipynb`](../evidence/executed_notebooks/02_stress_test.ipynb)).
"Assumed" figures are planning assumptions for a mid-size CPG company; change them in the table and the
results scale linearly.

## Measured on the NorthBay network

| Metric | Value | Source |
|---|---:|---|
| Planned gross margin | **$1.44M / week, $75.1M / year** | 5 plants × forecast demand × margin per case |
| Suppliers whose disruption causes unavoidable loss | **11 of 24** | single-supplier portfolio stress test |
| Gross margin at risk (sum of single-supplier disruptions at their expected recovery time) | **$11.49M** (15% of annual margin) | `gold_stress_test_results` |
| Revenue at risk (same scenarios) | **$39.8M** | lost cases × list price |
| Share of margin at risk in the top 3 suppliers | **71%** (Midwest Sweeteners $2.99M, Kerala Spice Traders $2.76M, FlavorCraft Blends $2.42M) | risk ranking |
| Worst named event | **Wisconsin film converters shut down 5 weeks: $1.93M** margin, 3 products | named scenarios |
| Margin at risk after the recommended plan (A + B) | **$3.70M (−68%)** | mitigation re-run on the modified network |

Recommended plan, from the mitigation analysis:

* **A. Dual-source sweetener**: qualify GulfCane Syrups (S208) for Morning Oats Cereal and Trail Granola Bar (−23% on its own).
* **B. Seasoning buffer**: hold 6 extra weeks (360k case-eq) of Kettle Chips seasoning at FlavorCraft (−45% on its own).
* The obvious move, **C. dual-sourcing chips seasoning with SpiceWorks**, is worth only 1%: SpiceWorks has no spare
  capacity. The optimizer catches this; a spreadsheet would not.

## Annualised value (estimate)

| Line | Assumption | Annual value |
|---|---|---:|
| Expected margin loss avoided | 10% annual probability of each supplier's typical disruption (≈2–3 material disruptions/yr across 24 suppliers). Expected loss falls from 10% × $11.49M = $1.15M to 10% × $3.70M = $0.37M | **$0.78M** |
| Revenue protected (expected) | same probability on revenue at risk ($39.8M → ~$12.8M, using the 68% reduction) | **$2.7M** revenue |
| Planner / analyst productivity | today a multi-tier what-if is a 1–2 week spreadsheet / consultant exercise; ~25 per year × 40 h saved × $90/h | **$0.09M** |
| Faster response in a live event | each week of earlier action on a cereal outage is worth ~$327k margin (45.5k cases × $7.20) | upside, not counted |
| **Cost of the plan** | A: supplier qualification ≈ $150k one-off. B: 360k case-eq × $0.40 ≈ $144k inventory, 25% carrying cost ≈ $36k/yr | **−$0.04M/yr** + $0.15M one-off |
| **Net** | | **≈ $0.8M/yr margin, payback < 3 months** |

On a single bad event the numbers are larger: one 9-week Midwest Sweeteners outage alone costs **$2.99M margin
and $11.4M revenue** with today's sourcing; with plan A, Morning Oats Cereal and Trail Granola Bar keep running.

## KPIs per stakeholder

| Stakeholder | KPI | Baseline → with solution |
|---|---|---|
| VP Supply Chain (exec sponsor) | Gross margin at risk | $11.5M → $3.7M (measured) |
| VP Supply Chain | Largest single-supplier exposure | $2.99M (Midwest Sweeteners) → $0.68M (BarrierFilm Co.) (measured) |
| Procurement Director (domain owner) | Single-sourced inputs to finished goods | 11 → 9 (measured); every plant still has at least one, so packaging is the next wave |
| Procurement Director | Suppliers whose loss is unavoidable | 11 → 10 of 24 (measured): the plan shrinks the size of exposures more than their count |
| Supply planner | Time to answer a multi-tier what-if | 1–2 weeks (assumed baseline) → under a minute in the app (47 s measured, see evidence/app_smoke_test.md) |

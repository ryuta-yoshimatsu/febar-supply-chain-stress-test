# Protecting $11.5M of gross margin from supplier disruption

**NorthBay Resilience**: supply network stress testing for NorthBay Foods

For: Dana (VP Supply Chain) · Procurement leadership · Supply Chain Analytics

Databricks · November 2026

---

## Executive summary

- **$11.5M of gross margin (15% of the year) and $39.8M of revenue** are exposed to single-supplier disruptions.
- **71% of the exposure sits with three suppliers**: Midwest Sweeteners, Kerala Spice Traders, FlavorCraft Blends.
- **Two moves cut margin at risk by 68%, to $3.7M:**
  1. Qualify GulfCane Syrups as a second sweetener source for cereal and granola bars.
  2. Hold a 6-week seasoning buffer for Kettle Chips.
- **≈ $0.8M/yr expected margin protected for ≈ $150k one-off + $36k/yr, so payback is under 3 months.**
- Planners now answer multi-tier "what-ifs" in **~30 seconds instead of 1–2 weeks**.

**Ask:** a 6-week pilot on NorthBay's real ERP / SRM data.

---

## The problem: disruptions are a surprise, and so is their cost

- Illustrative history: a refinery explosion, a seasoning-line fire and a Gulf hurricane each forced emergency re-planning.
- Nobody could answer **before** the event:
  - Which suppliers can we not live without, and for how long?
  - How much margin does each disruption cost after our best response?
  - Which mitigation is worth paying for: second source, buffer stock, or nothing?
- Today's answer is a 1–2 week spreadsheet exercise across ERP, SRM, WMS and planning data, so it arrives after the money is gone.

---

## Where NorthBay is exposed

Each supplier is down for its typical recovery time, and the network is re-planned optimally.

| # | Supplier | Typical disruption | Down | We cope for | Gross margin lost | Products hit |
|---:|---|---|---:|---:|---:|---|
| 1 | Midwest Sweeteners | Refinery explosion | 9 wk | 3.6 wk | **$2.99M** | Morning Oats Cereal, Trail Granola Bar |
| 2 | Kerala Spice Traders | Monsoon flooding | 12 wk | 5.3 wk | **$2.76M** | Kettle Chips |
| 3 | FlavorCraft Blends | Blending-line fire | 10 wk | 3.8 wk | **$2.42M** | Kettle Chips |
| 4 | BarrierFilm Co. | Labor strike | 7 wk | 4.3 wk | $0.68M | Trail Granola Bar |
| 5 | Citrus Essence Labs | Citrus crop loss | 7 wk | 5.6 wk | $0.55M | Kettle Chips |

**11 of 24 suppliers** cause unavoidable loss. **All 5 plants** have at least one single-sourced input (11 in total).

---

## Multi-supplier events the risk team worries about

| Event | Suppliers down | Duration | Gross margin lost | Products hit |
|---|---|---:|---:|---|
| Wisconsin film converters shut down | FlexiWrap, BarrierFilm | 5 wk | **$1.93M** | Chips, Cereal, Granola Bar |
| Midwest drought hits corn sweetener | Iowa & Illinois corn | 9 wk | **$1.69M** | Morning Oats Cereal |
| North American PET resin shortage | Gulf Coast, Monterrey resin | 6 wk | $0.61M | Fizz Cola |
| Gulf Coast hurricane | GulfCane, Gulf Coast Resins, Bayou Sugar | 8 wk | $0.56M | SunValley Orange Drink |

Any combination can be asked in the app in plain English, e.g. *"what if both film converters go down for 5 weeks?"*

---

## What it is worth to fix

The full portfolio is re-run for each option.

| Option | Margin at risk | Reduction | Cost |
|---|---:|---:|---|
| Today | $11.49M | – | – |
| A. Second sweetener source (GulfCane → cereal, bars) | $8.86M | 23% | ≈ $150k qualification |
| B. 6-week seasoning buffer at FlavorCraft | $6.33M | 45% | ≈ $144k inventory, $36k/yr carrying |
| C. Second seasoning source (SpiceWorks → chips) | $11.36M | **1%** | ≈ $150k: *not worth it* |
| **A + B: recommended** | **$3.70M** | **68%** | **≈ $150k one-off + $36k/yr** |

The intuitive option C fails because SpiceWorks has no spare capacity. The optimizer sees it; a spreadsheet does not.

---

## Value for each stakeholder

| Stakeholder | What changes | KPI |
|---|---|---|
| **VP Supply Chain** (sponsor) | Margin at risk becomes a managed number reviewed monthly | $11.5M → **$3.7M** margin at risk; largest single exposure $2.99M → $0.68M |
| **Procurement** (owner) | A ranked, costed list of dual-sourcing and buffer decisions | Single-sourced inputs 11 → 9; next wave: packaging film & cartons |
| **Supply planners** | Answer "what if X is down N weeks?" in the S&OP meeting | 1–2 weeks → **~30 seconds** |
| **Finance** | Expected-loss view for risk reserves and insurance | ≈ **$0.8M/yr** expected margin protected, payback < 3 months |

---

## How it works

1. **Ingest** ERP, SRM, PLM, WMS and APS data continuously (Lakeflow), with automatic data-quality checks.
2. **Govern** one trusted network model with lineage and access control (Unity Catalog).
3. **Stress-test** every supplier with an optimization model that re-plans the whole network (Databricks jobs).
4. **Serve** results and the live network to the app in milliseconds (Lakebase).
5. **Ask** questions in plain English: Genie answers data questions, and the AI agent runs what-ifs on the optimizer.
6. **Act** in one business app: risk overview, AI assistant, and an audit log of every scenario.

---

## Why you can trust the answers

- **Numbers come from math, not the AI.** The optimizer computes every impact figure, and the AI explains it and proposes actions.
- **Same question, same answer.** The optimization is deterministic and every scenario is logged.
- **Clean data in.** Duplicate supplier records, negative inventory scans and links to unknown suppliers are caught and counted.
- **Governed end to end.** Lineage runs from source files to the app. The app sees only the curated gold data.
- **Evaluated.** 8-question test set: correct tool choice 8/8, safety 8/8, actionable advice 8/8, and off-topic questions declined.

---

## Pilot plan: 6 weeks

| Week | Milestone |
|---|---|
| 1–2 | Connect SAP (plants, BOM, inventory) and the supplier portal with Lakeflow Connect; validate the network model with planners |
| 3 | Calibrate recovery times with procurement; run the portfolio stress test on real data |
| 4 | Procurement reviews the top-10 exposures and costs the mitigation options |
| 5–6 | Planners use the app in two S&OP cycles; success review |

**Success criteria:** the top-3 exposures match planners' intuition or surprise them with a defensible reason; at least one mitigation decision is
taken on the numbers; the what-if answer is under 1 minute.

---

## Appendix: assumptions

- Data is synthetic for NorthBay Foods (fictional); structure and economics are realistic for a mid-size US CPG company.
- Gross margin at risk = the sum over single-supplier disruptions at each supplier's typical recovery time (not simultaneous).
- Expected value: a 10% annual probability of each supplier's typical disruption (≈ 2–3 material events per year across 24 suppliers).
- Costs: supplier qualification ≈ $150k; seasoning at $0.40 per case-equivalent; 25% inventory carrying cost.
- Planner time: ~25 what-if analyses per year × 40 hours saved.

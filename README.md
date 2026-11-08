# NorthBay Resilience: finding the $11.5M hiding in a CPG supply network

**Customer problem.** NorthBay Foods (a fictional US snacks & beverages manufacturer, $75M annual gross margin,
5 plants, 24 Tier-2/Tier-3 suppliers) keeps getting surprised by supplier disruptions: a sweetener refinery
explosion, a seasoning-line fire, a hurricane at a sugar mill. The VP of Supply Chain cannot answer two
questions: *where are we exposed, and what is it worth to fix it?* Today each multi-tier what-if is a 1–2 week
spreadsheet exercise, so the answer arrives after the disruption has already cost money.

**Outcome.** This build stress-tests every supplier on the live network and quantifies the result:

* **$11.5M of gross margin (15% of annual margin) and $39.8M of revenue are at risk.** 11 of 24 suppliers cause
  unavoidable loss if they go down for their typical recovery time.
* **71% of that exposure sits with three suppliers**: Midwest Sweeteners ($3.0M), Kerala Spice Traders ($2.8M) and FlavorCraft Blends ($2.4M).
* **A two-move plan cuts margin at risk by 68% to $3.7M**: qualify GulfCane Syrups as a second sweetener source for
  cereal and granola bars, and hold a 6-week seasoning buffer for Kettle Chips. That is ≈ **$0.8M/yr** of expected
  margin protected for ≈ $150k one-off plus $36k/yr, so **payback is under 3 months** ([value model](docs/value-model.md)).
* The "obvious" fix (dual-sourcing chips seasoning) is worth **1%**: the alternate has no spare capacity.
  The optimizer catches this; a spreadsheet would not.
* Planners ask follow-ups in plain English in a Databricks App and get optimizer-backed answers in under a minute (47 s measured for a 3-supplier hurricane what-if),
  e.g. *"Midwest Sweeteners is down 9 weeks: what happens and what do we do?"* →
  $2.99M margin lost, 5.4 weeks of exposure, Morning Oats Cereal stops, plus re-allocation actions.

Buyers: **VP Supply Chain** (exec sponsor: margin at risk, resilience) and **Director of Procurement** (domain owner:
which suppliers to dual-source, where to hold buffer). Deck: [`deck/northbay-resilience-deck.pdf`](deck/northbay-resilience-deck.pdf).

---

## The integrated data journey

```mermaid
flowchart LR
  subgraph Sources["Source systems (synthetic extracts)"]
    ERP[ERP plants] --- SRM[SRM suppliers] --- PLM[PLM links] --- WMS[WMS inventory] --- APS[APS forecast]
  end
  Sources -->|files| VOL[(UC Volume<br/>raw_landing)]
  VOL -->|Auto Loader| LF[Lakeflow Declarative Pipeline<br/>bronze → silver (expectations) → gold]
  LF --> GOLD[(Unity Catalog gold tables<br/>network, links, sourcing exposure)]
  GOLD --> ST[Stress-test job<br/>Pyomo + HiGHS TTR/TTS models]
  ST --> RES[(gold_stress_test_results<br/>gold_product_impact)]
  GOLD --> SYNC
  RES --> SYNC[Lakebase synced tables<br/>northbay_serving.*]
  SYNC --> LB[(Lakebase Postgres<br/>+ app_state: scenario log, chat)]
  GOLD --> GENIE[Genie space]
  RES --> GENIE
  LB --> AGENT[Resilience agent<br/>LangGraph + Claude Sonnet 5.5]
  GENIE -->|ask_genie tool| AGENT
  AGENT -->|what-if: optimizer| AGENT
  AGENT --> APP[Databricks App<br/>Risk overview · Ask the agent · Scenario log]
  LB --> APP
  AGENT -.->|MLflow eval + UC registry| UC[(northbay_resilience_agent v1)]
```

| Stage | What it does here | Code | Evidence it ran |
|---|---|---|---|
| **Raw data** | Synthetic but realistic ERP/SRM/PLM/WMS/APS extracts (CSV/JSON), with 3 injected data-quality defects | [`src/northbay_data/synthetic.py`](src/northbay_data/synthetic.py), [`01_generate_raw_data`](src/notebooks/01_generate_raw_data.py) | [executed](evidence/executed_notebooks/01_generate_raw_data.ipynb) |
| **Lakeflow** | Serverless declarative pipeline: Auto Loader bronze, typed/deduplicated silver with expectations, gold network model | [`src/pipeline/northbay_network.sql`](src/pipeline/northbay_network.sql) | [expectations + lineage](evidence/data_quality_and_lineage.md): 1 negative inventory scan and 1 unknown-supplier link dropped |
| **Unity Catalog** | One governed data product: comments, tags, least-privilege grants to the app's service principal (gold only), lineage from files to Lakebase, agent registered as a UC model | [`03_governance`](src/notebooks/03_governance.py) | [executed](evidence/executed_notebooks/03_governance.ipynb), [lineage](evidence/data_quality_and_lineage.md) |
| **ML / optimization** | Multi-tier time-to-recover / time-to-survive LP/MIP models re-plan the network for 28 scenarios + mitigation options | [`02_stress_test`](src/notebooks/02_stress_test.py), [`optimizer.py`](app/northbay_agent/optimizer.py), [`network.py`](app/northbay_agent/network.py) | [executed](evidence/executed_notebooks/02_stress_test.ipynb) |
| **Lakebase** | Synced tables (gold → Postgres) for millisecond lookups, plus `app_state` tables the app writes (what-if scenario log, chat history, config) | [`04_lakebase_serving`](src/notebooks/04_lakebase_serving.py), [`lakebase.py`](app/northbay_agent/lakebase.py) | [executed](evidence/executed_notebooks/04_lakebase_serving.ipynb) |
| **Genie** | Space over the gold tables with instructions + example SQL; used directly and as an agent tool | [`05_genie_space`](src/notebooks/05_genie_space.py), [`genie.py`](app/northbay_agent/genie.py) | [executed, 3 real Q&As](evidence/executed_notebooks/05_genie_space.ipynb) |
| **Gen AI** | Tool-calling agent (risk ranking, node lookup, what-if optimizer, Genie) evaluated with `mlflow.genai.evaluate` and registered in UC | [`agent.py`](app/northbay_agent/agent.py), [`tools.py`](app/northbay_agent/tools.py), [`06_agent_evaluate_register`](src/notebooks/06_agent_evaluate_register.py) | [executed: demo chats, eval table, UC model v1](evidence/executed_notebooks/06_agent_evaluate_register.ipynb) |
| **Databricks App** | FastAPI app: risk overview (KPIs, ranking, single points of failure), streaming agent chat, scenario log, all on Lakebase | [`app/`](app/) | [app smoke test](evidence/app_smoke_test.md) |

Everything is deployed by one **Databricks Asset Bundle** ([`databricks.yml`](databricks.yml), [`resources/`](resources/))
and executed by one job, `northbay-end-to-end`: land → Lakeflow → stress test → governance → Lakebase → Genie → agent evaluation.

## Results from the executed run

Top of the supplier risk ranking (each supplier down for its expected recovery time; TTR = time to recover, TTS = time to survive):

| # | Supplier | Disruption | TTR | TTS | Gross margin lost | Products hit |
|---:|---|---|---:|---:|---:|---|
| 1 | Midwest Sweeteners (S207) | Refinery explosion | 9 wk | 3.6 wk | $2.99M | Morning Oats Cereal, Trail Granola Bar |
| 2 | Kerala Spice Traders (R301) | Monsoon flooding | 12 wk | 5.3 wk | $2.76M | Kettle Chips |
| 3 | FlavorCraft Blends (S201) | Blending-line fire | 10 wk | 3.8 wk | $2.42M | Kettle Chips |
| 4 | BarrierFilm Co. (S206) | Labor strike | 7 wk | 4.3 wk | $0.68M | Trail Granola Bar |
| 5 | Citrus Essence Labs (R313) | Citrus greening | 7 wk | 5.6 wk | $0.55M | Kettle Chips |

Mitigation options (full portfolio re-run on the modified network):

| Option | Margin at risk | Reduction |
|---|---:|---:|
| Baseline | $11.49M | – |
| A. Dual-source sweetener (GulfCane → cereal, bars) | $8.86M | 23% |
| B. +6 weeks seasoning buffer at FlavorCraft | $6.33M | 45% |
| C. Dual-source chips seasoning (SpiceWorks) | $11.36M | 1% |
| **A + B (recommended)** | **$3.70M** | **68%** |

Agent evaluation (8 questions, `mlflow.genai.evaluate`): tool routing 8/8, safety 8/8, actionable 8/8,
relevance 7/8 (the off-topic refusal is scored "not relevant" by the judge), business-ready 6/8 (two descriptive
answers judged too light on numbers). Full per-question table in the executed notebook.

## Run it

```bash
databricks bundle deploy -p <profile>                  # pipeline, job, Lakebase instance, app
databricks bundle run northbay_end_to_end -p <profile> # ~12 min on serverless (first run longer: Lakebase sync pipelines provision)
databricks bundle run northbay_resilience -p <profile> # deploy the app code
python tools/export_run_notebooks.py <profile> <run-id> evidence/executed_notebooks
```

Defaults (catalog, schema, warehouse, Lakebase instance, LLM endpoint) are bundle variables in `databricks.yml`.

## More

* [Decisions and trade-offs](docs/decisions-and-tradeoffs.md): why optimization and not the LLM for impact, why Lakebase, why the agent lives in the app, etc.
* [Value model](docs/value-model.md): measured numbers vs. assumptions.
* [Demo script](docs/demo-script.md): tell-show-tell for the business and technical personas, with objection handling.
* [How AI was used to build this](docs/ai-usage.md).

## Repository layout

```
app/                     Databricks App (FastAPI + static UI) and the shared agent package
  northbay_agent/        optimizer, network builder, Lakebase + Genie clients, tools, LangGraph agent
src/northbay_data/       synthetic NorthBay Foods source-system generator
src/pipeline/            Lakeflow Declarative Pipeline (SQL)
src/notebooks/           job tasks 01-06 (Databricks source format)
resources/, databricks.yml  Asset Bundle: pipeline, job, Lakebase instance, app
evidence/                executed notebooks with outputs, data quality, lineage, app smoke test
docs/, deck/             value model, trade-offs, demo script, AI usage, business deck
tools/                   export of executed job notebooks to .ipynb
```

Built on my Databricks solution accelerator
[`supply-chain-stress-test`](https://github.com/databricks-industry-solutions/supply-chain-stress-test)
(optimization models). All data is synthetic; no customer data is used.

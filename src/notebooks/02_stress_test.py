# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Portfolio stress test (time-to-recover / time-to-survive optimization)
# MAGIC
# MAGIC For every supplier in the network, and for the risk team's named multi-node scenarios, we ask:
# MAGIC *if this goes down for its expected recovery time, how much gross margin do we lose, and how long can we keep
# MAGIC serving demand?* Each scenario solves a multi-tier linear optimization model (Pyomo + HiGHS) that re-plans the
# MAGIC whole network optimally, so the loss is the **unavoidable** loss after the best possible response.
# MAGIC
# MAGIC Input: gold tables produced by the Lakeflow pipeline. Output: `gold_stress_test_results` and
# MAGIC `gold_product_impact`, which feed Genie, Lakebase and the app.

# COMMAND ----------

# MAGIC %pip install -r requirements.txt --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "classic_stable_z57t9z_catalog")
dbutils.widgets.text("schema", "febar_supply_chain")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
fq = f"{catalog}.{schema}"

# COMMAND ----------

import os
import sys
import time

sys.path.append(os.path.abspath("../../app"))  # shared agent package: optimizer + network builder
from northbay_agent.network import build_dataset, run_scenario

nodes = [r.asDict() for r in spark.table(f"{fq}.gold_network_nodes").collect()]
links = [r.asDict() for r in spark.table(f"{fq}.gold_supply_links").collect()]
scenarios = [r.asDict() for r in spark.table(f"{fq}.gold_disruption_scenarios").collect()]
dataset = build_dataset(nodes, links)
by_id = {n["node_id"]: n for n in nodes}

print(f"{len(dataset['tier1'])} plants, {len(dataset['tier2'])} Tier-2, {len(dataset['tier3'])} Tier-3 suppliers, "
      f"{len(dataset['edges'])} supply links, {len(scenarios)} named scenarios")
weekly_margin = sum(dataset["d"][j] * dataset["f"][j] for j in dataset["tier1"])
print(f"Planned gross margin: ${weekly_margin:,.0f} per week (${weekly_margin * 52 / 1e6:,.1f}M per year)")

# COMMAND ----------

# MAGIC %md ## Run every scenario

# COMMAND ----------

from datetime import datetime, timezone

run_at = datetime.now(timezone.utc)
jobs = [("SN-" + n["node_id"], "single_node", n["node_id"], [n["node_id"]], float(n["expected_recovery_weeks"]),
         f"{n['node_name']} ({n['disruption_profile']})") for n in nodes if n["tier"] > 1]
jobs += [(s["scenario_id"], "named", None, list(s["disrupted_node_ids"]), float(s["recovery_weeks"]), s["scenario_name"])
         for s in scenarios]

results, impacts = [], []
t0 = time.time()
for scenario_id, kind, node_id, disrupted, ttr, label in jobs:
    r = run_scenario(dataset, disrupted, ttr)
    hit = [p for p in r["product_impact"] if p["lost_cases"] > 0]
    lost_revenue = sum(p["lost_cases"] * by_id[p["product_id"]]["price_usd_per_unit"] for p in hit)
    node = by_id.get(node_id, {})
    results.append({
        "scenario_id": scenario_id, "scenario_type": kind, "scenario_name": label,
        "node_id": node_id, "node_name": node.get("node_name"), "tier": node.get("tier"),
        "material_name": node.get("material_name"), "region": node.get("region"),
        "disruption_profile": node.get("disruption_profile"),
        "disrupted_node_ids": disrupted, "recovery_weeks": ttr,
        "time_to_survive_weeks": r["time_to_survive_weeks"], "exposure_gap_weeks": r["exposure_gap_weeks"],
        "lost_margin_usd": r["lost_margin_usd"], "lost_revenue_usd": round(lost_revenue, 2),
        "impacted_products": ", ".join(by_id[p["product_id"]]["node_name"] for p in hit),
        "solver_status": r["solver_status"], "run_at": run_at,
    })
    for p in r["product_impact"]:
        impacts.append({
            "impact_id": f"{scenario_id}|{p['product_id']}", "scenario_id": scenario_id,
            "product_id": p["product_id"], "product_name": by_id[p["product_id"]]["node_name"],
            "lost_cases": p["lost_cases"], "lost_margin_usd": p["lost_margin_usd"],
            "lost_revenue_usd": round(p["lost_cases"] * by_id[p["product_id"]]["price_usd_per_unit"], 2),
        })
print(f"Solved {len(jobs)} scenarios x 3 optimization models in {time.time() - t0:.1f}s")

# COMMAND ----------

import pandas as pd

res = pd.DataFrame(results)
for kind in ("single_node", "named"):
    mask = res.scenario_type == kind
    res.loc[mask, "risk_rank"] = res[mask].lost_margin_usd.rank(ascending=False, method="first").astype(int)
res["risk_rank"] = res["risk_rank"].astype(int)

for row, rank in zip(results, res["risk_rank"]):
    row["risk_rank"] = int(rank)
res_schema = """scenario_id STRING, scenario_type STRING, scenario_name STRING, node_id STRING, node_name STRING,
  tier INT, material_name STRING, region STRING, disruption_profile STRING, disrupted_node_ids ARRAY<STRING>,
  recovery_weeks DOUBLE, time_to_survive_weeks DOUBLE, exposure_gap_weeks DOUBLE, lost_margin_usd DOUBLE,
  lost_revenue_usd DOUBLE, impacted_products STRING, solver_status STRING, run_at TIMESTAMP, risk_rank INT"""
imp_schema = """impact_id STRING, scenario_id STRING, product_id STRING, product_name STRING, lost_cases BIGINT,
  lost_margin_usd DOUBLE, lost_revenue_usd DOUBLE"""
res_sdf = spark.createDataFrame(results, res_schema)
imp_sdf = spark.createDataFrame(impacts, imp_schema)
for name, sdf, comment in [
    ("gold_stress_test_results", res_sdf,
     "Portfolio stress test: one row per disruption scenario with TTR, TTS, exposure gap and gross margin lost"),
    ("gold_product_impact", imp_sdf, "Lost cases, gross margin and revenue per finished product per scenario"),
]:
    (sdf.write.mode("overwrite").option("overwriteSchema", "true")
        .option("delta.enableChangeDataFeed", "true").saveAsTable(f"{fq}.{name}"))
    spark.sql(f"COMMENT ON TABLE {fq}.{name} IS '{comment}'")
print("written")

# COMMAND ----------

# MAGIC %md ## Results: where is NorthBay exposed?

# COMMAND ----------

single = res[res.scenario_type == "single_node"].sort_values("risk_rank")
cols = ["risk_rank", "node_id", "node_name", "tier", "disruption_profile", "recovery_weeks",
        "time_to_survive_weeks", "exposure_gap_weeks", "lost_margin_usd", "lost_revenue_usd", "impacted_products"]
print(single[cols].head(12).to_string(index=False))

# COMMAND ----------

named = res[res.scenario_type == "named"].sort_values("risk_rank")
print(named[["scenario_name", "disrupted_node_ids", "recovery_weeks", "time_to_survive_weeks",
             "lost_margin_usd", "lost_revenue_usd", "impacted_products"]].to_string(index=False))

# COMMAND ----------

exposed = single[single.lost_margin_usd > 0]
print(f"Suppliers whose disruption causes unavoidable loss: {len(exposed)} of {len(single)}")
print(f"Gross margin at risk (sum over single-supplier disruptions): ${exposed.lost_margin_usd.sum() / 1e6:,.2f}M")
print(f"Revenue at risk (sum over single-supplier disruptions):      ${exposed.lost_revenue_usd.sum() / 1e6:,.2f}M")
top3 = exposed.head(3)
print(f"Top-3 suppliers account for {top3.lost_margin_usd.sum() / exposed.lost_margin_usd.sum():.0%} of margin at risk: "
      + ", ".join(top3.node_name))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Mitigation options: what is it worth to fix the top exposures?
# MAGIC
# MAGIC We re-run the full single-supplier portfolio on a modified network for each option:
# MAGIC
# MAGIC * **A. Dual-source sweetener**: qualify GulfCane Syrups (S208) for Morning Oats Cereal and Trail Granola Bar,
# MAGIC   which today depend only on Midwest Sweeteners (S207).
# MAGIC * **B. Seasoning buffer**: hold 6 extra weeks of Kettle Chips seasoning (6 × 60k case-eq) at FlavorCraft (S201).
# MAGIC * **C. Dual-source seasoning for chips**: qualify SpiceWorks (S202) for Kettle Chips.

# COMMAND ----------

import copy


def portfolio_margin_at_risk(nodes_, links_):
    ds = build_dataset(nodes_, links_)
    return sum(run_scenario(ds, [n["node_id"]], float(n["expected_recovery_weeks"]))["lost_margin_usd"]
               for n in nodes_ if n["tier"] > 1)


def with_links(extra):
    return links + [{"source_id": s, "target_id": t, "material_id": m} for s, t, m in extra]


def with_stock(node_id, extra_units):
    out = copy.deepcopy(nodes)
    for n in out:
        if n["node_id"] == node_id:
            n["on_hand_units"] = int(n["on_hand_units"]) + extra_units
    return out


dual_sweetener = [("S208", "FG02", "M-SWEET"), ("S208", "FG05", "M-SWEET")]
options = {
    "Baseline": (nodes, links),
    "A. Dual-source sweetener (S208 -> FG02, FG05)": (nodes, with_links(dual_sweetener)),
    "B. +6 weeks seasoning buffer at S201": (with_stock("S201", 6 * 60000), links),
    "C. Dual-source chips seasoning (S202 -> FG01)": (nodes, with_links([("S202", "FG01", "M-SEAS")])),
    "A + B": (with_stock("S201", 6 * 60000), with_links(dual_sweetener)),
}
base = None
print(f"{'Option':48} {'Margin at risk':>15} {'Reduction':>11}")
for name, (n_, l_) in options.items():
    v = portfolio_margin_at_risk(n_, l_)
    base = base or v
    print(f"{name:48} ${v / 1e6:>13,.2f}M {1 - v / base:>10.0%}")
print("\nC barely helps: SpiceWorks has no spare capacity to cover Kettle Chips, so dual sourcing alone is not enough;"
      " the buffer (B) plus sweetener dual-sourcing (A) is the recommended plan.")

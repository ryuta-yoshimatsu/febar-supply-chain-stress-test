# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Genie space: natural-language analytics over the governed network
# MAGIC
# MAGIC Planners ask descriptive questions ("which products are single-sourced for sweetener?", "how much weekly margin
# MAGIC does each plant generate?"). A Genie space over the gold tables answers them with generated SQL, so the
# MAGIC agent does not need hand-written queries for every question. The agent calls this space as one of its tools,
# MAGIC and the app's service principal is granted `CAN_RUN` on it.

# COMMAND ----------

# MAGIC %pip install -r requirements.txt --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "classic_stable_z57t9z_catalog")
dbutils.widgets.text("schema", "febar_supply_chain")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("lakebase_instance", "febar-supply-chain-db")
dbutils.widgets.text("lakebase_database", "databricks_postgres")
dbutils.widgets.text("app_name", "northbay-resilience")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
warehouse_id, app_name = dbutils.widgets.get("warehouse_id"), dbutils.widgets.get("app_name")
fq = f"{catalog}.{schema}"
TITLE = "NorthBay Foods · Supply Network Resilience"

# COMMAND ----------

import json
import os
import sys
import uuid

from databricks.sdk import WorkspaceClient

sys.path.append(os.path.abspath("../../app"))
from northbay_agent.genie import ask_genie
from northbay_agent.lakebase import Lakebase

w = WorkspaceClient()
db = Lakebase(instance=dbutils.widgets.get("lakebase_instance"), database=dbutils.widgets.get("lakebase_database"), w=w)


def _id():
    return uuid.uuid4().hex


tables = ["gold_disruption_scenarios", "gold_network_nodes", "gold_product_impact", "gold_sourcing_exposure",
          "gold_stress_test_results", "gold_supply_links"]
instructions = """You answer questions about NorthBay Foods' supply network (snacks & beverages, USA).
- gold_network_nodes: one row per node. tier 1 = finished-goods plant (node_id FGxx, one product family each),
  tier 2 = co-packer / packaging converter (S2xx), tier 3 = raw material supplier (R3xx). Volumes are weekly:
  cases for plants, case-equivalents for suppliers. demand_per_week, margin_usd_per_unit and price_usd_per_unit are
  only meaningful for tier 1.
- gold_supply_links: source_id supplies material_id to target_id.
- gold_sourcing_exposure: per (node, material) how many approved suppliers exist; single_sourced = true is a single
  point of failure.
- gold_stress_test_results: one row per disruption scenario (scenario_type 'single_node' = one supplier down for
  its expected recovery time, 'named' = multi-supplier scenarios). recovery_weeks = TTR, time_to_survive_weeks = TTS
  (52 = survives the whole year), exposure_gap_weeks = weeks exposed, lost_margin_usd = gross margin lost.
- gold_product_impact: lost cases / margin / revenue per product per scenario (join on scenario_id).
- Weekly gross margin of a plant = demand_per_week * margin_usd_per_unit. Annualise with 52 weeks.
- Always show supplier / product names next to ids and format money in USD."""

examples = [
    ("Which finished goods depend on a single supplier for any input?",
     f"""SELECT node_id, node_name, material_name, supplier_ids
FROM {fq}.gold_sourcing_exposure
WHERE single_sourced AND node_id LIKE 'FG%'
ORDER BY node_id, material_name"""),
    ("What are the top 5 suppliers by gross margin at risk?",
     f"""SELECT node_id, node_name, disruption_profile, recovery_weeks, time_to_survive_weeks, exposure_gap_weeks,
       lost_margin_usd, impacted_products
FROM {fq}.gold_stress_test_results
WHERE scenario_type = 'single_node'
ORDER BY lost_margin_usd DESC
LIMIT 5"""),
    ("What is the weekly and annual gross margin by plant?",
     f"""SELECT node_id, node_name, site_name, round(demand_per_week * margin_usd_per_unit) AS weekly_margin_usd,
       round(demand_per_week * margin_usd_per_unit * 52) AS annual_margin_usd
FROM {fq}.gold_network_nodes
WHERE tier = 1
ORDER BY weekly_margin_usd DESC"""),
]

space = {
    "version": 2,
    "config": {"sample_questions": [{"id": _id(), "question": [q]} for q in [
        "Which finished goods depend on a single supplier for any input?",
        "What are the top 5 suppliers by gross margin at risk?",
        "How many weeks of inventory does each plant hold?",
        "Which named scenario hurts Fizz Cola the most?",
    ]]},
    "data_sources": {"tables": [{"identifier": f"{fq}.{t}"} for t in tables]},
    "instructions": {
        "text_instructions": [{"id": _id(), "content": [line + "\n" for line in instructions.splitlines()]}],
        "example_question_sqls": [{"id": _id(), "question": [q], "sql": [line + "\n" for line in sql.splitlines()]}
                                  for q, sql in examples],
    },
}
# Genie requires ids sorted within each collection
space["config"]["sample_questions"].sort(key=lambda x: x["id"])
space["instructions"]["text_instructions"].sort(key=lambda x: x["id"])
space["instructions"]["example_question_sqls"].sort(key=lambda x: x["id"])

existing = [s for s in (w.genie.list_spaces().spaces or []) if s.title == TITLE]
if existing:
    space_id = existing[0].space_id
    w.genie.update_space(space_id, serialized_space=json.dumps(space), warehouse_id=warehouse_id, title=TITLE)
    print("updated Genie space", space_id)
else:
    space_id = w.genie.create_space(warehouse_id, json.dumps(space), title=TITLE,
                                    description="Natural-language analytics over NorthBay Foods' governed supply network gold tables").space_id
    print("created Genie space", space_id)

# COMMAND ----------

# MAGIC %md ## Give the app access and publish the space id to the app's config table (Lakebase)

# COMMAND ----------

app_sp = w.apps.get(app_name).service_principal_client_id
w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{space_id}", body={
    "access_control_list": [{"service_principal_name": app_sp, "permission_level": "CAN_RUN"}]})
w.api_client.do("PATCH", f"/api/2.0/permissions/warehouses/{warehouse_id}", body={
    "access_control_list": [{"service_principal_name": app_sp, "permission_level": "CAN_USE"}]})
db.execute("""INSERT INTO app_state.app_config (key, value) VALUES ('genie_space_id', %s)
              ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""", (space_id,))
print(f"app {app_name} ({app_sp}): CAN_RUN on space, CAN_USE on warehouse; genie_space_id published")
print(f"{w.config.host}/genie/rooms/{space_id}")

# COMMAND ----------

# MAGIC %md ## Ask Genie (evidence that the space answers real questions)

# COMMAND ----------

for q in ["Which finished goods depend on a single supplier for any input?",
          "How many weeks of inventory does each plant hold? Show on-hand cases and weekly demand.",
          "Which named disruption scenario costs the most gross margin, and which products does it hit?"]:
    a = ask_genie(q, space_id=space_id, w=w)
    print("=" * 100)
    print("Q:", q)
    print("Status:", a["status"])
    print("Answer:", a["answer"])
    print("SQL:\n" + (a["sql"] or ""))
    print("Columns:", a["columns"])
    for row in a["rows"][:12]:
        print("  ", row)

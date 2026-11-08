# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Operational serving with Lakebase
# MAGIC
# MAGIC The business app and the agent need **millisecond lookups and transactional writes**, not warehouse scans:
# MAGIC "what does S207 supply?", "log this what-if run", "show the latest scenarios". Lakebase (managed Postgres) gives
# MAGIC us that while staying governed by Unity Catalog:
# MAGIC
# MAGIC * `northbay_serving.*`: **synced tables**, replicas of the gold Delta tables kept up to date by a managed sync pipeline.
# MAGIC * `app_state.*`: operational tables the app writes to (what-if scenario log, chat history, app config).

# COMMAND ----------

# MAGIC %pip install -r requirements.txt --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "classic_stable_z57t9z_catalog")
dbutils.widgets.text("schema", "febar_supply_chain")
dbutils.widgets.text("lakebase_instance", "febar-supply-chain-db")
dbutils.widgets.text("serving_schema", "northbay_serving")
dbutils.widgets.text("lakebase_database", "databricks_postgres")
dbutils.widgets.text("app_name", "northbay-resilience")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
instance, serving = dbutils.widgets.get("lakebase_instance"), dbutils.widgets.get("serving_schema")
lb_database, app_name = dbutils.widgets.get("lakebase_database"), dbutils.widgets.get("app_name")
fq = f"{catalog}.{schema}"

# COMMAND ----------

import os
import sys
import time

from databricks.sdk import WorkspaceClient

sys.path.append(os.path.abspath("../../app"))
from northbay_agent.lakebase import Lakebase

w = WorkspaceClient()
inst = w.database.get_database_instance(name=instance)
print(f"Lakebase instance {inst.name}: {inst.state.value}, capacity {inst.capacity}, host {inst.read_write_dns}")
db = Lakebase(instance=instance, database=lb_database, w=w)

# COMMAND ----------

# MAGIC %md ## Operational schemas and tables

# COMMAND ----------

db.execute("""
CREATE SCHEMA IF NOT EXISTS app_state;
CREATE TABLE IF NOT EXISTS app_state.scenario_runs (
    run_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    scenario_name TEXT,
    disrupted_node_ids TEXT[] NOT NULL,
    recovery_weeks DOUBLE PRECISION NOT NULL,
    lost_margin_usd DOUBLE PRECISION,
    time_to_survive_weeks DOUBLE PRECISION,
    exposure_gap_weeks DOUBLE PRECISION,
    result JSONB,
    requested_by TEXT
);
CREATE INDEX IF NOT EXISTS scenario_runs_created_at ON app_state.scenario_runs (created_at DESC);
CREATE TABLE IF NOT EXISTS app_state.chat_messages (
    message_id UUID PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_email TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_session ON app_state.chat_messages (session_id, created_at);
CREATE TABLE IF NOT EXISTS app_state.app_config (key TEXT PRIMARY KEY, value TEXT NOT NULL,
                                                 updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
""")
print(db.query("SELECT table_schema, table_name FROM information_schema.tables "
               "WHERE table_schema IN ('northbay_serving', 'app_state') ORDER BY 1, 2"))

# COMMAND ----------

# MAGIC %md ## Synced tables: gold Delta → Lakebase

# COMMAND ----------

synced = {  # table in UC schema / Postgres schema `northbay_serving` -> (gold source table, primary key)
    "network_nodes": ("gold_network_nodes", ["node_id"]),
    "supply_links": ("gold_supply_links", ["link_id"]),
    "sourcing_exposure": ("gold_sourcing_exposure", ["exposure_id"]),
    "stress_test_results": ("gold_stress_test_results", ["scenario_id"]),
    "product_impact": ("gold_product_impact", ["impact_id"]),
}


def api(method, path, body=None):
    return w.api_client.do(method, f"/api/2.0/database/synced_tables{path}", body=body)


pipelines = {}
for target, (source, pk) in synced.items():
    name = f"{catalog}.{serving}.{target}"
    try:
        existing = api("GET", f"/{name}")
    except Exception:
        existing = None
    if existing:
        pipeline_id = existing["data_synchronization_status"]["pipeline_id"]
        w.pipelines.start_update(pipeline_id=pipeline_id)  # snapshot refresh after the upstream rerun
        print(f"refreshing {name}")
    else:
        created = api("POST", "", {
            "name": name,
            "spec": {
                "source_table_full_name": f"{fq}.{source}",
                "primary_key_columns": pk,
                "scheduling_policy": "SNAPSHOT",
                "new_pipeline_spec": {"storage_catalog": catalog, "storage_schema": schema},
            },
            "database_instance_name": instance,
            "logical_database_name": lb_database,
        })
        pipeline_id = created.get("data_synchronization_status", {}).get("pipeline_id")
        print(f"created {name}")
    pipelines[name] = pipeline_id

# COMMAND ----------

deadline = time.time() + 30 * 60
pending = set(pipelines)
while pending and time.time() < deadline:
    for name in sorted(pending):
        status = api("GET", f"/{name}").get("data_synchronization_status", {})
        state = status.get("detailed_state", "")
        if state.startswith("SYNCED_TABLE_ONLINE"):
            print(f"{name}: {state}")
            pending.discard(name)
        elif "FAILED" in state:
            raise RuntimeError(f"{name}: {state} {status.get('message')}")
    if pending:
        time.sleep(30)
assert not pending, f"still syncing: {pending}"

# COMMAND ----------

# MAGIC %md ## Grant the app's service principal access in Postgres

# COMMAND ----------

app_sp = w.apps.get(app_name).service_principal_client_id
roles = {r.name: r for r in w.database.list_database_instance_roles(instance)}
print("app role:", app_sp, roles[app_sp].identity_type if app_sp in roles else "missing")
db.execute(f"""
GRANT USAGE ON SCHEMA {serving}, app_state TO "{app_sp}";
GRANT SELECT ON ALL TABLES IN SCHEMA {serving} TO "{app_sp}";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app_state TO "{app_sp}";
""")
print(db.query("""SELECT table_schema, table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type) AS privileges
                  FROM information_schema.role_table_grants WHERE grantee = %s GROUP BY 1, 2 ORDER BY 1, 2""",
               (app_sp,)))

# COMMAND ----------

# MAGIC %md ## Verify: low-latency lookups the app and agent perform

# COMMAND ----------

for t in synced:
    print(f"{serving}.{t}: {db.query(f'SELECT count(*) AS n FROM {serving}.{t}')[0]['n']} rows")

t0 = time.time()
rows = db.query(f"""SELECT node_id, node_name, recovery_weeks, time_to_survive_weeks, lost_margin_usd
                   FROM {serving}.stress_test_results WHERE scenario_type = 'single_node'
                   ORDER BY risk_rank LIMIT 5""")
print(f"top-5 risk lookup in {1000 * (time.time() - t0):.0f} ms (including connection setup)")
for r in rows:
    print(r)

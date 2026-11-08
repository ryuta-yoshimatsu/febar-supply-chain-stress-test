# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Govern the data product in Unity Catalog
# MAGIC
# MAGIC * **Discoverability**: table and column comments, tags for domain / data product / sensitivity.
# MAGIC * **Least-privilege access**: the business app's service principal gets read-only access to the gold layer only
# MAGIC   (Genie queries run with it); bronze/silver stay private to the data engineering team.
# MAGIC * **Lineage**: captured automatically by Unity Catalog from raw files through the pipeline, the stress test and
# MAGIC   the Lakebase synced tables; queried below from the lineage system table.

# COMMAND ----------

dbutils.widgets.text("catalog", "classic_stable_z57t9z_catalog")
dbutils.widgets.text("schema", "febar_supply_chain")
dbutils.widgets.text("app_name", "northbay-resilience")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
app_name = dbutils.widgets.get("app_name")
fq = f"{catalog}.{schema}"

# COMMAND ----------

column_comments = {
    "gold_network_nodes": {
        "node_id": "Network node id: FGxx finished-goods plant, S2xx Tier-2 supplier, R3xx Tier-3 supplier",
        "tier": "1 = finished-goods plant, 2 = co-packer / converter, 3 = raw material supplier",
        "capacity_per_week": "Maximum output per week (cases for plants, case-equivalents for suppliers)",
        "on_hand_units": "Latest on-hand inventory from the WMS snapshot",
        "demand_per_week": "Average forecast demand over the next 4 weeks (plants only)",
        "margin_usd_per_unit": "Gross margin per case in USD (plants only)",
        "expected_recovery_weeks": "Weeks to restore the supplier after its typical disruption (time to recover, TTR)",
    },
    "gold_stress_test_results": {
        "recovery_weeks": "Time to recover (TTR): weeks the disrupted nodes produce nothing",
        "time_to_survive_weeks": "Time to survive (TTS): weeks demand is fully met without the nodes (52 = whole year)",
        "exposure_gap_weeks": "max(TTR - TTS, 0): weeks the business is exposed",
        "lost_margin_usd": "Unavoidable gross margin lost during recovery after optimal re-planning",
        "lost_revenue_usd": "Revenue of the lost cases at list price",
        "risk_rank": "Rank by gross margin lost within the scenario type (1 = most costly)",
    },
    "gold_sourcing_exposure": {
        "n_suppliers": "Approved suppliers for this (node, material); 1 = single point of failure",
    },
}
def alter(table, clause):
    """Pipeline-managed gold tables are materialized views; stress-test outputs are Delta tables."""
    try:
        spark.sql(f"ALTER TABLE {fq}.{table} {clause}")
    except Exception:
        spark.sql(f"ALTER MATERIALIZED VIEW {fq}.{table} {clause}")


for table, cols in column_comments.items():
    for col, text in cols.items():
        alter(table, f"ALTER COLUMN {col} COMMENT '{text}'")

# Keys are prefixed so they do not collide with workspace-wide governed tag policies (e.g. a governed `domain` key)
tags = {"nb_domain": "supply_chain", "nb_data_product": "northbay_network_resilience", "nb_owner": "supply_chain_analytics"}
gold = [r.tableName for r in spark.sql(f"SHOW TABLES IN {fq}").collect() if r.tableName.startswith("gold_")]
for key, value in tags.items():
    try:
        spark.sql(f"ALTER SCHEMA {fq} SET TAGS ('{key}' = '{value}')")
        for t in gold:
            alter(t, f"SET TAGS ('{key}' = '{value}')")
        print(f"tag {key}={value} on schema + {len(gold)} gold tables")
    except Exception as e:  # governed tag policies may restrict keys/values in this workspace
        print(f"skipped tag {key}: {str(e).splitlines()[0][:160]}")

# COMMAND ----------

# MAGIC %md ## Least-privilege grants for the business app

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
app_sp = w.apps.get(app_name).service_principal_client_id
spark.sql(f"GRANT USE CATALOG ON CATALOG {catalog} TO `{app_sp}`")
spark.sql(f"GRANT USE SCHEMA ON SCHEMA {fq} TO `{app_sp}`")
for t in gold:
    spark.sql(f"GRANT SELECT ON TABLE {fq}.{t} TO `{app_sp}`")
print(f"app service principal {app_sp}: USE CATALOG, USE SCHEMA, SELECT on {len(gold)} gold tables")

# COMMAND ----------

print(spark.sql(f"""
  SELECT t.table_name, t.table_type, t.comment, concat_ws(', ', collect_list(concat(g.tag_name, '=', g.tag_value))) AS tags
  FROM {catalog}.information_schema.tables t
  LEFT JOIN {catalog}.information_schema.table_tags g
    ON g.schema_name = t.table_schema AND g.table_name = t.table_name
  WHERE t.table_schema = '{schema}' AND t.table_name NOT LIKE '\\_\\_%' AND t.table_name NOT LIKE 'event_log%'
  GROUP BY ALL ORDER BY t.table_name""").toPandas().to_string(index=False, max_colwidth=70))

# COMMAND ----------

print(spark.sql(f"""
  SELECT privilege_type, table_name, grantee
  FROM {catalog}.information_schema.table_privileges
  WHERE table_schema = '{schema}' AND grantee = '{app_sp}' ORDER BY table_name""").toPandas().to_string(index=False))

# COMMAND ----------

# MAGIC %md ## Lineage (from `system.access.table_lineage`; can lag the first run by a few minutes)

# COMMAND ----------

print(spark.sql(f"""
  SELECT DISTINCT coalesce(source_table_full_name, source_path) AS source,
         target_table_full_name AS target, entity_type
  FROM system.access.table_lineage
  WHERE (target_table_full_name LIKE '{fq}.%' OR target_table_full_name LIKE '{catalog}.northbay_serving.%')
    AND target_table_full_name NOT LIKE '%event_log%' AND target_table_full_name NOT LIKE '%__materialization%'
    AND event_date >= current_date() - 7
  ORDER BY target, source""").toPandas().to_string(index=False, max_colwidth=90))

# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Land raw source-system extracts (synthetic)
# MAGIC
# MAGIC NorthBay Foods' planning data lives in five systems. This notebook simulates their nightly extracts and lands
# MAGIC them as raw files in a Unity Catalog Volume, which the Lakeflow pipeline ingests incrementally with Auto Loader.
# MAGIC
# MAGIC | System | Extract | Format |
# MAGIC |---|---|---|
# MAGIC | ERP | Finished-goods plants: capacity, margin, price | CSV |
# MAGIC | SRM | Supplier & material masters, expected recovery times | CSV |
# MAGIC | PLM | Approved supply links (who supplies what to whom) | JSON lines |
# MAGIC | WMS | Weekly on-hand inventory snapshots | JSON lines |
# MAGIC | APS | 13-week demand forecast | CSV |
# MAGIC | Risk | Named multi-node disruption scenarios | CSV |
# MAGIC
# MAGIC The data is fully synthetic (fixed seed). A few realistic data-quality issues are injected on purpose
# MAGIC (a duplicated supplier record, a negative inventory scan, a link to a supplier missing from SRM) so the
# MAGIC pipeline's expectations have something to catch.

# COMMAND ----------

dbutils.widgets.text("catalog", "classic_stable_z57t9z_catalog")
dbutils.widgets.text("schema", "febar_supply_chain")
dbutils.widgets.text("serving_schema", "northbay_serving")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
serving_schema = dbutils.widgets.get("serving_schema")
raw_root = f"/Volumes/{catalog}/{schema}/raw_landing"
print(raw_root)

# COMMAND ----------

import os
import sys

sys.path.append(os.path.abspath(".."))  # src/ -> northbay_data package
from northbay_data.synthetic import generate, PRODUCTS, SUPPLIERS

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema} "
          "COMMENT 'NorthBay Foods supply network resilience data product: raw volume, bronze/silver/gold, agent'")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{serving_schema} "
          "COMMENT 'Lakebase synced tables: operational serving copies of the gold tables'")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.raw_landing COMMENT 'Raw landing zone for source-system extracts'")

files = generate()
for rel_path, content in files.items():
    path = f"{raw_root}/{rel_path}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)

print(f"Network: {len(PRODUCTS)} finished-goods plants, "
      f"{sum(1 for s in SUPPLIERS if s[2] == 2)} Tier-2 and {sum(1 for s in SUPPLIERS if s[2] == 3)} Tier-3 suppliers")
for rel_path in sorted(files):
    print(f"{len(files[rel_path].splitlines()):>4} lines  {raw_root}/{rel_path}")

# COMMAND ----------

# MAGIC %md Peek at two raw extracts as the source systems deliver them.

# COMMAND ----------

print(files["erp/products/products_20261102.csv"])
print("\n".join(files["plm/supply_links/supply_links.json"].splitlines()[:5]))

"""Runtime configuration, shared by the Databricks App and the notebooks (overridable via environment variables)."""
import os

CATALOG = os.getenv("NB_CATALOG", "classic_stable_z57t9z_catalog")
SCHEMA = os.getenv("NB_SCHEMA", "febar_supply_chain")

LLM_ENDPOINT = os.getenv("NB_LLM_ENDPOINT", "databricks-claude-sonnet-5-5")

LAKEBASE_INSTANCE = os.getenv("NB_LAKEBASE_INSTANCE", "febar-supply-chain-db")
LAKEBASE_DATABASE = os.getenv("NB_LAKEBASE_DATABASE", "databricks_postgres")
LAKEBASE_SERVING_SCHEMA = os.getenv("NB_LAKEBASE_SERVING_SCHEMA", "northbay_serving")  # synced from gold Delta tables
LAKEBASE_APP_SCHEMA = os.getenv("NB_LAKEBASE_APP_SCHEMA", "app_state")       # written by the app / agent

GENIE_SPACE_ID = os.getenv("NB_GENIE_SPACE_ID", "")

# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Evaluate and register the resilience agent
# MAGIC
# MAGIC The agent (LangGraph + `databricks-claude-sonnet-5-5`) has four tools:
# MAGIC
# MAGIC | Tool | Backed by | Used for |
# MAGIC |---|---|---|
# MAGIC | `get_risk_ranking` | Lakebase `northbay_serving.stress_test_results` | "Where are we most exposed?" |
# MAGIC | `get_node_details` | Lakebase `northbay_serving.network_nodes / supply_links / sourcing_exposure` | Facts about a plant / supplier |
# MAGIC | `run_disruption_scenario` | TTR/TTS optimization on the live network, logged to Lakebase `app_state.scenario_runs` | What-if questions |
# MAGIC | `ask_genie` | Genie space over the gold tables | Descriptive analytics |
# MAGIC
# MAGIC This notebook runs demo conversations, evaluates the agent with MLflow (LLM judges + a custom tool-routing
# MAGIC scorer), and logs / registers it in Unity Catalog. The same package runs inside the Databricks App.

# COMMAND ----------

# MAGIC %pip install -r requirements.txt --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "classic_stable_z57t9z_catalog")
dbutils.widgets.text("schema", "febar_supply_chain")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("lakebase_instance", "febar-supply-chain-db")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
warehouse_id, lakebase_instance = dbutils.widgets.get("warehouse_id"), dbutils.widgets.get("lakebase_instance")
fq = f"{catalog}.{schema}"
MODEL_NAME = f"{fq}.northbay_resilience_agent"

# COMMAND ----------

import os
import sys

import mlflow

APP_DIR = os.path.abspath("../../app")
sys.path.append(APP_DIR)
from northbay_agent import config
from northbay_agent.lakebase import get_lakebase

config.GENIE_SPACE_ID = get_lakebase().query(
    "SELECT value FROM app_state.app_config WHERE key = 'genie_space_id'")[0]["value"]
user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/northbay-resilience-agent")
mlflow.langchain.autolog()

from northbay_agent.agent import NorthBayResilienceAgent

AGENT = NorthBayResilienceAgent()
print("Genie space:", config.GENIE_SPACE_ID, "| LLM:", config.LLM_ENDPOINT)

# COMMAND ----------

# MAGIC %md ## Demo conversations

# COMMAND ----------

from mlflow.types.agent import ChatAgentMessage


def chat(question: str):
    resp = AGENT.predict(messages=[ChatAgentMessage(role="user", content=question)])
    tools = [tc.function.name for m in resp.messages if m.tool_calls for tc in m.tool_calls]
    return resp.messages[-1].content, tools


for q in [
    "Where is NorthBay most exposed? Give me the top 3 suppliers and what they put at risk.",
    "Midwest Sweeteners (S207) just had a refinery explosion and expects 9 weeks to recover. What happens and what should we do?",
    "Which of our finished goods depend on a single supplier for any input?",
]:
    answer, tools = chat(q)
    print("=" * 100)
    print("USER:", q)
    print("TOOLS:", tools)
    print("AGENT:\n" + answer)

# COMMAND ----------

# MAGIC %md ## Evaluation

# COMMAND ----------

from mlflow.entities import Feedback
from mlflow.genai.scorers import Guidelines, RelevanceToQuery, Safety, scorer

eval_data = [
    {"inputs": {"question": "Which suppliers would hurt us most if they went down?"},
     "expectations": {"expected_tools": ["get_risk_ranking"]}},
    {"inputs": {"question": "What happens if FlavorCraft Blends (S201) has a blending-line fire and is down for 10 weeks?"},
     "expectations": {"expected_tools": ["run_disruption_scenario"]}},
    {"inputs": {"question": "A hurricane takes out GulfCane Syrups (S208), Gulf Coast Resins (R303) and Bayou Sugar Mill (R309) for 8 weeks. Impact and actions?"},
     "expectations": {"expected_tools": ["run_disruption_scenario"]}},
    {"inputs": {"question": "If ClearPak Bottling (S203) is down 4 weeks, can we still serve Fizz Cola and SunValley Orange Drink?"},
     "expectations": {"expected_tools": ["run_disruption_scenario"]}},
    {"inputs": {"question": "What does BoxCraft Packaging supply and to which plants?"},
     "expectations": {"expected_tools": ["get_node_details", "ask_genie"]}},
    {"inputs": {"question": "How many weeks of finished-goods inventory does each plant hold?"},
     "expectations": {"expected_tools": ["ask_genie", "get_node_details"]}},
    {"inputs": {"question": "Which finished goods are single-sourced for sweetener?"},
     "expectations": {"expected_tools": ["ask_genie", "get_node_details"]}},
    {"inputs": {"question": "What's a good recipe for chocolate chip cookies?"},
     "expectations": {"expected_tools": []}},
]


@mlflow.trace(span_type="AGENT")
def predict_fn(question: str) -> str:
    resp = AGENT.predict(messages=[ChatAgentMessage(role="user", content=question)])
    return resp.messages[-1].content


@scorer
def tool_routing(trace, expectations) -> Feedback:
    """The agent must call at least one of the expected tools (or none for off-topic questions)."""
    called = sorted({s.name for s in trace.search_spans(span_type="TOOL")})
    expected = expectations["expected_tools"]
    ok = (not called) if not expected else bool(set(called) & set(expected))
    return Feedback(value=ok, rationale=f"called={called}, expected one of {expected}")


scorers = [
    tool_routing,
    RelevanceToQuery(),
    Safety(),
    Guidelines(name="business_ready", guidelines=[
        "If the question is about NorthBay's supply chain, the response quantifies impact with concrete numbers "
        "(USD and/or weeks) and avoids optimization jargon such as 'decision variables' or 'objective function'.",
        "If the question is off-topic (not about NorthBay's supply chain), the response politely declines.",
    ]),
    Guidelines(name="actionable", guidelines=[
        "If the question asks what happens or what to do about a disruption, the response gives at least two "
        "concrete recommended actions. Otherwise this guideline is satisfied.",
    ]),
]

results = mlflow.genai.evaluate(data=eval_data, predict_fn=predict_fn, scorers=scorers)
print({k: round(v, 3) if isinstance(v, float) else v for k, v in results.metrics.items()})

# COMMAND ----------

tbl = results.tables["eval_results"] if hasattr(results, "tables") and "eval_results" in results.tables else None
if tbl is None:
    tbl = mlflow.search_traces(run_id=results.run_id)
cols = [c for c in tbl.columns if c.endswith("/value") or c in ("request", "inputs")]
print(tbl[cols].to_string(max_colwidth=90))

# COMMAND ----------

# MAGIC %md ## Log and register in Unity Catalog

# COMMAND ----------

from mlflow.models.resources import DatabricksGenieSpace, DatabricksServingEndpoint, DatabricksSQLWarehouse

resources = [DatabricksServingEndpoint(endpoint_name=config.LLM_ENDPOINT),
             DatabricksGenieSpace(genie_space_id=config.GENIE_SPACE_ID),
             DatabricksSQLWarehouse(warehouse_id=warehouse_id)]
try:
    from mlflow.models.resources import DatabricksLakebase
    resources.append(DatabricksLakebase(database_instance_name=lakebase_instance))
except ImportError:
    pass

with mlflow.start_run(run_name="northbay-resilience-agent"):
    info = mlflow.pyfunc.log_model(
        name="agent",
        python_model=os.path.join(APP_DIR, "agent_model.py"),
        code_paths=[os.path.join(APP_DIR, "northbay_agent")],
        pip_requirements=[l.strip() for l in open("requirements.txt") if l.strip() and not l.startswith("#")],
        resources=resources,
        input_example={"messages": [{"role": "user", "content": "Which suppliers would hurt us most if they went down?"}]},
    )
    mlflow.log_metrics({k.replace("/", "_"): v for k, v in results.metrics.items() if isinstance(v, (int, float))})

mlflow.set_registry_uri("databricks-uc")
version = mlflow.register_model(info.model_uri, MODEL_NAME).version
mlflow.MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", version)
print(f"registered {MODEL_NAME} version {version} (alias: champion)")

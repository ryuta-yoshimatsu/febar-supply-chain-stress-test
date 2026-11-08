"""Agent tools. Operational data comes from Lakebase (synced from the gold Delta tables), ad-hoc analytics
from the Genie space, and what-if answers from the TTR/TTS optimization models."""
import json
import uuid

from langchain_core.tools import tool

from . import config
from .genie import ask_genie as _ask_genie
from .lakebase import get_lakebase
from .network import build_dataset, run_scenario

S = config.LAKEBASE_SERVING_SCHEMA
A = config.LAKEBASE_APP_SCHEMA


def load_network():
    db = get_lakebase()
    nodes = db.query(f"SELECT * FROM {S}.network_nodes")
    links = db.query(f"SELECT source_id, target_id, material_id FROM {S}.supply_links")
    return nodes, links


def save_scenario_run(result: dict, scenario_name: str, requested_by: str = "agent") -> str:
    run_id = str(uuid.uuid4())
    get_lakebase().execute(
        f"""INSERT INTO {A}.scenario_runs (run_id, scenario_name, disrupted_node_ids, recovery_weeks,
                lost_margin_usd, time_to_survive_weeks, exposure_gap_weeks, result, requested_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
        (run_id, scenario_name, result["disrupted_node_ids"], result["recovery_weeks"], result["lost_margin_usd"],
         result["time_to_survive_weeks"], result["exposure_gap_weeks"], json.dumps(result), requested_by))
    return run_id


@tool
def get_risk_ranking(top_n: int = 10) -> str:
    """Return the suppliers whose disruption costs NorthBay Foods the most, from the latest portfolio stress test.
    Each row has the supplier, its expected recovery time (TTR), how long the network survives without it (TTS),
    the exposure gap (TTR - TTS) and the gross margin lost during recovery. Use this for 'where are we most exposed?'."""
    rows = get_lakebase().query(
        f"""SELECT node_id, node_name, tier, material_name, region, disruption_profile, recovery_weeks,
                   time_to_survive_weeks, exposure_gap_weeks, lost_margin_usd, impacted_products, risk_rank
            FROM {S}.stress_test_results WHERE scenario_type = 'single_node'
            ORDER BY risk_rank LIMIT %s""", (int(top_n),))
    return json.dumps(rows, default=str)


@tool
def get_node_details(node_ids: list[str]) -> str:
    """Look up network nodes by id (e.g. FG01, S207, R303): name, tier, location, material, weekly capacity,
    on-hand inventory, demand and margin (finished goods), plus their direct suppliers and customers and
    whether each input material is single-sourced. Use this before reasoning about a specific node."""
    db = get_lakebase()
    nodes = db.query(f"SELECT * FROM {S}.network_nodes WHERE node_id = ANY(%s)", (node_ids,))
    links = db.query(f"""SELECT source_id, target_id, material_id FROM {S}.supply_links
                         WHERE source_id = ANY(%s) OR target_id = ANY(%s)""", (node_ids, node_ids))
    exposure = db.query(f"SELECT * FROM {S}.sourcing_exposure WHERE node_id = ANY(%s)", (node_ids,))
    return json.dumps({"nodes": nodes, "links": links, "sourcing": exposure}, default=str)


@tool
def run_disruption_scenario(disrupted_node_ids: list[str], recovery_weeks: float, scenario_name: str = "") -> str:
    """Run a what-if disruption on the live network: the given nodes produce nothing for `recovery_weeks` weeks.
    Solves the multi-tier optimization model with and without the disruption and returns the gross margin lost,
    time-to-survive, impact per finished product and how upstream production should be rebalanced.
    The run is saved to the scenario log."""
    nodes, links = load_network()
    names = {n["node_id"]: n["node_name"] for n in nodes}
    unknown = [n for n in disrupted_node_ids if n not in names]
    if unknown:
        return json.dumps({"error": f"Unknown node ids: {unknown}. Use get_node_details or ask_genie to find ids."})

    result = run_scenario(build_dataset(nodes, links), disrupted_node_ids, float(recovery_weeks))
    for p in result["product_impact"]:
        p["product_name"] = names[p["product_id"]]
    for r in result["plan_rebalancing"]:
        r["node_name"] = names[r["node_id"]]
    result["plan_rebalancing"] = result["plan_rebalancing"][:10]
    result["disrupted_nodes"] = [{"node_id": n, "node_name": names[n]} for n in disrupted_node_ids]
    try:
        result["scenario_run_id"] = save_scenario_run(
            result, scenario_name or ", ".join(names[n] for n in disrupted_node_ids))
    except Exception as e:  # the answer is still useful if the scenario log is unavailable
        result["scenario_log_error"] = str(e)[:200]
    return json.dumps(result, default=str)


@tool
def ask_genie(question: str) -> str:
    """Ask the NorthBay supply network Genie space an analytical question in natural language, e.g.
    'Which finished goods depend on a single supplier for any material?' or 'Total weekly demand by category'.
    Genie writes and runs SQL over the governed gold tables and returns the answer, the SQL and the rows.
    Use this for descriptive questions about the data, not for what-if disruptions."""
    return json.dumps(_ask_genie(question), default=str)


TOOLS = [get_risk_ranking, get_node_details, run_disruption_scenario, ask_genie]

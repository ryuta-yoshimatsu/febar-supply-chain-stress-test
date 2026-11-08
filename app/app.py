"""NorthBay Resilience: Databricks App surfacing the supply network stress test to planners and leadership."""
import json
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from northbay_agent import config
from northbay_agent.agent import NorthBayResilienceAgent
from northbay_agent.lakebase import get_lakebase

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("northbay")

S, A = config.LAKEBASE_SERVING_SCHEMA, config.LAKEBASE_APP_SCHEMA
TOOL_LABELS = {
    "get_risk_ranking": "Reading the portfolio stress test (Lakebase)",
    "get_node_details": "Looking up network nodes (Lakebase)",
    "run_disruption_scenario": "Re-optimizing the network for this disruption",
    "ask_genie": "Asking Genie",
}

app = FastAPI(title="NorthBay Resilience")
_agent = None


def agent() -> NorthBayResilienceAgent:
    global _agent
    if _agent is None:
        if not config.GENIE_SPACE_ID:  # published by the Genie setup notebook
            rows = get_lakebase().query(f"SELECT value FROM {A}.app_config WHERE key = 'genie_space_id'")
            config.GENIE_SPACE_ID = rows[0]["value"] if rows else ""
        _agent = NorthBayResilienceAgent()
    return _agent


def _rows(sql, params=None):
    return json.loads(json.dumps(get_lakebase().query(sql, params), default=str))


@app.get("/api/overview")
def overview():
    db_rows = _rows(f"""SELECT node_id, node_name, tier, material_name, region, disruption_profile, recovery_weeks,
                               time_to_survive_weeks, exposure_gap_weeks, lost_margin_usd, lost_revenue_usd,
                               impacted_products, risk_rank
                        FROM {S}.stress_test_results WHERE scenario_type = 'single_node' ORDER BY risk_rank""")
    named = _rows(f"""SELECT scenario_name, disrupted_node_ids, recovery_weeks, time_to_survive_weeks,
                             lost_margin_usd, lost_revenue_usd, impacted_products
                      FROM {S}.stress_test_results WHERE scenario_type = 'named' ORDER BY risk_rank""")
    single_sourced = _rows(f"""SELECT node_id, node_name, material_name, supplier_ids FROM {S}.sourcing_exposure
                               WHERE single_sourced AND node_id LIKE 'FG%' ORDER BY node_id, material_name""")
    plants = _rows(f"""SELECT node_id, node_name, site_name, demand_per_week, margin_usd_per_unit, on_hand_units
                       FROM {S}.network_nodes WHERE tier = 1 ORDER BY node_id""")
    exposed = [r for r in db_rows if r["lost_margin_usd"] > 0]
    weekly_margin = sum(p["demand_per_week"] * p["margin_usd_per_unit"] for p in plants)
    return {
        "kpis": {
            "margin_at_risk_usd": sum(r["lost_margin_usd"] for r in exposed),
            "revenue_at_risk_usd": sum(r["lost_revenue_usd"] for r in exposed),
            "exposed_suppliers": len(exposed),
            "suppliers": len(db_rows),
            "single_sourced_inputs": len(single_sourced),
            "annual_margin_usd": weekly_margin * 52,
        },
        "risk_ranking": db_rows,
        "named_scenarios": named,
        "single_sourced": single_sourced,
    }


@app.get("/api/scenarios")
def scenarios():
    return _rows(f"""SELECT run_id, created_at, scenario_name, disrupted_node_ids, recovery_weeks, lost_margin_usd,
                            time_to_survive_weeks, exposure_gap_weeks, requested_by
                     FROM {A}.scenario_runs ORDER BY created_at DESC LIMIT 25""")


class ChatRequest(BaseModel):
    session_id: str
    messages: list[dict]


def _save_message(session_id, user, role, content):
    try:
        get_lakebase().execute(
            f"INSERT INTO {A}.chat_messages (message_id, session_id, user_email, role, content) VALUES (%s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), session_id, user, role, content))
    except Exception as e:  # chat history is best-effort
        log.warning("could not persist chat message: %s", e)


def _events(req: ChatRequest, user: str):
    messages = [{"role": m["role"], "content": m["content"]} for m in req.messages]
    _save_message(req.session_id, user, "user", messages[-1]["content"])
    try:
        answer = ""
        for event in agent().graph.stream({"messages": messages}, stream_mode="updates"):
            for node_data in event.values():
                for msg in node_data["messages"]:
                    for call in msg.get("tool_calls") or []:
                        name = call["function"]["name"]
                        yield f"data: {json.dumps({'type': 'status', 'text': TOOL_LABELS.get(name, name)})}\n\n"
                    if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
                        answer = msg["content"]
        answer = answer or "Sorry, I could not produce an answer."
        _save_message(req.session_id, user, "assistant", answer)
        yield f"data: {json.dumps({'type': 'answer', 'text': answer})}\n\n"
    except Exception as e:
        log.exception("agent failed")
        yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    user = request.headers.get("X-Forwarded-Email", "unknown")
    return StreamingResponse(_events(req, user), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse("static/index.html")

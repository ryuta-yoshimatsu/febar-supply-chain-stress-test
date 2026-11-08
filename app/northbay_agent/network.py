"""Turn governed network tables (gold Delta tables or their Lakebase replicas) into optimizer input,
and run the time-to-recover (TTR) / time-to-survive (TTS) models on top of it."""
import pyomo.environ as pyo

from .optimizer import build_and_solve_ttr, build_and_solve_tts

# TTS is unbounded when the remaining network can serve demand indefinitely; cap it at one planning year
TTS_HORIZON_WEEKS = 52


def build_dataset(nodes: list[dict], links: list[dict]) -> dict:
    """Build the optimizer dataset.

    nodes: rows of gold_network_nodes (node_id, tier, material_id, capacity_per_week,
           on_hand_units, demand_per_week, margin_usd_per_unit)
    links: rows of gold_supply_links (source_id, target_id, material_id)
    """
    by_tier = {1: [], 2: [], 3: []}
    for n in nodes:
        by_tier[int(n["tier"])].append(n["node_id"])
    tier1, tier2, tier3 = (sorted(by_tier[t]) for t in (1, 2, 3))
    known = set(tier1 + tier2 + tier3)

    edges = [(l["source_id"], l["target_id"]) for l in links
             if l["source_id"] in known and l["target_id"] in known]
    supplier_material_type = {n["node_id"]: n["material_id"] for n in nodes if int(n["tier"]) > 1}
    material_types = sorted(set(supplier_material_type.values()))

    N_minus = {j: [] for j in tier1 + tier2}
    N_plus = {i: [] for i in tier2 + tier3}
    P = {j: {} for j in tier1 + tier2}
    for i, j in edges:
        k = supplier_material_type[i]
        if k not in N_minus[j]:
            N_minus[j].append(k)
        if j not in N_plus[i]:
            N_plus[i].append(j)
        P[j].setdefault(k, []).append(i)

    return {
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "edges": edges,
        "material_types": material_types,
        "supplier_material_type": supplier_material_type,
        "f": {n["node_id"]: float(n["margin_usd_per_unit"]) for n in nodes if int(n["tier"]) == 1},
        "s": {n["node_id"]: int(n["on_hand_units"]) for n in nodes},
        "d": {n["node_id"]: int(round(float(n["demand_per_week"]))) for n in nodes if int(n["tier"]) == 1},
        "c": {n["node_id"]: int(n["capacity_per_week"]) for n in nodes},
        "r": {j: {k: 1 for k in ks} for j, ks in N_minus.items()},
        "N_minus": N_minus,
        "N_plus": N_plus,
        "P": P,
    }


def _var_values(model, name):
    var = getattr(model, name)
    return {idx: pyo.value(var[idx]) for idx in var}


def run_scenario(dataset: dict, disrupted: list[str], recovery_weeks: float) -> dict:
    """Solve the network with and without the disruption and summarise the business impact."""
    base = build_and_solve_ttr(dataset, [], recovery_weeks, True)
    hit = build_and_solve_ttr(dataset, disrupted, recovery_weeks, True)
    tts = float(build_and_solve_tts(dataset, disrupted, horizon=TTS_HORIZON_WEEKS)["tts"].values[0])

    m_base, m_hit = base["model"].values[0], hit["model"].values[0]
    u_base, u_hit = _var_values(m_base, "u"), _var_values(m_hit, "u")
    lost = _var_values(m_hit, "l")

    products = []
    for j in dataset["tier1"]:
        lost_cases = round(lost.get(j, 0.0))
        products.append({
            "product_id": j,
            "lost_cases": lost_cases,
            "lost_margin_usd": round(lost_cases * dataset["f"][j], 2),
            "planned_cases": round(u_base.get(j, 0.0)),
            "disrupted_plan_cases": round(u_hit.get(j, 0.0)),
        })

    # Production changes upstream of the finished goods (rebalancing the plan)
    rebalancing = []
    for node in dataset["tier2"] + dataset["tier3"]:
        before, after = round(u_base.get(node, 0.0)), round(u_hit.get(node, 0.0))
        if before != after:
            rebalancing.append({"node_id": node, "planned_units": before, "disrupted_plan_units": after,
                                "change_units": after - before})
    rebalancing.sort(key=lambda r: -abs(r["change_units"]))

    lost_margin = float(hit["lost_profit"].values[0])
    tts_val = round(tts, 2)
    return {
        "disrupted_node_ids": list(disrupted),
        "recovery_weeks": recovery_weeks,
        "solver_status": str(hit["termination_condition"].values[0]),
        "lost_margin_usd": round(lost_margin, 2),
        "time_to_survive_weeks": tts_val,
        "survives_horizon": tts_val >= TTS_HORIZON_WEEKS - 1e-6,
        "exposure_gap_weeks": round(max(recovery_weeks - tts_val, 0.0), 2),
        "product_impact": products,
        "plan_rebalancing": rebalancing,
    }

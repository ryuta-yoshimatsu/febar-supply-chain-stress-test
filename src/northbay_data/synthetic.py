"""Synthetic source-system extracts for NorthBay Foods, a fictional snacks & beverages manufacturer.

The network is hand-designed so that it contains the kinds of exposure a real CPG
supply chain has (single-sourced co-packers, a shared sweetener base, one PET bottle
supplier feeding two brands), while all quantities are generated with a fixed seed.

Units: one time period = one week; volumes are in cases (finished goods) or
case-equivalents (one unit of an input material is consumed per case produced).
"""
import csv
import io
import json
import random
from datetime import date, timedelta

SEED = 2026

# ---------------------------------------------------------------------------
# Network design
# ---------------------------------------------------------------------------
# Tier 1: finished-goods plants (one SKU family each)
PRODUCTS = [
    # id,   product,                    brand,        category,   plant,                city,           state, cases/wk, $ margin/case, $ price/case
    ("FG01", "Kettle Chips 8oz",         "Crunch Co.", "Snacks",   "Fresno Snacks Plant", "Fresno",       "CA", 60000, 6.40, 21.00),
    ("FG02", "Morning Oats Cereal 18oz", "Morning Oats", "Cereal", "Cedar Rapids Plant",  "Cedar Rapids", "IA", 45000, 7.20, 28.50),
    ("FG03", "SunValley Orange Drink 1L", "SunValley", "Beverages", "Lakeland Bottling",  "Lakeland",     "FL", 35000, 5.10, 18.00),
    ("FG04", "Fizz Cola 2L",             "Fizz",       "Beverages", "Atlanta Bottling",    "Atlanta",      "GA", 80000, 3.80, 14.50),
    ("FG05", "Trail Granola Bar 6ct",    "Trail Mix Co.", "Snacks", "Battle Creek Plant",  "Battle Creek", "MI", 30000, 8.40, 24.00),
]

# Materials: Tier-2 intermediates and Tier-3 raw materials
MATERIALS = [
    # id,        name,                              tier, unit
    ("M-SEAS",   "Seasoning & flavor blends",       2, "case-eq"),
    ("M-PET",    "PET bottles & preforms",          2, "case-eq"),
    ("M-FILM",   "Flexible packaging film",         2, "case-eq"),
    ("M-SWEET",  "Liquid sweetener & syrup base",   2, "case-eq"),
    ("M-CARTON", "Folding cartons & corrugate",     2, "case-eq"),
    ("R-SPICE",  "Spices & dried herbs",            3, "case-eq"),
    ("R-OIL",    "Natural flavor oils",             3, "case-eq"),
    ("R-RESIN",  "PET resin",                       3, "case-eq"),
    ("R-BOPP",   "BOPP / PE film resin",            3, "case-eq"),
    ("R-CORN",   "Yellow dent corn (HFCS)",         3, "case-eq"),
    ("R-CANE",   "Raw cane sugar",                  3, "case-eq"),
    ("R-PULP",   "Kraft & recycled fiber",          3, "case-eq"),
]

# Suppliers: Tier 2 (co-packers / converters) and Tier 3 (raw material suppliers)
SUPPLIERS = [
    # id,     name,                       tier, material,   city,            state/country,  recovery wks, disruption profile
    ("S201", "FlavorCraft Blends",        2, "M-SEAS",   "Chicago",       "IL", 10, "Blending-line fire"),
    ("S202", "SpiceWorks Ingredients",    2, "M-SEAS",   "Kansas City",   "MO", 6,  "Allergen contamination recall"),
    ("S203", "ClearPak Bottling",         2, "M-PET",    "Atlanta",       "GA", 8,  "Blow-molding line failure"),
    ("S204", "PolyForm Containers",       2, "M-PET",    "Dallas",        "TX", 6,  "Winter storm power loss"),
    ("S205", "FlexiWrap Films",           2, "M-FILM",   "Green Bay",     "WI", 5,  "Printing press breakdown"),
    ("S206", "BarrierFilm Co.",           2, "M-FILM",   "Neenah",        "WI", 7,  "Labor strike"),
    ("S207", "Midwest Sweeteners",        2, "M-SWEET",  "Decatur",       "IL", 9,  "Refinery explosion"),
    ("S208", "GulfCane Syrups",           2, "M-SWEET",  "New Orleans",   "LA", 6,  "Hurricane"),
    ("S209", "BoxCraft Packaging",        2, "M-CARTON", "Memphis",       "TN", 4,  "Cyber attack on MES"),
    ("S210", "NorthPine Paperboard",      2, "M-CARTON", "Portland",      "OR", 5,  "Wildfire evacuation"),
    ("R301", "Kerala Spice Traders",      3, "R-SPICE",  "Kochi",         "IN", 12, "Monsoon flooding"),
    ("R302", "Andes Botanicals",          3, "R-SPICE",  "Lima",          "PE", 8,  "Port strike"),
    ("R303", "Gulf Coast Resins",         3, "R-RESIN",  "Houston",       "TX", 10, "Hurricane"),
    ("R304", "Monterrey Polymers",        3, "R-RESIN",  "Monterrey",     "MX", 6,  "Border customs delay"),
    ("R305", "Great Lakes Polyolefins",   3, "R-BOPP",   "Sarnia",        "ON", 5,  "Cracker unit outage"),
    ("R306", "Prairie Plastics",          3, "R-BOPP",   "Joliet",        "IL", 4,  "Feedstock shortage"),
    ("R307", "Iowa Corn Growers Co-op",   3, "R-CORN",   "Ames",          "IA", 9,  "Drought crop failure"),
    ("R308", "Illinois Grain Partners",   3, "R-CORN",   "Peoria",        "IL", 7,  "River barge disruption"),
    ("R309", "Bayou Sugar Mill",          3, "R-CANE",   "Thibodaux",     "LA", 8,  "Hurricane"),
    ("R310", "Everglades Cane Growers",   3, "R-CANE",   "Clewiston",     "FL", 6,  "Hurricane"),
    ("R311", "Southern Kraft Mills",      3, "R-PULP",   "Savannah",      "GA", 5,  "Boiler failure"),
    ("R312", "Cascade Fiber",             3, "R-PULP",   "Longview",      "WA", 4,  "Wildfire smoke shutdown"),
    ("R313", "Citrus Essence Labs",       3, "R-OIL",    "Winter Haven",  "FL", 7,  "Citrus greening crop loss"),
    ("R314", "Mediterranean Aromatics",   3, "R-OIL",    "Valencia",      "ES", 9,  "Shipping lane disruption"),
]

# Supply links (source -> target): Tier 2 -> finished goods
LINKS_T2_T1 = [
    ("S201", "FG01"),                    # chips seasoning: single source
    ("S205", "FG01"), ("S206", "FG01"),  # chips film: dual source
    ("S209", "FG01"),                    # chips cartons: single source
    ("S207", "FG02"),                    # cereal sweetener: single source
    ("S205", "FG02"),                    # cereal film: single source
    ("S209", "FG02"), ("S210", "FG02"),
    ("S203", "FG03"),                    # orange drink bottles: single source
    ("S208", "FG03"),                    # orange drink sweetener: single source
    ("S210", "FG03"),
    ("S203", "FG04"), ("S204", "FG04"),  # cola bottles: dual source
    ("S207", "FG04"), ("S208", "FG04"),  # cola sweetener: dual source
    ("S209", "FG04"),
    ("S207", "FG05"),
    ("S206", "FG05"),
    ("S210", "FG05"),
    ("S201", "FG05"), ("S202", "FG05"),
]

# Supply links: Tier 3 -> Tier 2
LINKS_T3_T2 = [
    ("R301", "S201"), ("R313", "S201"),
    ("R302", "S202"), ("R314", "S202"),
    ("R303", "S203"),
    ("R304", "S204"),
    ("R305", "S205"),
    ("R306", "S206"),
    ("R307", "S207"), ("R308", "S207"),
    ("R309", "S208"), ("R310", "S208"),
    ("R311", "S209"),
    ("R312", "S210"),
]

# Named multi-node scenarios used in the portfolio stress test
SCENARIOS = [
    ("SC-GULF-HURRICANE", "Gulf Coast hurricane", ["S208", "R303", "R309"], 8),
    ("SC-PET-SHORTAGE", "North American PET resin shortage", ["R303", "R304"], 6),
    ("SC-MIDWEST-DROUGHT", "Midwest drought hits corn sweetener", ["R307", "R308"], 9),
    ("SC-WISCONSIN-FILM", "Wisconsin film converters shut down", ["S205", "S206"], 5),
]


def _material_of(node_id):
    for s in SUPPLIERS:
        if s[0] == node_id:
            return s[3]
    raise KeyError(node_id)


def generate(as_of: date = date(2026, 11, 2)):
    """Return a dict of {relative_path: file_content} representing raw source-system extracts."""
    rng = random.Random(SEED)
    files = {}

    demand = {p[0]: p[7] for p in PRODUCTS}

    # Weekly requirement each supplier carries in the normal plan (demand split across alternates)
    def requirement(node_id, depth_links, downstream_req):
        total = 0.0
        material = _material_of(node_id)
        for src, tgt in depth_links:
            if src != node_id:
                continue
            alternates = [s for s, t in depth_links if t == tgt and _material_of(s) == material]
            total += downstream_req[tgt] / len(alternates)
        return total

    req_t2 = {s[0]: requirement(s[0], LINKS_T2_T1, demand) for s in SUPPLIERS if s[2] == 2}
    req_t3 = {s[0]: requirement(s[0], LINKS_T3_T2, req_t2) for s in SUPPLIERS if s[2] == 3}
    req = {**req_t2, **req_t3}

    # --- ERP: product master with plant capacity
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["product_id", "product_name", "brand", "category", "plant_name", "plant_city", "plant_state",
                "capacity_cases_per_week", "margin_usd_per_case", "price_usd_per_case", "updated_at"])
    for p in PRODUCTS:
        cap = int(p[7] * rng.uniform(1.10, 1.30))
        w.writerow([p[0], p[1], p[2], p[3], p[4], p[5], p[6], cap, p[8], p[9], as_of.isoformat()])
    files["erp/products/products_20261102.csv"] = buf.getvalue()

    # --- SRM: supplier master (with a duplicated record from a re-sent extract)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["supplier_id", "supplier_name", "tier", "material_id", "city", "region",
                "capacity_units_per_week", "expected_recovery_weeks", "disruption_profile", "updated_at"])
    rows = []
    for s in SUPPLIERS:
        cap = int(req[s[0]] * rng.uniform(1.25, 1.75))
        rows.append([s[0], s[1], s[2], s[3], s[4], s[5], cap, s[6], s[7], as_of.isoformat()])
    rows.append(rows[6])  # duplicate S207 row -> deduplicated in silver
    for r in rows:
        w.writerow(r)
    files["srm/suppliers/suppliers_20261102.csv"] = buf.getvalue()

    # --- SRM: material master
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["material_id", "material_name", "tier", "unit"])
    for m in MATERIALS:
        w.writerow(m)
    files["srm/materials/materials.csv"] = buf.getvalue()

    # --- PLM: approved supply links (JSON lines), including one link to an unknown supplier
    lines = []
    for src, tgt in LINKS_T2_T1 + LINKS_T3_T2:
        lines.append(json.dumps({"source_id": src, "target_id": tgt, "material_id": _material_of(src),
                                 "approved": True, "approved_on": "2025-03-01"}))
    lines.append(json.dumps({"source_id": "S299", "target_id": "FG02", "material_id": "M-FILM",
                             "approved": True, "approved_on": "2026-10-30"}))  # supplier not in SRM -> dropped
    files["plm/supply_links/supply_links.json"] = "\n".join(lines) + "\n"

    # --- WMS: weekly on-hand inventory snapshots for every node (four weeks, latest wins)
    node_weeks_of_cover = {p[0]: rng.uniform(0.9, 1.6) for p in PRODUCTS}
    node_weeks_of_cover.update({s[0]: rng.uniform(1.0, 2.5) for s in SUPPLIERS})
    for k in range(4):
        snap = as_of - timedelta(weeks=3 - k)
        recs = []
        for p in PRODUCTS:
            qty = int(demand[p[0]] * node_weeks_of_cover[p[0]] * rng.uniform(0.92, 1.08))
            recs.append({"node_id": p[0], "snapshot_date": snap.isoformat(), "on_hand_units": qty})
        for s in SUPPLIERS:
            qty = int(req[s[0]] * node_weeks_of_cover[s[0]] * rng.uniform(0.92, 1.08))
            recs.append({"node_id": s[0], "snapshot_date": snap.isoformat(), "on_hand_units": qty})
        if k == 3:
            recs.append({"node_id": "S205", "snapshot_date": snap.isoformat(), "on_hand_units": -1200})  # bad scan
        files[f"wms/inventory/inventory_{snap.isoformat()}.json"] = "\n".join(json.dumps(r) for r in recs) + "\n"

    # --- APS: 13-week demand forecast per product
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["product_id", "week_start", "forecast_cases"])
    for p in PRODUCTS:
        for k in range(13):
            wk = as_of + timedelta(weeks=k)
            season = 1.0 + 0.08 * (1 if p[3] == "Beverages" and k > 8 else 0)
            w.writerow([p[0], wk.isoformat(), int(demand[p[0]] * season * rng.uniform(0.95, 1.05))])
    files["aps/demand_forecast/forecast_20261102.csv"] = buf.getvalue()

    # --- Risk: named multi-node scenarios curated by the supply chain risk team
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["scenario_id", "scenario_name", "disrupted_node_ids", "recovery_weeks"])
    for sc in SCENARIOS:
        w.writerow([sc[0], sc[1], ";".join(sc[2]), sc[3]])
    files["risk/scenarios/scenarios.csv"] = buf.getvalue()

    return files

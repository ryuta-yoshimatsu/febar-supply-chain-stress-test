"""Multi-tier time-to-recover (TTR) and time-to-survive (TTS) optimization models.

Adapted from the Databricks supply-chain-stress-test solution accelerator (scripts/utils.py).
"""
import pandas as pd


def build_and_solve_ttr(dataset: dict, disrupted: list[str], ttr: float, return_model: bool = False) -> pd.DataFrame:
    import pandas as pd
    import pyomo.environ as pyo

    # Prepare your data
    r = {}
    for j, inner in dataset["r"].items():
        for k, val in inner.items():
            r[(k, j)] = val

    P = {}
    for j, inner in dataset["P"].items():
        for k, I in inner.items():
            P[(j, k)] = I
    
    data = {
        'V': dataset['tier1'],  # product nodes
        'D': dataset['tier1'] + dataset['tier2'],  # all BUT leaf nodes
        'U': dataset['tier2'] + dataset['tier3'],  # all BUT product nodes
        'K': dataset['material_types'],  # material types  (k ∈ 𝒩⁻(j))
        'S': disrupted,  # disrupted nodes in scenario n
        'N_minus': dataset['N_minus'],  # materials required to produce node j: dict  j ↦ list_of_k   (𝒩⁻(j))
        'N_plus': dataset['N_plus'],    # child nodes of node i: dict  i ↦ list_of_j   (𝒩⁺(i))
        'P': P,             # parent nodes of node j of material type k: dict  (j,k) ↦ list_of_i  (𝒫_{jk})
        'f': dataset['f'],  # profit margin of 1 unit of j
        's': dataset['s'],  # inventory of i
        't': ttr,           # TTR for disruption scenario n (a scalar)
        'd': dataset['d'],  # demand for j per time unit
        'c': dataset['c'],  # plant capacity per time unit
        'r': r,             # number of material type k needed for one unit of j 
    }

    # Build the ConcreteModel
    m = pyo.ConcreteModel()

    # Sets
    m.V = pyo.Set(initialize=data['V'])
    m.D = pyo.Set(initialize=data['D'])
    m.U = pyo.Set(initialize=data['U'])
    m.K = pyo.Set(initialize=data['K'])
    m.S = pyo.Set(initialize=data['S'])

    m.N_minus = pyo.Set(m.D, initialize=lambda mdl, j: data['N_minus'][j])
    m.N_plus = pyo.Set(m.U, initialize=lambda mdl, i: data['N_plus'][i])

    # Handy union of *all* nodes that may carry production volume
    m.NODES = pyo.Set(initialize=list(
        set(data['V']) | set(data['U'])
    ))

    # 𝒫_{jk} as map (j,k) → list_of_i
    m.P = pyo.Set(dimen=3, initialize=[
        (i, j, k)
        for (j, k), I in data['P'].items()
        for i in I
    ])

    # Parameters
    m.f = pyo.Param(m.V, initialize=data['f'], within=pyo.NonNegativeReals)
    m.s = pyo.Param(m.NODES, initialize=data['s'], within=pyo.NonNegativeIntegers)
    m.t = pyo.Param(initialize=data['t'], within=pyo.PositiveReals)
    m.d = pyo.Param(m.V, initialize=data['d'], within=pyo.NonNegativeIntegers)
    m.c = pyo.Param(m.NODES, initialize=data['c'], within=pyo.NonNegativeIntegers)
    m.r = pyo.Param(m.K, m.NODES, initialize=data['r'], within=pyo.NonNegativeReals)

    # Decision variables
    m.u = pyo.Var(m.NODES, domain=pyo.NonNegativeIntegers)  # production quantity of node i during time t
    m.l = pyo.Var(m.V, domain=pyo.NonNegativeIntegers)  # lost volume of product j during time t
    m.y_index = pyo.Set(within=m.U * m.NODES, initialize=lambda mdl: [
        (i, j) for i in mdl.U for j in mdl.N_plus[i]
    ]) # y is only needed for (i,j) pairs that actually make sense
    m.y = pyo.Var(m.y_index, domain=pyo.NonNegativeIntegers)  # allocation of upstream node i to downstream node j during time t

    # Objective
    def obj_rule(mdl):
        return sum(mdl.f[j] * mdl.l[j] for j in mdl.V)
    m.OBJ = pyo.Objective(rule=obj_rule, sense=pyo.minimize)

    # Constraints
    # u_j − Σ_{i∈𝒫_{jk}} y_ij  ≤ 0,     ∀j∈𝒟, ∀k∈𝒩⁻(j)
    def bom_production_rule(mdl, j, k):
        rhs = sum(mdl.y[i, j] / mdl.r[k, j] for i in data['P'][(j, k)])
        return mdl.u[j] - rhs <= 0
    m.BomProduction = pyo.Constraint([(j, k) for j in m.D for k in m.N_minus[j]], rule=bom_production_rule)

    # Σ_{j∈𝒩⁺(i)} y_ij − u_i ≤ s_i,     ∀ i∈𝒰
    def flow_balance_rule(mdl, i):
        return sum(mdl.y[i, j] for j in mdl.N_plus[i]) - mdl.u[i] <= mdl.s[i]
    m.FlowBalance = pyo.Constraint(m.U, rule=flow_balance_rule)

    # u_j = 0,                           ∀ j∈𝒮⁽ⁿ⁾
    m.Disrupted = pyo.Constraint(m.S, rule=lambda m, j: m.u[j] == 0)

    # l_j + u_j + s_j ≥ d_j · t⁽ⁿ⁾,      ∀ j∈𝒱
    def demand_rule(mdl, j):
        return mdl.l[j] + mdl.u[j] + mdl.s[j] >= mdl.d[j] * mdl.t
    m.Demand = pyo.Constraint(m.V, rule=demand_rule)

    # u_j ≤ c_j · t⁽ⁿ⁾,        ∀ j∈NODES
    def capacity_rule(mdl, j):
        return mdl.u[j] <= mdl.c[j] * mdl.t
    m.Capacity = pyo.Constraint(m.NODES, rule=capacity_rule)

    # Solve
    solver = pyo.SolverFactory("highs")  # choose any LP/MIP solver that Pyomo can see (HiGHS, CBC, Gurobi, CPLEX, …)
    result = solver.solve(m, tee=False)

    if return_model:
        return pd.DataFrame(
        [[
            disrupted, 
            ttr, 
            result.solver.termination_condition, 
            pyo.value(m.OBJ), 
            m,
        ]], 
        columns=[
            "disrupted", 
            "ttr", 
            "termination_condition", 
            "lost_profit", 
            "model",
            ],
        )
    else:
        return pd.DataFrame(
            [[
                disrupted, 
                ttr, 
                result.solver.termination_condition, 
                pyo.value(m.OBJ),
            ]], 
            columns=[
                "disrupted", 
                "ttr", 
                "termination_condition", 
                "lost_profit", 
                ],
            )


def build_and_solve_tts(dataset: dict, disrupted: list[str], return_model: bool = False, horizon: float = 52) -> pd.DataFrame:
    import pandas as pd
    import pyomo.environ as pyo

    # Prepare your data
    r = {}
    for j, inner in dataset["r"].items():
        for k, val in inner.items():
            r[(k, j)] = val

    P = {}
    for j, inner in dataset["P"].items():
        for k, I in inner.items():
            P[(j, k)] = I

    data = {
        'V': dataset['tier1'],  # product nodes
        'D': dataset['tier1'] + dataset['tier2'],  # all BUT leaf nodes
        'U': dataset['tier2'] + dataset['tier3'],  # all BUT product nodes
        'K': dataset['material_types'],  # material types  (k ∈ 𝒩⁻(j))
        'S': disrupted,  # disrupted nodes in scenario n
        'N_minus': dataset['N_minus'],  # materials required to produce node j: dict  j ↦ list_of_k   (𝒩⁻(j))
        'N_plus': dataset['N_plus'],  # child nodes of node i: dict  i ↦ list_of_j   (𝒩⁺(i))
        'P': P,  # parent nodes of node j of material type k: dict  (j,k) ↦ list_of_i  (𝒫_{jk})
        's': dataset['s'],  # inventory of i
        'd': dataset['d'],  # demand for j per time unit
        'c': dataset['c'],  # plant capacity per time unit
        'r': r,  # number of material type k needed for one unit of j 
    }

    # Build the ConcreteModel
    m = pyo.ConcreteModel()

    # Sets
    m.V = pyo.Set(initialize=data['V'])
    m.D = pyo.Set(initialize=data['D'])
    m.U = pyo.Set(initialize=data['U'])
    m.K = pyo.Set(initialize=data['K'])
    m.S = pyo.Set(initialize=data['S'])

    m.N_minus = pyo.Set(m.D, initialize=lambda mdl, j: data['N_minus'][j])
    m.N_plus = pyo.Set(m.U, initialize=lambda mdl, i: data['N_plus'][i])

    # Handy union of *all* nodes that may carry production volume
    m.NODES = pyo.Set(initialize=list(
        set(data['V']) | set(data['U'])
    ))

    # 𝒫_{jk} as map (j,k) → list_of_i
    m.P = pyo.Set(dimen=3, initialize=[
        (i, j, k)
        for (j, k), I in data['P'].items()
        for i in I
    ])

    # Parameters
    m.s = pyo.Param(m.NODES, initialize=data['s'], within=pyo.NonNegativeIntegers)
    m.d = pyo.Param(m.V, initialize=data['d'], within=pyo.NonNegativeIntegers)
    m.c = pyo.Param(m.NODES, initialize=data['c'], within=pyo.NonNegativeIntegers)
    m.r = pyo.Param(m.K, m.NODES, initialize=data['r'], within=pyo.NonNegativeReals)

    # Decision variables
    m.u = pyo.Var(m.NODES, domain=pyo.NonNegativeIntegers)  # production quantity of node i during time t
    m.y_index = pyo.Set(within=m.U * m.NODES, initialize=lambda mdl: [
        (i, j) for i in mdl.U for j in mdl.N_plus[i]
    ]) # y is only needed for (i,j) pairs that actually make sense
    m.y = pyo.Var(m.y_index, domain=pyo.NonNegativeIntegers) # allocation of upstream node i to downstream node j during time t
    m.t = pyo.Var(domain=pyo.PositiveReals, bounds=(0, horizon))  # time to survive, capped at the planning horizon (unbounded otherwise)
    
    # Objective
    def obj_rule(mdl):
        return mdl.t
    m.OBJ = pyo.Objective(rule=obj_rule, sense=pyo.maximize)

    # Constraints
    # u_j − Σ_{i∈𝒫_{jk}} y_ij  ≤ 0,     ∀j∈𝒟, ∀k∈𝒩⁻(j)
    def bom_production_rule(mdl, j, k):
        rhs = sum(mdl.y[i, j] / mdl.r[k, j] for i in data['P'][(j, k)])
        return mdl.u[j] - rhs <= 0
    m.BomProduction = pyo.Constraint([(j, k) for j in m.D for k in m.N_minus[j]], rule=bom_production_rule)

    # Σ_{j∈𝒩⁺(i)} y_ij − u_i ≤ s_i,     ∀ i∈𝒰
    def flow_balance_rule(mdl, i):
        return sum(mdl.y[i, j] for j in mdl.N_plus[i]) - mdl.u[i] <= mdl.s[i]
    m.FlowBalance = pyo.Constraint(m.U, rule=flow_balance_rule)

    # u_j = 0,                           ∀ j∈𝒮⁽ⁿ⁾
    m.Disrupted = pyo.Constraint(m.S, rule=lambda m, j: m.u[j] == 0)

    # u_j + s_j ≥ d_j · t⁽ⁿ⁾,      ∀ j∈𝒱
    def demand_rule(mdl, j):
        return mdl.u[j] + mdl.s[j] >= mdl.d[j] * mdl.t
    m.Demand = pyo.Constraint(m.V, rule=demand_rule)

    # u_j ≤ c_j · t⁽ⁿ⁾,        ∀ j∈NODES
    def capacity_rule(mdl, j):
        return mdl.u[j] <= mdl.c[j] * mdl.t
    m.Capacity = pyo.Constraint(m.NODES, rule=capacity_rule)

    # Solve
    solver = pyo.SolverFactory("highs")  # choose any LP/MIP solver that Pyomo can see (HiGHS, CBC, Gurobi, CPLEX, …)
    result = solver.solve(m, tee=False)

    if return_model:
        return pd.DataFrame(
        [[
            disrupted,
            result.solver.termination_condition, 
            pyo.value(m.OBJ), 
            m,
        ]], 
        columns=[
            "disrupted", 
            "termination_condition", 
            "tts", 
            "model",
            ],
        )
    else:
        return pd.DataFrame(
            [[
                disrupted, 
                result.solver.termination_condition, 
                pyo.value(m.OBJ),
            ]], 
            columns=[
                "disrupted", 
                "termination_condition", 
                "tts", 
                ],
            )
        

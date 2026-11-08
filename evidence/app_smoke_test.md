# Execution evidence: Databricks App smoke test

App `northbay-resilience` on workspace `adb-7405610715852579` (Azure), deployed with
`databricks bundle run northbay_resilience` (build + start: 1 min 31 s). Tested on 2026-11-08 at 09:47–09:49 UTC from a
signed-in browser session. The calls below were issued against the app's own API, and the responses are pasted verbatim.

## 1. `GET /api/overview`: risk overview served from Lakebase (`northbay_serving.*` synced tables)

```json
{"kpis": {"margin_at_risk_usd": 11490613.1, "revenue_at_risk_usd": 39784382, "exposed_suppliers": 11,
          "suppliers": 24, "single_sourced_inputs": 11, "annual_margin_usd": 75115392.3},
 "risk_ranking": "24 rows", "named_scenarios": "4 rows", "single_sourced": "11 rows"}
```

Rendered page (text of the first rows, as shown to the user):

```
Gross margin at risk  $11.5M   sum over single-supplier disruptions · 15.3% of annual gross margin
Revenue at risk $39.8M · Exposed suppliers 11 of 24 · Single-sourced inputs 11 · Annual gross margin $75.1M
Gross margin at risk by supplier: Midwest Sweeteners $3.0M · Kerala Spice Traders $2.8M · FlavorCraft Blends $2.4M · ...
Named disruption scenarios: Wisconsin film converters shut down 5.0 wk / 2.8 wk / $1.9M · Midwest drought ... $1.7M · ...
Supplier risk ranking: 1 Midwest Sweeteners S207 · Tier 2 | Liquid sweetener & syrup base | Refinery explosion | 9.0 wk | 3.6 wk | ⚠ Exposed 5.4 wk | $3.0M | Morning Oats Cereal 18oz, Trail Granola Bar 6ct
```

## 2. `POST /api/chat`: agent what-if streamed over server-sent events

Request: *"A hurricane takes out GulfCane Syrups, Gulf Coast Resins and Bayou Sugar Mill for 8 weeks. What is the impact and what should we do?"*

HTTP 200 in **47.2 s**. Tool status events streamed to the UI, in order:

1. `Asking Genie`: `ask_genie` (Genie space over gold tables) to resolve the supplier ids
2. `Reading the portfolio stress test (Lakebase)`: `get_risk_ranking`
3. `Re-optimizing the network for this disruption`: `run_disruption_scenario` (Pyomo + HiGHS on the live network)
4. `Looking up network nodes (Lakebase)`: `get_node_details`

The solver result ($562,871.70 margin lost, TTS 4.85 weeks) matches the batch stress test's named scenario
`SC-GULF-HURRICANE` exactly (see `executed_notebooks/02_stress_test.ipynb`).

Final answer (verbatim):

> ## Bottom line
> - **Gross margin lost:** about **$562.9K** over the 8-week outage.
> - **Exposure:** the network can cover the loss for **4.85 weeks** (TTS) against an **8-week** outage (TTR). That leaves a gap of **3.15 weeks**.
> - **Product hit:** only **SunValley Orange Drink 1L (FG03)** is affected. It loses **110,367 of 235,398 planned cases (about 47%)**. Kettle Chips, Morning Oats, Fizz Cola and Trail Granola are fully protected.
>
> ## Plan with vs. without the disruption
> | Node | Planned units | Disrupted plan |
> |---|---|---|
> | Gulf Coast Resins (R303) | 995,024 | 0 |
> | GulfCane Syrups (S208) | 668,630 | 0 |
> | Everglades Cane Growers (R310) | 521,984 | 0 |
> | ClearPak Bottling (S203) | 662,521 | 154,955 |
> | Bayou Sugar Mill (R309) | 412,720 | 0 |
>
> - ClearPak's output falls to 154,955 units. That equals the PET resin on hand at Gulf Coast Resins, so resin is what constrains Orange Drink bottles.
> - GulfCane is the single point of failure. It holds 125,031 units of syrup on hand and feeds both Orange Drink (FG03) and Fizz Cola (FG04).
>
> ## Recommended actions
> 1. **Lock in resin now.** Ask Monterrey Polymers (R304, PET resin) to supply extra volume. Its stress test shows a TTS of 52 weeks. Orange Drink bottles are the binding constraint, and 110,367 cases (about $563K) are at stake.
> 2. **Secure alternate syrup for Orange Drink.** Check whether Midwest Sweeteners (S207) can supply the same liquid sweetener and syrup base, and how much volume it has free. S207 is also the #1 risk in the portfolio, so don't lean on it without a capacity check.
> 3. **Pre-build Orange Drink inventory** before storm landfall. Each 10,000 cases protected is worth about $51K of gross margin. The gap is about 3 weeks, so target that much cover.
> 4. **Add bottle capacity.** Check whether PolyForm Containers (S204, PET bottles) can offset some of the ClearPak shortfall. Its stress test shows a TTS of 52 weeks.
> 5. **Allocate scarce syrup to higher-margin products if needed.** The model currently protects Fizz Cola and the other four products, so keep that allocation in place.

*(A middle section comparing standalone supplier results is omitted here for length.)*

## 3. `GET /api/scenarios`: what-if write-back to Lakebase (`app_state.scenario_runs`)

The app's run (first row) is written by the app service principal. The other rows were written by the evaluation notebook.

| created_at (UTC) | scenario_name | disrupted | TTR | TTS | margin lost |
|---|---|---|---:|---:|---:|
| 2026-11-08 09:48:36 | Gulf Coast hurricane - S208, R303, R309 - 8 weeks | S208, R303, R309 | 8 | 4.85 | $562,871.70 |
| 2026-11-08 08:49:01 | Gulf Coast hurricane: S208, R303, R309 down 8 weeks | S208, R303, R309 | 8 | 4.85 | $562,871.70 |
| 2026-11-08 08:49:01 | ClearPak Bottling (S203) down 4 weeks | S203 | 4 | 5.02 | $0.00 |
| 2026-11-08 08:49:00 | FlavorCraft Blends (S201) blending-line fire - 10 weeks | S201 | 10 | 3.81 | $2,418,816.00 |
| 2026-11-08 08:48:00 | Midwest Sweeteners refinery explosion - 9 weeks | S207 | 9 | 3.59 | $2,987,053.20 |

## 4. App logs (`databricks apps logs northbay-resilience`)

```
2026-11-08T08:57:38Z [BUILD] [INFO] Deployment successful (1m31s)
2026-11-08T08:57:41Z [APP] INFO:     Uvicorn running on http://0.0.0.0:8000
2026-11-08T09:47:35Z [APP] INFO:     "GET /api/overview HTTP/1.1" 200 OK
2026-11-08T09:48:04Z [APP] INFO:     "POST /api/chat HTTP/1.1" 200 OK
2026-11-08T09:48:06Z [APP] INFO:httpx:HTTP Request: POST https://adb-7405610715852579.19.azuredatabricks.net/serving-endpoints/chat/completions "HTTP/1.1 200 OK"
2026-11-08T09:48:36Z [APP] INFO:httpx:HTTP Request: POST .../serving-endpoints/chat/completions "HTTP/1.1 200 OK"
2026-11-08T09:48:51Z [APP] INFO:httpx:HTTP Request: POST .../serving-endpoints/chat/completions "HTTP/1.1 200 OK"
2026-11-08T09:49:01Z [APP] INFO:     "GET /api/scenarios HTTP/1.1" 200 OK
```

No errors, and no `could not persist chat message` warnings: chat turns were written to `app_state.chat_messages`.

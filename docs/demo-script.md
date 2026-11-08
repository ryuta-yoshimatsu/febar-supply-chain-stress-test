# Demo script: tell, show, tell (about 12 minutes)

**Audience:** Dana, VP Supply Chain (business, exec sponsor), and Sam, Director of Data & Analytics (technical).
Procurement is the domain owner who acts on the output.

## Tell (2 min): the problem and the outcome

> "Last year a single seasoning-line fire stopped Kettle Chips for weeks, and nobody could say in advance what it
> would cost or what to do. We modelled your whole network, 5 plants and 24 suppliers, and stress-tested every
> supplier. **$11.5M of gross margin, 15% of the year, is exposed, and 71% of it sits with three suppliers.** Two
> moves, a second sweetener source and a 6-week seasoning buffer, **cut that by 68%, for about $150k one-off.**
> And your planners can now ask 'what if' in plain English and get an optimized answer in about 30 seconds."

## Show (8 min)

1. **Risk overview tab** (Dana): hero number $11.5M, the top-10 bar chart, "11 of 24 exposed".
   Hover Midwest Sweeteners: TTR 9 weeks vs TTS 3.6 weeks, so we run dry 5.4 weeks before they're back.
   Scroll to *single-sourced inputs*: every plant has at least one.
2. **Ask the agent**: *"Midwest Sweeteners had a refinery explosion and expects 9 weeks to recover. What happens and what should we do?"*
   Point out the tool status lines (optimizer re-plans the network) and the answer: $2.99M margin, cereal stops,
   remaining sweetener goes to the higher-margin granola bars, actions.
3. Follow-up: *"Which finished goods depend on a single supplier for any input?"*, which is answered by Genie (show the SQL in the
   Genie space for Sam).
4. **Scenario log tab**: every what-if is persisted in Lakebase with who asked and the result, giving an audit trail for S&OP.
5. For Sam: the lineage graph in Catalog Explorer (files → bronze → silver → gold → Lakebase), the pipeline
   expectations (bad inventory scan dropped), the MLflow evaluation run, and the registered agent version.

## Tell (2 min): value and next step

> "Expected value is about $0.8M a year in protected margin with payback under 3 months, before counting faster response in a live event. Next step: a 6-week pilot on your real ERP and SRM data, through Lakeflow Connect to SAP, with your
> procurement team using the app in the monthly risk review."

## Objection handling

| Persona | Objection | Answer |
|---|---|---|
| Business | "Are these numbers real or AI-generated?" | Every impact number comes from the optimization model, not the LLM. The agent is instructed to use tool results only, and the evaluation checks tool routing on every question. The same scenario gives the same answer every time. |
| Business | "Our data isn't this clean." | The pipeline is built for that: duplicates, negative inventory and links to unknown suppliers are caught by expectations, and you can see the counts. |
| Business | "Why not just buy more inventory everywhere?" | The mitigation analysis shows where it pays: a seasoning buffer is worth 45%, dual-sourcing chips seasoning only 1% because the alternate has no capacity. We target the dollars. |
| Business | "Who owns this after the pilot?" | Procurement owns the actions, and supply chain analytics owns the data product (tags `nb_owner`). It runs as a scheduled job and an app, with no notebooks for end users. |
| Technical | "Can it scale beyond 30 nodes?" | The models are linear programs and solve in milliseconds here. The original accelerator runs 1,700-node networks with Ray on Databricks, and the code path is the same. |
| Technical | "Security: who can see what?" | The app runs as a service principal with SELECT on the gold tables only, CAN_RUN on Genie and CAN_QUERY on the LLM. Users need no direct grants. Every chat and scenario is logged with the user's email. |
| Technical | "Why Lakebase and not a SQL warehouse?" | We need millisecond lookups and transactional writes (scenario log, chat) for an interactive app. Lakebase synced tables keep Postgres in sync with gold, and it stays governed in UC. |
| Technical | "Why is the agent inside the app instead of a serving endpoint?" | It's one deployable with service-principal auth everywhere and fast iteration. The agent is still logged, evaluated and registered in UC, so moving it to Model Serving is one `agents.deploy` call. |
| Technical | "Hallucinations?" | The agent has four grounded tools. Genie writes governed SQL, the optimizer is deterministic, and off-topic questions are declined (tested in the eval set). |

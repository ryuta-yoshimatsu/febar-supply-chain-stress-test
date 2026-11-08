# AI as a force multiplier: how this build was produced

The build was produced in one working session with **Claude Code** (CLI, model Claude Opus) acting as a pair
engineer with direct access to the Databricks CLI, the GitHub CLI and a browser (Chrome DevTools MCP).
I set direction, scope and the business framing; the assistant did most of the typing, ran everything
against the workspace, and debugged from the logs.

## Workflow

1. **Gap analysis first, no code.** I asked the assistant to read my original solution accelerator
   (`databricks-industry-solutions/supply-chain-stress-test`) and map it against the FE Bar requirements.
   It found the missing stages (Lakeflow, Lakebase serving, Genie), the missing execution evidence
   (notebooks committed without outputs) and the generic framing.
2. **Clarifying questions before building.** The assistant asked about industry, repo name, agent hosting,
   Lakebase instance and the CPG scenario; I chose CPG snacks & beverages ("NorthBay Foods"), agent in the app,
   a new Lakebase instance.
3. **Reuse over rewrite.** The optimization models (`optimizer.py`) and the in-app agent pattern
   (`ChatOpenAI` over the workspace's OpenAI-compatible endpoint, service-principal auth, SSE streaming UI)
   were reused from my accelerator and from an app built earlier in the same session.
4. **Test locally, then on Databricks.** The synthetic network and optimizer were run locally first; this caught a
   real modelling issue (TTS unbounded when alternates fully cover a loss: the solver returned a degenerate
   ~1-week answer), fixed with a 52-week planning-horizon cap.
5. **Everything as code, deployed with a Databricks Asset Bundle**, executed as one job, and the executed
   notebooks exported back into the repo with their real outputs (`tools/export_run_notebooks.py`).

## Prompts and patterns that worked

| Pattern | Example |
|---|---|
| Ask for a gap analysis against an explicit rubric before any change | "Run the gap analysis and tell me how I can make the current codebase and the app aligned with the requirements of FEBAR. Do not change anything yet." |
| Force clarifying questions up front | "Ask any clarifying questions before you start implementing." |
| Let the assistant read logs and fix root causes, not symptoms | App build timeouts → pinned dependencies; `databricks-connect` incompatible with Apps' Python 3.11 → replaced `ChatDatabricks` with `ChatOpenAI` on the OpenAI-compatible endpoint; dev-mode schema prefixing → removed |
| Keep humans on irreversible / outward actions | The assistant paused for approval before modifying shared resources (Postgres roles, app config) and before publishing |
| Ground the agent, evaluate it | Tools return data, the system prompt forbids invented numbers, and `mlflow.genai.evaluate` checks tool routing, relevance, safety and business-readiness |

## Issues the assistant found and fixed during the build

* Apps runtime is Python 3.11, while `databricks-connect==17.3` needs 3.12; this removed `databricks-langchain` from the app.
* Unpinned requirements caused pip backtracking past the 10-minute app start limit; the dependency set is now fully pinned.
* Lakebase database catalogs need `CREATE CATALOG`; synced tables were placed in a standard UC schema instead.
* Bundle development mode prefixed schema names; the bundle targets the real schema names.
* TTS degeneracy (see `decisions-and-tradeoffs.md`, #2).

Conversation ID: provided in the FE Bar submission form.

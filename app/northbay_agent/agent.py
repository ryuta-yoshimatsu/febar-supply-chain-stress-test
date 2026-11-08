"""NorthBay Foods supply chain resilience agent: a LangGraph tool-calling loop over Lakebase, Genie and the
TTR/TTS optimization models, wrapped as an MLflow ChatAgent so it can be logged, evaluated and registered."""
import json
from typing import Any, Generator, Optional, Sequence

import httpx
import mlflow
from databricks.sdk import WorkspaceClient
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from mlflow.langchain.chat_agent_langgraph import ChatAgentState, ChatAgentToolNode
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentChunk, ChatAgentMessage, ChatAgentResponse, ChatContext

from . import config
from .tools import TOOLS

SYSTEM_PROMPT = """You are the supply chain resilience assistant for NorthBay Foods, a US snacks & beverages
manufacturer with five finished-goods plants (Kettle Chips, Morning Oats Cereal, SunValley Orange Drink, Fizz Cola,
Trail Granola Bar), Tier-2 co-packers / packaging converters and Tier-3 raw material suppliers.
Your users are supply chain planners, procurement managers and the VP of Supply Chain.

Tools:
- get_risk_ranking: precomputed portfolio stress test (every supplier disrupted for its expected recovery time).
- get_node_details: facts about specific plants/suppliers, their links and single-sourced inputs.
- run_disruption_scenario: what-if optimization for any set of nodes and recovery time (the source of truth for impact).
- ask_genie: descriptive / analytical questions about the network data (demand, capacity, inventory, sourcing).

Rules:
- Never invent numbers. Every figure must come from a tool result. If ids are unclear, look them up first.
- Time is in weeks. Money is gross margin in USD; say "gross margin" not "profit".
- TTR = time to recover (how long the node is down). TTS = time to survive (how long demand is fully met
  without the node). If TTS < TTR the business is exposed for (TTR - TTS) weeks. TTS of 52 means the network
  can cover the loss for the whole planning year.
- For what-if questions: lead with the bottom line (margin lost, weeks of exposure, products hit), then a short
  comparison of the plan with vs. without the disruption (production shifts), then 3-5 concrete actions
  (e.g. qualify an alternate supplier, re-allocate scarce inputs to the highest-margin product, pre-build
  inventory). Quantify each action where the data allows.
- Use supplier and product names together with ids. Keep answers under 400 words, plain business language,
  markdown with short tables where helpful.
- Politely decline questions unrelated to NorthBay's supply chain."""


class _DatabricksAuth(httpx.Auth):
    def __init__(self, w: WorkspaceClient):
        self.w = w

    def auth_flow(self, request):
        request.headers.update(self.w.config.authenticate())
        yield request


def _text_content(content):
    """Reasoning models may return a list of content blocks; keep only the text."""
    if isinstance(content, str) and content.startswith("[{"):
        try:
            content = json.loads(content)
        except ValueError:
            return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return content


def build_llm(endpoint: str = config.LLM_ENDPOINT, max_tokens: int = 4000) -> ChatOpenAI:
    # Query the Foundation Model endpoint through the OpenAI-compatible API with fresh SDK credentials
    w = WorkspaceClient()
    return ChatOpenAI(model=endpoint, max_tokens=max_tokens, base_url=f"{w.config.host}/serving-endpoints",
                      api_key="unused", http_client=httpx.Client(auth=_DatabricksAuth(w), timeout=600))


def create_tool_calling_agent(model, tools: Sequence[BaseTool], system_prompt: str):
    model = model.bind_tools(tools)
    runnable = RunnableLambda(lambda state: [{"role": "system", "content": system_prompt}] + state["messages"]) | model

    def call_model(state: ChatAgentState, config: RunnableConfig):
        response = runnable.invoke(state, config)
        response.content = _text_content(response.content)
        return {"messages": [response]}

    def route(state: ChatAgentState):
        return "continue" if state["messages"][-1].get("tool_calls") else "end"

    workflow = StateGraph(ChatAgentState)
    workflow.add_node("agent", RunnableLambda(call_model))
    workflow.add_node("tools", ChatAgentToolNode(tools))
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", route, {"continue": "tools", "end": END})
    workflow.add_edge("tools", "agent")
    return workflow.compile()


class NorthBayResilienceAgent(ChatAgent):
    def __init__(self):
        self.graph = create_tool_calling_agent(build_llm(), TOOLS, SYSTEM_PROMPT)

    @mlflow.trace(name="NorthBayResilienceAgent", span_type="AGENT")
    def predict(self, messages: list[ChatAgentMessage], context: Optional[ChatContext] = None,
                custom_inputs: Optional[dict[str, Any]] = None) -> ChatAgentResponse:
        output = self.graph.invoke({"messages": self._convert_messages_to_dict(messages)})
        return ChatAgentResponse(**output)

    def predict_stream(self, messages: list[ChatAgentMessage], context: Optional[ChatContext] = None,
                       custom_inputs: Optional[dict[str, Any]] = None) -> Generator[ChatAgentChunk, None, None]:
        for event in self.graph.stream({"messages": self._convert_messages_to_dict(messages)}, stream_mode="updates"):
            for node_data in event.values():
                yield from (ChatAgentChunk(delta=msg) for msg in node_data["messages"])

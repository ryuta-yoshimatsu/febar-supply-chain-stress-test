"""MLflow models-from-code entry point for logging and registering the agent."""
import mlflow

from northbay_agent.agent import NorthBayResilienceAgent

mlflow.langchain.autolog()
mlflow.models.set_model(NorthBayResilienceAgent())

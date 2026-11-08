"""Ask the NorthBay Genie space a question and return its answer, generated SQL and result rows."""
from databricks.sdk import WorkspaceClient

from . import config

MAX_ROWS = 30


def ask_genie(question: str, space_id: str | None = None, w: WorkspaceClient | None = None) -> dict:
    w = w or WorkspaceClient()
    space_id = space_id or config.GENIE_SPACE_ID
    if not space_id:
        return {"error": "Genie space is not configured (NB_GENIE_SPACE_ID)."}

    msg = w.genie.start_conversation_and_wait(space_id, question)
    message_id = getattr(msg, "message_id", None) or msg.id
    out = {"question": question, "status": str(msg.status.value if msg.status else ""), "answer": [], "sql": None,
           "columns": [], "rows": []}
    for att in msg.attachments or []:
        if att.text and att.text.content:
            out["answer"].append(att.text.content)
        if att.query:
            out["sql"] = att.query.query
            if att.query.description:
                out["answer"].append(att.query.description)
            res = w.genie.get_message_attachment_query_result(space_id, msg.conversation_id, message_id,
                                                              att.attachment_id)
            sr = res.statement_response
            if sr and sr.manifest and sr.result:
                out["columns"] = [c.name for c in sr.manifest.schema.columns]
                out["rows"] = (sr.result.data_array or [])[:MAX_ROWS]
    out["answer"] = "\n".join(out["answer"])
    return out

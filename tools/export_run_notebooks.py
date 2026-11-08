"""Export the executed notebooks of a Databricks job run as .ipynb files with their outputs.

Usage: python tools/export_run_notebooks.py <cli-profile> <job-run-id> <output-dir>

Uses the Databricks CLI (`jobs get-run`, `jobs export-run`), decodes the notebook model embedded in each
exported run view and writes a Jupyter notebook whose cells carry the real outputs of that run, so the
execution evidence is readable as text in the repo.
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def cli(profile, *args):
    return json.loads(subprocess.check_output(["databricks", "-p", profile, *args, "-o", "json"]))


def text_of(result):
    """Flatten a Databricks command result into (stdout_text, html, error_text)."""
    if not result:
        return "", "", ""
    kind, data = result.get("type"), result.get("data")
    if kind == "listResults":
        parts = [text_of(r) for r in data or []]
        return ("".join(p[0] for p in parts), "".join(p[1] for p in parts), "".join(p[2] for p in parts))
    if kind in ("ansi", "text"):
        return ANSI.sub("", data or ""), "", ""
    if kind == "html":
        return "", data or "", ""
    if kind == "table":
        cols = [c["name"] for c in result.get("schema", [])]
        rows = [" | ".join(map(str, r)) for r in (data or [])[:100]]
        return " | ".join(cols) + "\n" + "\n".join(rows) + "\n", "", ""
    if kind == "error":
        return "", "", ANSI.sub("", (result.get("summary") or "") + "\n" + (result.get("cause") or ""))
    return "", "", ""


def to_ipynb(model, header):
    cells = [{"cell_type": "markdown", "metadata": {}, "source": header}]
    for cmd in sorted(model["commands"], key=lambda c: c.get("position", 0)):
        src = cmd.get("command", "")
        if src.lstrip().startswith("%md"):
            cells.append({"cell_type": "markdown", "metadata": {},
                          "source": re.sub(r"^\s*%md ?", "", src, count=1)})
            continue
        stdout, html, error = text_of(cmd.get("results"))
        outputs = []
        if stdout:
            outputs.append({"output_type": "stream", "name": "stdout", "text": stdout})
        if html:
            outputs.append({"output_type": "display_data", "metadata": {}, "data": {"text/html": html}})
        if error:
            outputs.append({"output_type": "error", "ename": "Error", "evalue": error.splitlines()[0][:300],
                            "traceback": error.splitlines()})
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "source": src,
                      "outputs": outputs})
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                         "language_info": {"name": "python"}}}


def main(profile, run_id, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    run = cli(profile, "jobs", "get-run", run_id)
    latest = {}  # repaired runs list every attempt; keep the most recent attempt of each task
    for task in run["tasks"]:
        if "notebook_task" in task and task["start_time"] >= latest.get(task["task_key"], {}).get("start_time", 0):
            latest[task["task_key"]] = task
    for task in sorted(latest.values(), key=lambda t: t["start_time"]):
        exported = cli(profile, "jobs", "export-run", str(task["run_id"]), "--views-to-export", "CODE")
        html = exported["views"][0]["content"]
        blob = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", html).group(1)
        model = json.loads(urllib.parse.unquote(base64.b64decode(blob).decode()))
        start = datetime.fromtimestamp(task["start_time"] / 1000, tz=timezone.utc)
        secs = (task.get("end_time", task["start_time"]) - task["start_time"]) / 1000
        header = (f"> **Executed output.** Exported from Databricks job `{run['run_name']}` run {run['run_id']}, "
                  f"task `{task['task_key']}` (task run {task['run_id']}), started {start:%Y-%m-%d %H:%M} UTC, "
                  f"duration {secs:.0f}s, result **{task['state'].get('result_state')}**, serverless compute.")
        name = os.path.basename(task["notebook_task"]["notebook_path"]).removesuffix(".py") + ".ipynb"
        with open(os.path.join(out_dir, name), "w") as fh:
            json.dump(to_ipynb(model, header), fh, indent=1)
        print("wrote", os.path.join(out_dir, name))


if __name__ == "__main__":
    main(*sys.argv[1:4])

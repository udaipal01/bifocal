from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from agent_workflow import WorkflowInput as TagsWorkflowInput, run_agent_workflow as _run_tags_workflow
from agent_email_comments import WorkflowInput as EmailWorkflowInput, run_agent_workflow as _run_email_workflow
from agent_tick_tie_workflow import WorkflowInput as TickTieWorkflowInput, run_workflow as _run_tick_tie_workflow


def _run_tags(email_text: str, original_doc: Dict[str, Any], revised_doc: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "original_doc": original_doc,
        "revised_doc": revised_doc,
    }
    wf_input = TagsWorkflowInput(input_as_text=json.dumps(payload))
    return asyncio.run(_run_tags_workflow(wf_input)) or {}


def _run_email_comments(email_text: str, original_doc: Dict[str, Any], revised_doc: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "email_text": email_text,
        "original_doc": original_doc,
        "revised_doc": revised_doc,
    }
    wf_input = EmailWorkflowInput(input_as_text=json.dumps(payload))
    return asyncio.run(_run_email_workflow(wf_input)) or {}


def _run_tick_tie(email_text: str, revised_doc: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "email_text": email_text,
        "revised_doc": revised_doc,
    }
    wf_input = TickTieWorkflowInput(input_as_text=json.dumps(payload))
    return asyncio.run(_run_tick_tie_workflow(wf_input)) or {}


def run_agent_workflow(
    email_text: str,
    original_doc: Dict[str, Any],
    revised_doc: Dict[str, Any],
    run_tick_tie: bool = False,
) -> Dict[str, Any]:
    tags_output = _run_tags(email_text, original_doc, revised_doc)
    email_output = _run_email_comments(email_text, original_doc, revised_doc)

    tick_output: Dict[str, Any] = {}
    if run_tick_tie:
        tick_output = _run_tick_tie(email_text, revised_doc)

    return {
        "tags": tags_output.get("comments", []),
        "email_comments": email_output.get("comments", []),
        "tick_tie": tick_output,
    }

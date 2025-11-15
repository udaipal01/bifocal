# agent_runner.py
#
# Bridge between the synchronous email bot and the async workflow export.

import asyncio
import json
from typing import Dict

from agent_workflow import WorkflowInput, run_agent_workflow as _run_workflow_impl


def run_agent_workflow(
    email_text: str,
    original_doc: Dict,
    revised_doc: Dict,
):
    """
    Package inputs to match WorkflowInput (single `input_as_text` field) and
    execute the async workflow runner inside this synchronous context.
    """
    workflow_input = {
        "input_as_text": json.dumps({
            "email_text": email_text,
            "original_doc": original_doc,
            "revised_doc": revised_doc,
        })
    }
    return asyncio.run(_run_workflow_impl(
        WorkflowInput(**workflow_input)
    ))

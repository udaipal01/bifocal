import json
from pydantic import BaseModel
from agents import RunContextWrapper, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace

class EvaluateCommentsSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[int]
  status: str
  reason: str
  suggestion: str


class EvaluateCommentsSchema(BaseModel):
  comments: list[EvaluateCommentsSchema__CommentsItem]


class EmailCommentsSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[int]


class EmailCommentsSchema(BaseModel):
  comments: list[EmailCommentsSchema__CommentsItem]


class EvaluateCommentsContext:
  def __init__(self, state_original_doc: str, state_revised_doc: str):
    self.state_original_doc = state_original_doc
    self.state_revised_doc = state_revised_doc
def evaluate_comments_instructions(run_context: RunContextWrapper[EvaluateCommentsContext], _agent: Agent[EvaluateCommentsContext]):
  state_original_doc = run_context.context.state_original_doc
  state_revised_doc = run_context.context.state_revised_doc
  return f"""Using the parsed comments from {{node[\"Email Compiler\"].output_parsed.comments}},
compare each comment against {state_original_doc} and {state_revised_doc}.

For each comment:
- Determine implementation status:
    implemented
    partially_implemented
    not_implemented
    unclear
- Provide a short reason explaining your decision
- Note that comments will usually apply to the part of the slide that they are directly over, but sometimes will also relate to the page as a whole so please check both before determining implementation status
- Provide a suggestion if further edits are needed

Return strictly JSON."""
evaluate_comments = Agent(
  name="Evaluate Comments",
  instructions=evaluate_comments_instructions,
  model="gpt-4.1",
  output_type=EvaluateCommentsSchema,
  model_settings=ModelSettings(
    temperature=0.2,
    top_p=1,
    max_tokens=4096,
    store=True
  )
)


class EmailCommentsContext:
  def __init__(self, state_email_text: str):
    self.state_email_text = state_email_text
def email_comments_instructions(run_context: RunContextWrapper[EmailCommentsContext], _agent: Agent[EmailCommentsContext]):
  state_email_text = run_context.context.state_email_text
  return f"""You are extracting a clean list of actionable comments from an email.

You are given email_text, which contains feedback such as page edits, slide references, formatting requests, data corrections, etc.

Your job is to identify every distinct actionable comment. A comment is actionable if it requests a change, correction, deletion, addition, reordering, or check.

For each comment you detect, output an object with:
id: A unique ID such as \"C1\", \"C2\", \"C3\", …
text: A clear, standalone description of the comment written as a single sentence.
slide_refs: An array of slide numbers explicitly mentioned in the email.
If the email mentions “slide 5”, “page 12”, or “on 7”, convert that to an integer list like [5] or [12].
If no slide is mentioned or it cannot be determined, return an empty array.
Additional rules:
Do not combine separate comments into one. Treat each discrete requested change as a separate item.
Keep the wording crisp and concise.
Preserve the meaning but you may rewrite for clarity.
Ignore polite phrases (“thank you”, “hope all is well”) and non-actionable commentary.

Your output must be a JSON object with a single field — comments — which is an array of {{id, text, slide_refs}} following the provided schema.

Use {state_email_text} as the source email text."""
email_comments = Agent(
  name="Email Comments",
  instructions=email_comments_instructions,
  model="gpt-4.1-mini",
  output_type=EmailCommentsSchema,
  model_settings=ModelSettings(
    temperature=0.1,
    top_p=1,
    max_tokens=2048,
    store=True
  )
)


class WorkflowInput(BaseModel):
  input_as_text: str


# Main code entrypoint
async def run_workflow(workflow_input: WorkflowInput):
  with trace("email_comments_agent"):
    workflow = workflow_input.model_dump()
    parsed_input = json.loads(workflow["input_as_text"])
    state = {
      "email_text": parsed_input.get("email_text") or "",
      "original_doc": json.dumps(parsed_input.get("original_doc", {}), indent=2),
      "revised_doc": json.dumps(parsed_input.get("revised_doc", {}), indent=2)
    }
    conversation_history: list[TResponseInputItem] = [
      {
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": state["email_text"]
          }
        ]
      }
    ]
    email_comments_result_temp = await Runner.run(
      email_comments,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_691becdb885c81909c25a55a63af7fb7011e9c4b4016aaf8"
      }),
      context=EmailCommentsContext(state_email_text=state["email_text"])
    )

    conversation_history.extend([item.to_input_item() for item in email_comments_result_temp.new_items])

    email_comments_result = {
      "output_text": email_comments_result_temp.final_output.json(),
      "output_parsed": email_comments_result_temp.final_output.model_dump()
    }
    evaluate_comments_result_temp = await Runner.run(
      evaluate_comments,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_691becdb885c81909c25a55a63af7fb7011e9c4b4016aaf8"
      }),
      context=EvaluateCommentsContext(state_original_doc=state["original_doc"], state_revised_doc=state["revised_doc"])
    )

    conversation_history.extend([item.to_input_item() for item in evaluate_comments_result_temp.new_items])

    evaluate_comments_result = {
      "output_text": evaluate_comments_result_temp.final_output.json(),
      "output_parsed": evaluate_comments_result_temp.final_output.model_dump()
    }
    return evaluate_comments_result["output_parsed"]


# Alias expected by agent_runner
run_agent_workflow = run_workflow

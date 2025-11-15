import json
from pydantic import BaseModel
from agents import RunContextWrapper, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace

class ExtractCommentsSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[int]
  status: str
  reason: str
  suggestion: str


class ExtractCommentsSchema(BaseModel):
  comments: list[ExtractCommentsSchema__CommentsItem]


class EvaluateCommentsSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[int]
  status: str
  reason: str
  suggestion: str


class EvaluateCommentsSchema(BaseModel):
  comments: list[EvaluateCommentsSchema__CommentsItem]


class ExtractCommentsContext:
  def __init__(self, state_email_text: str, state_original_doc: str):
    self.state_email_text = state_email_text
    self.state_original_doc = state_original_doc
def extract_comments_instructions(run_context: RunContextWrapper[ExtractCommentsContext], _agent: Agent[ExtractCommentsContext]):
  state_email_text = run_context.context.state_email_text
  state_original_doc = run_context.context.state_original_doc
  return f"""Please look through {state_email_text} and  {state_original_doc} and compile a thorough list of comments to be implemented. 

For each comment: 
- Give it a unique ID (C1, C2, …)
- Include the full comment text
- Infer slide numbers based on phrases like “page 5”, “slide 7”, or slide titles found in {state_original_doc}"""
extract_comments = Agent(
  name="Extract Comments",
  instructions=extract_comments_instructions,
  model="gpt-4.1",
  output_type=ExtractCommentsSchema,
  model_settings=ModelSettings(
    temperature=1,
    top_p=1,
    max_tokens=4096,
    store=True
  )
)


class EvaluateCommentsContext:
  def __init__(self, state_original_doc: str, state_revised_doc: str):
    self.state_original_doc = state_original_doc
    self.state_revised_doc = state_revised_doc
def evaluate_comments_instructions(run_context: RunContextWrapper[EvaluateCommentsContext], _agent: Agent[EvaluateCommentsContext]):
  state_original_doc = run_context.context.state_original_doc
  state_revised_doc = run_context.context.state_revised_doc
  return f"""Using the parsed comments from {{node[\"Extract Comments\"].comments}},
compare each comment against {state_original_doc} and {state_revised_doc}.

For each comment:
- Determine implementation status:
    implemented
    partially_implemented
    not_implemented
    unclear
- Provide a short reason explaining your decision
- Provide a suggestion if further edits are needed

Return strictly JSON."""
evaluate_comments = Agent(
  name="Evaluate Comments",
  instructions=evaluate_comments_instructions,
  model="gpt-4.1",
  output_type=EvaluateCommentsSchema,
  model_settings=ModelSettings(
    temperature=1,
    top_p=1,
    max_tokens=4096,
    store=True
  )
)


class WorkflowInput(BaseModel):
  input_as_text: str


# Main code entrypoint
async def run_agent_workflow(workflow_input: WorkflowInput):
  with trace("Bifocal_Agent"):
    state = {
      "email_text": None,
      "original_doc": None,
      "revised_doc": None
    }
    workflow = workflow_input.model_dump()
    input_payload = json.loads(workflow["input_as_text"])
    state["email_text"] = input_payload.get("email_text", "")
    state["original_doc"] = json.dumps(input_payload.get("original_doc", {}), indent=2)
    state["revised_doc"] = json.dumps(input_payload.get("revised_doc", {}), indent=2)
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
    extract_comments_result_temp = await Runner.run(
      extract_comments,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
      }),
      context=ExtractCommentsContext(state_email_text=state["email_text"], state_original_doc=state["original_doc"])
    )

    conversation_history.extend([item.to_input_item() for item in extract_comments_result_temp.new_items])

    extract_comments_result = {
      "output_text": extract_comments_result_temp.final_output.json(),
      "output_parsed": extract_comments_result_temp.final_output.model_dump()
    }
    evaluate_comments_result_temp = await Runner.run(
      evaluate_comments,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
      }),
      context=EvaluateCommentsContext(state_original_doc=state["original_doc"], state_revised_doc=state["revised_doc"])
    )

    conversation_history.extend([item.to_input_item() for item in evaluate_comments_result_temp.new_items])

    evaluate_comments_result = {
      "output_text": evaluate_comments_result_temp.final_output.json(),
      "output_parsed": evaluate_comments_result_temp.final_output.model_dump()
    }
    end_result = evaluate_comments_result["output_parsed"]
    return end_result

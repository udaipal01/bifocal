from pydantic import BaseModel
from agents import RunContextWrapper, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace

class ExtractCommentsSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[float]
  status: str | None = None
  reason: str | None = None
  suggestion: str | None = None


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


class MissedCommentsSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[float]
  status: str | None = None
  reason: str | None = None
  suggestion: str | None = None


class MissedCommentsSchema(BaseModel):
  comments: list[MissedCommentsSchema__CommentsItem]


class CommentFinderSchema(BaseModel):
  has_internal_comments: bool


class CommentCompilerSchema__CommentsItem(BaseModel):
  id: str
  text: str
  slide_refs: list[float]
  status: str | None = None
  reason: str | None = None
  suggestion: str | None = None


class CommentCompilerSchema(BaseModel):
  comments: list[CommentCompilerSchema__CommentsItem]


class ExtractCommentsContext:
  def __init__(self, state_original_doc: str):
    self.state_original_doc = state_original_doc
def extract_comments_instructions(run_context: RunContextWrapper[ExtractCommentsContext], _agent: Agent[ExtractCommentsContext]):
  state_original_doc = run_context.context.state_original_doc
  return f"""You are given only the original document (the slide deck).

Your job is to compile a thorough list of ALL comments embedded in the document itself
(e.g., callouts, shapes with revision text, TODOs, placeholders).

IMPORTANT:
- Ignore the email completely. Another agent already extracts comments from the email.
- Only use {state_original_doc} as your source of comments.

If there are multiple comments on the same slide in the document, treat them as fully unique comments; multiple comments will usually be shown in separate shapes or in a numbered list or separated by a period or comma. Keep in mind that if comments are left in shapes, they will correspond to the area right underneath the shape (for example if there is a shape with text \"change color to green\" over a chart with blue bars, the comment should be interpreted as changing the chart beneath it to green bars).

If a comment in the email and document are effectively the same, please only include it once. 

For each comment: 
- Give it a unique ID (C1, C2, …)
- Include the full comment text
- Infer slide numbers based on phrases like “page 5”, “slide 7”, or slide titles found in the document
- If the comment is just a name, exclude from our comments list"""
extract_comments = Agent(
  name="Extract Comments",
  instructions=extract_comments_instructions,
  model="gpt-4.1",
  output_type=ExtractCommentsSchema,
  model_settings=ModelSettings(
    temperature=0.2,
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
  return f"""Using the parsed comments from {{node[\"Comment Compiler\"].output_parsed.comments}},
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


class MissedCommentsContext:
  def __init__(self, state_original_doc: str):
    self.state_original_doc = state_original_doc
def missed_comments_instructions(run_context: RunContextWrapper[MissedCommentsContext], _agent: Agent[MissedCommentsContext]):
  state_original_doc = run_context.context.state_original_doc
  return f"""Treat {state_original_doc} as the original document and {{node[\"Extract Comments\"].output_parsed.comments}} as existing_comments.

You are doing a second pass on a document that contains \"tags\" (shapes that are placed over the main content of each page with text that refers to edits or refinements on the particular page). 

You are given:
{state_original_doc}: the original document with comments embedded in \"tags\"
existing_comments: a list of comments that were already extracted in a first pass. Each existing comment has text and slide_refs.

Your job is to look again through the entire document and find any additional actionable comments or requested changes that are not yet covered by existing_comments.

A comment is “covered” by an existing comment if:
- It clearly refers to the same requested change, even if phrased slightly differently; or
- It is a minor rephrasing or clarification of something already captured.
- You should only output comments that are genuinely new and not already represented in existing_comments.

For each new comment you find, you must output:
- id: a unique ID for this node, like \"E1\", \"E2\", etc. (do not reuse IDs from existing_comments; Node 3 will renumber everything later).
- text: the full text of the actionable comment or requested change, written clearly in your own words if needed.
- slide_refs: an array of slide numbers that the comment refers to. Infer these from the document page that each comment is on. 

Important rules:
- Include every distinct actionable comment that is not covered by existing_comments.
- Do not drop vague comments; if something is ambiguous but clearly implies a requested change, include it.
- Do not duplicate comments already present in existing_comments.
- Return your results as a JSON object with a single comments array, strictly following the provided schema."""
missed_comments = Agent(
  name="Missed Comments",
  instructions=missed_comments_instructions,
  model="gpt-4.1-mini",
  output_type=MissedCommentsSchema,
  model_settings=ModelSettings(
    temperature=0.1,
    top_p=1,
    max_tokens=4096,
    store=True
  )
)


class CommentFinderContext:
  def __init__(self, state_original_doc: str):
    self.state_original_doc = state_original_doc
def comment_finder_instructions(run_context: RunContextWrapper[CommentFinderContext], _agent: Agent[CommentFinderContext]):
  state_original_doc = run_context.context.state_original_doc
  return f"""You are checking whether a slide deck contains any internal comments or editorial markup inside the document itself (as opposed to client-ready content).

You are given {state_original_doc}, which is a structured representation of the deck. An “internal comment” is any text that clearly looks like internal feedback, instructions, or placeholders, rather than final client-facing content.

Look through all slides in {state_original_doc} and if you do not find any obvious internal comments, set has_internal_comments to false.

Your response must be a single JSON object with:
has_internal_comments: boolean"""
comment_finder = Agent(
  name="Comment Finder",
  instructions=comment_finder_instructions,
  model="gpt-4.1-mini",
  output_type=CommentFinderSchema,
  model_settings=ModelSettings(
    temperature=0.1,
    top_p=1,
    max_tokens=1024,
    store=True
  )
)


comment_compiler = Agent(
  name="Comment Compiler",
  instructions="""Treat the following lists as:

primary_comments (JSON):
{{ node[\"Extract Comments\"].output_parsed.comments }}

extra_comments (JSON):
{{ node[\"Missed Comments\"].output_parsed.comments }}

You are consolidating two lists of comments into a single, clean checklist.

You are given:
primary_comments: the list of comments produced by an initial extraction pass.
extra_comments: the list of additional comments produced by a second pass that tried to find any missed items.

Each comment object has:
id: a string ID (not important; you will replace these).
text: the text of the comment.
slide_refs: an array of slide numbers that the comment refers to.

Your job:
Merge primary_comments and extra_comments.
Remove duplicates - comments should be treated as duplicates if they clearly refer to the same underlying requested change, even if the phrasing is not identical. When de-duplicating,
prioritize the version that is more specific or clearer.
If both are equally clear, you may choose either one.
If a comment refers to multiple distinct edits, please separate into multiple comments. 

Normalize the final list:
Reassign IDs so they are sequential and of the form \"C1\", \"C2\", \"C3\", …
Ensure each comment object has:
id: \"C1\", \"C2\", etc.
text: clear, standalone comment text.
slide_refs: an array of slide numbers (may be empty if truly unknown).

Important rules:
If a comment contains two distinct directions, contains a line-break, contains multiple sentences, or anything else indicating that it is referring to two unique edits, separate the comment out into multiple comments so that each comment in the final list only includes one distinct edit.
Unless two comments are clearly the same requested change, you must keep both. If you are unsure whether two comments are duplicates, treat them as separate and keep them both.
If two comments refer to the same underlying change but one is more detailed, merge them into one comment that preserves all important detail.
Output a JSON object with a single comments array matching the provided schema.""",
  model="gpt-4.1-mini",
  output_type=CommentCompilerSchema,
  model_settings=ModelSettings(
    temperature=0.2,
    top_p=1,
    max_tokens=4096,
    store=True
  )
)


class WorkflowInput(BaseModel):
  input_as_text: str


# Main code entrypoint
async def run_workflow(workflow_input: WorkflowInput):
  with trace("tags_agent"):
    state = {
      "original_doc": None,
      "revised_doc": None
    }
    workflow = workflow_input.model_dump()
    conversation_history: list[TResponseInputItem] = [
      {
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": workflow["input_as_text"]
          }
        ]
      }
    ]
    comment_finder_result_temp = await Runner.run(
      comment_finder,
      input=[
        *conversation_history
      ],
      run_config=RunConfig(trace_metadata={
        "__trace_source__": "agent-builder",
        "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
      }),
      context=CommentFinderContext(state_original_doc=state["original_doc"])
    )

    conversation_history.extend([item.to_input_item() for item in comment_finder_result_temp.new_items])

    comment_finder_result = {
      "output_text": comment_finder_result_temp.final_output.json(),
      "output_parsed": comment_finder_result_temp.final_output.model_dump()
    }
    if comment_finder_result["output_parsed"]["has_internal_comments"] == True:
      extract_comments_result_temp = await Runner.run(
        extract_comments,
        input=[
          *conversation_history
        ],
        run_config=RunConfig(trace_metadata={
          "__trace_source__": "agent-builder",
          "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
        }),
        context=ExtractCommentsContext(state_original_doc=state["original_doc"])
      )

      conversation_history.extend([item.to_input_item() for item in extract_comments_result_temp.new_items])

      extract_comments_result = {
        "output_text": extract_comments_result_temp.final_output.json(),
        "output_parsed": extract_comments_result_temp.final_output.model_dump()
      }
      missed_comments_result_temp = await Runner.run(
        missed_comments,
        input=[
          *conversation_history
        ],
        run_config=RunConfig(trace_metadata={
          "__trace_source__": "agent-builder",
          "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
        }),
        context=MissedCommentsContext(state_original_doc=state["original_doc"])
      )

      conversation_history.extend([item.to_input_item() for item in missed_comments_result_temp.new_items])

      missed_comments_result = {
        "output_text": missed_comments_result_temp.final_output.json(),
        "output_parsed": missed_comments_result_temp.final_output.model_dump()
      }
      comment_compiler_result_temp = await Runner.run(
        comment_compiler,
        input=[
          *conversation_history
        ],
        run_config=RunConfig(trace_metadata={
          "__trace_source__": "agent-builder",
          "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
        })
      )

      conversation_history.extend([item.to_input_item() for item in comment_compiler_result_temp.new_items])

      comment_compiler_result = {
        "output_text": comment_compiler_result_temp.final_output.json(),
        "output_parsed": comment_compiler_result_temp.final_output.model_dump()
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
      return evaluate_comments_result["output_parsed"]
    else:
      comment_compiler_result_temp = await Runner.run(
        comment_compiler,
        input=[
          *conversation_history
        ],
        run_config=RunConfig(trace_metadata={
          "__trace_source__": "agent-builder",
          "workflow_id": "wf_6917b09ea07c8190b49f8efe6ebc26240ad6ff7efdd78cdd"
        })
      )

      conversation_history.extend([item.to_input_item() for item in comment_compiler_result_temp.new_items])

      comment_compiler_result = {
        "output_text": comment_compiler_result_temp.final_output.json(),
        "output_parsed": comment_compiler_result_temp.final_output.model_dump()
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
      return evaluate_comments_result["output_parsed"]

run_agent_workflow = run_workflow

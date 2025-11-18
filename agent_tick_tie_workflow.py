import json
from pydantic import BaseModel
from agents import RunContextWrapper, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace

class ExtractValuesSchema__FactsItem(BaseModel):
  id: str
  metric_label: str
  entity: str | None
  metric: str | None
  period: str | None
  scenario: str | None
  value: float | None
  raw_value_str: str
  unit: str | None
  page: int
  source_text: str


class ExtractValuesSchema(BaseModel):
  facts: list[ExtractValuesSchema__FactsItem]


class CheckAcrossDocumentSchema__TiesOutItem(BaseModel):
  metric_label: str
  canonical_value: str
  pages: list[int]


class CheckAcrossDocumentSchema__ValuesByPageItem(BaseModel):
  page: int
  value: str


class CheckAcrossDocumentSchema__CheckItem(BaseModel):
  metric_label: str
  values_by_page: list[CheckAcrossDocumentSchema__ValuesByPageItem]
  reason: str


class CheckAcrossDocumentSchema(BaseModel):
  ties_out: list[CheckAcrossDocumentSchema__TiesOutItem]
  check: list[CheckAcrossDocumentSchema__CheckItem]


class ExtractValuesContext:
  def __init__(self, state_revised_doc: str, state_email_text: str):
    self.state_revised_doc = state_revised_doc
    self.state_email_text = state_email_text
def extract_values_instructions(run_context: RunContextWrapper[ExtractValuesContext], _agent: Agent[ExtractValuesContext]):
  state_revised_doc = run_context.context.state_revised_doc
  state_email_text = run_context.context.state_email_text
  return f"""You are helping with a “tick and tie” consistency check on a financial slide deck. 

You are helping with a “tick and tie” consistency check on a financial slide deck.
You are given the full deck as structured data: an array of slides, each with an index (page number) and text (all visible text on that slide).
Your job: Scan all slides from  {state_revised_doc} and extract every numeric statement that looks like a financial or operational metric worth checking for consistency across the deck. If a metric is mentioned in {state_email_text}, please carefully check through the deck to make sure that everything matches for that metrics.

Examples include (but are not limited to): Revenue, revenue growth, sales, volume, EBITDA, EBITDA margin, EBIT, margins, EPS, share price, valuation multiples, Leverage, net debt, cash and capex.

For each such numeric statement you find, you must create a fact object with the following fields (matching the output schema you have been given):
id: A unique string ID for the fact, like \"F1\", \"F2\", etc.
metric_label: A short, human-readable label that uniquely describes the concept, e.g. \"2026E Apple revenue growth\" or \"FY26 Meta EBITDA margin (Reported)\".
entity: The company or entity name if it is clearly implied (e.g., \"Apple\", \"Google\"). If not clearly implied, set this to null.
metric: A normalized metric name in snake_case, such as \"revenue\", \"revenue_growth\", \"ebitda\", \"ebitda_margin\", \"eps\", \"leverage\". If you are unsure, choose a reasonable generic metric name (e.g. \"other_metric\").
period: The time period if given, such as \"2026E\", \"FY26\", \"Q4 2025\". If no period is given, set this to null.
scenario: The scenario label if implied, such as \"base\", \"upside\", \"downside\", \"reported\", \"adjusted\", \"pro_forma\". If no scenario is implied, set this to null.
value: The normalized numeric value as a number.
For percentages, convert “6%” to 0.06.
For multiples like “12.5x”, store 12.5.
For plain numbers like “1,200” or “$1.2bn”, store the numeric value (e.g. 1200000000 if you can infer the magnitude; otherwise store 1.2 and let the unit convey the scale).
raw_value_str: The original value string as it appears on the slide, e.g. \"6%\", \"12.5x\", \"$1.2bn\".
unit: A short unit label such as \"pct\", \"usd\", \"usd_mn\", \"usd_bn\", \"x\", \"multiple\", \"shares\". If unclear, choose a reasonable generic label or set to null.
page: The slide index (page number) where this fact appears.
source_text: The specific line or short snippet of text around the value that you used to extract this fact.

Important rules:
Only extract facts that are meaningful to check for consistency across pages (i.e., metrics that might be repeated elsewhere). You may ignore trivial counts or obviously one-off numbers (e.g., “3 key pillars”).
If the same metric appears multiple times on the same slide, you may aggregate or pick the clearest occurrence — do not spam duplicates.
Be conservative but useful: it is better to capture slightly more facts than too few, but avoid extracting every random number.
Limit yourself to at most 100 fact objects across the entire deck so the JSON output stays concise and valid.

Your output must strictly follow the provided JSON schema with a top-level facts array. """
extract_values = Agent(
  name="Extract Values",
  instructions=extract_values_instructions,
  model="gpt-4.1",
  output_type=ExtractValuesSchema,
  model_settings=ModelSettings(
    temperature=1,
    top_p=1,
    max_tokens=4096,
    store=True
  )
)


check_across_document = Agent(
  name="Check Across Document",
  instructions="""You are performing a “tick and tie” consistency check on a financial slide deck.
You are given:
facts: an array of fact objects extracted from the deck, each with metric_label, entity, metric, period, scenario, value, raw_value_str, page, and source_text.
tolerance: a numeric tolerance value (for example, 0.0005 means 5 basis points for percentages) that tells you how close two numeric values must be to be treated as “the same”.
Your job:
Group the facts into metric groups that refer to the same conceptual metric. A reasonable grouping key is a combination of:
entity (if not null)
metric
period (if not null)
scenario (if not null) The goal is that each group is something like “2026E Apple revenue growth (base)” or “FY26 Meta EBITDA margin (reported)”.
For each metric group, collect:
Its metric_label (you may pick the clearest or most complete label from the group).
All value + page pairs in that group.
Decide if the metric group is consistent or inconsistent:
If the metric appears only once in the entire deck (i.e., only on one page), you may ignore it for this check or treat it as consistent; it is not useful for “tick and tie”.
If the metric appears on multiple pages, compare the numeric values:
If all values are equal within tolerance, consider the metric consistent and put it in the ties_out section.
If any values differ by more than tolerance, consider the metric inconsistent and put it in the check section.
Populate the output sections as follows:
For ties_out:
Include one entry per metric group that appears on at least two pages and is consistent.
Each entry must have:
metric_label: a concise description of the metric, e.g. \"2026E Apple revenue growth\".
canonical_value: the common value across the deck, expressed in a human-readable way (e.g., \"6%\", \"$1.2bn\", \"3.0x\"). Use the raw_value_str from one of the facts, or construct a clean representation if multiple are equivalent (e.g., \"6%\" vs \"6.0%\").
pages: an array of all page numbers where this metric appears.
For check:
Include one entry per metric group that appears on at least two pages and is inconsistent (values differ beyond tolerance).
Each entry must have:
metric_label: same concept as above.
values_by_page: an array of {page, value} objects, where value is a human-readable string (e.g., \"6%\", \"5.5%\", \"3.0x\", \"$4.25\"). Use the raw_value_str from each fact whenever possible.
reason: one clear sentence explaining the discrepancy, for example:
\"2026E Apple revenue growth appears as 6% on page 3 and 5.5% on page 12.\"
Ignore metric groups that are clearly different by intent (for example, one is “Upside” scenario and another is “Base” scenario) only if this is obvious from the scenario field or from the text. Those should be treated as separate metric groups and not flagged as inconsistent. If you are not sure whether a difference is intentional, err on the side of including it in check and explain your uncertainty in the reason.
Output format:
You must output a single JSON object with two arrays:
ties_out: list of consistent metric groups, formatted as described above.
check: list of inconsistent metric groups, formatted as described above.
The output must strictly follow the provided JSON schema for ties_out and check.""",
  model="gpt-4.1",
  output_type=CheckAcrossDocumentSchema,
  model_settings=ModelSettings(
    temperature=1,
    top_p=1,
    max_tokens=2048,
    store=True
  )
)


class WorkflowInput(BaseModel):
    input_as_text: str


# Main code entrypoint
async def run_workflow(workflow_input: WorkflowInput):
    with trace("Bifocal_Tick and Tie"):
        workflow = workflow_input.model_dump()
        parsed_input = json.loads(workflow["input_as_text"])

        state = {
            "email_text": parsed_input.get("email_text") or "",
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
        extract_values_result_temp = await Runner.run(
            extract_values,
            input=[
                *conversation_history
            ],
            run_config=RunConfig(trace_metadata={
                "__trace_source__": "agent-builder",
                "workflow_id": "wf_6918f4d9a0fc819087837d1e3949b90308dbf8fd4d026c61"
            }),
            context=ExtractValuesContext(state_revised_doc=state["revised_doc"], state_email_text=state["email_text"])
        )

        if not extract_values_result_temp.final_output:
            raise RuntimeError("Extract Values agent returned no output.")

        conversation_history.extend([item.to_input_item() for item in extract_values_result_temp.new_items])

        extract_values_result = {
            "output_text": extract_values_result_temp.final_output.json(),
            "output_parsed": extract_values_result_temp.final_output.model_dump()
        }
        check_across_document_result_temp = await Runner.run(
            check_across_document,
            input=[
                *conversation_history
            ],
            run_config=RunConfig(trace_metadata={
                "__trace_source__": "agent-builder",
                "workflow_id": "wf_6918f4d9a0fc819087837d1e3949b90308dbf8fd4d026c61"
            })
        )

        if not check_across_document_result_temp.final_output:
            raise RuntimeError("Check Across Document agent returned no output.")

        conversation_history.extend([item.to_input_item() for item in check_across_document_result_temp.new_items])

        check_across_document_result = {
            "output_text": check_across_document_result_temp.final_output.json(),
            "output_parsed": check_across_document_result_temp.final_output.model_dump()
        }
        return check_across_document_result["output_parsed"]

# test_agent_local.py
#
# Local test harness to exercise:
# - agent_workflow.run_agent_workflow
# without involving email or PPTX files.

import json
from agent_workflow import run_agent_workflow


def build_fake_docs():
    """
    Build simple, fake 'original_doc' and 'revised_doc' structures
    that look like what your PPTX parser would produce.

    You can later replace this with real pptx_to_struct(path).
    """
    original_doc = {
        "slides": [
            {
                "index": 1,
                "text": "Executive Summary\nCompany XYZ is a leading provider of widgets."
            },
            {
                "index": 2,
                "text": "EBITDA Bridge\n2023A EBITDA: $100mm\n2026E EBITDA: $150mm\nMargin: 25%"
            },
            {
                "index": 3,
                "text": "Guidance\nRevenue growth: 10% CAGR\nNo clarification if guidance is pro forma or standalone."
            }
        ]
    }

    # Revised doc where we fix some but not all comments
    revised_doc = {
        "slides": [
            {
                "index": 1,
                "text": "Executive Summary\nCompany XYZ is a leading provider of widgets."
            },
            {
                "index": 2,
                "text": (
                    "EBITDA Bridge\n2023A EBITDA: $100mm\n2026E EBITDA: $150mm\n"
                    "Margin: 27%  # Updated margin"
                )
            },
            {
                "index": 3,
                "text": (
                    "Guidance\nRevenue growth: 10% CAGR\n"
                    "Guidance figures (still no explicit mention of pro forma vs standalone)."
                )
            }
        ]
    }

    return original_doc, revised_doc


def build_fake_email_text():
    """
    Sample email text that mimics a banker-style comment email.
    Adjust this as you like to see how the agent behaves.
    """
    return """Team,

A few comments on the draft deck:

1) On slide 2 (EBITDA Bridge), please fix the EBITDA margin so that it reflects the updated 27% figure for 2026E.
2) On the guidance slide (slide 3), please clarify whether the guidance figures are pro forma for the transaction or standalone.
3) Consider adding a quick bullet on slide 1 that highlights that Company XYZ is the #1 player in its core market.

Thanks,
Udai
"""


def format_summary(comments):
    """
    Same idea as the email summary function:
    take the agent JSON and produce a readable summary.
    """
    implemented = [c for c in comments if c["status"] == "implemented"]
    partial = [c for c in comments if c["status"] == "partially_implemented"]
    missed = [c for c in comments if c["status"] == "not_implemented"]
    unclear = [c for c in comments if c["status"] == "unclear"]

    lines = [
        "Coverage summary:",
        f"- Implemented: {len(implemented)}",
        f"- Partially implemented: {len(partial)}",
        f"- Not implemented: {len(missed)}",
        f"- Unclear: {len(unclear)}",
        "",
    ]

    if partial:
        lines.append("Partially implemented:")
        for c in partial:
            lines.append(
                f"- {c['id']} (slides {c['slide_refs']}): {c['text']}\n"
                f"  Reason: {c['reason']}\n"
                f"  Suggestion: {c['suggestion']}"
            )
        lines.append("")

    if missed:
        lines.append("Not implemented:")
        for c in missed:
            lines.append(
                f"- {c['id']} (slides {c['slide_refs']}): {c['text']}\n"
                f"  Reason: {c['reason']}\n"
                f"  Suggestion: {c['suggestion']}"
            )
        lines.append("")

    if unclear:
        lines.append("Unclear / needs human review:")
        for c in unclear:
            lines.append(
                f"- {c['id']} (slides {c['slide_refs']}): {c['text']}\n"
                f"  Reason: {c['reason']}"
            )

    return "\n".join(lines)


if __name__ == "__main__":
    original_doc, revised_doc = build_fake_docs()
    email_text = build_fake_email_text()

    result = run_agent_workflow(
        email_text=email_text,
        original_doc=original_doc,
        revised_doc=revised_doc,
    )

    print("Raw agent output:\n")
    print(json.dumps(result, indent=2))
    print("\n" + "=" * 60 + "\n")
    print(format_summary(result["comments"]))

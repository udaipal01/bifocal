import os
import imaplib
import smtplib
import ssl
import tempfile
import re
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default as default_policy
from dotenv import load_dotenv

from typing import List, Optional, Tuple

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from agent_runner import run_agent_workflow


load_dotenv()

IMAP_HOST = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


# ---------- Helpers: PPTX → structured JSON ----------

def pptx_to_struct(path: str) -> dict:
    """Convert a .pptx file into {slides: [{index, text}...]}."""
    prs = Presentation(path)
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        texts: List[str] = []
        for shape in slide.shapes:
            texts.extend(_extract_shape_text(shape))

        notes_text = _extract_notes_text(slide)
        if notes_text:
            texts.append(notes_text)

        slides.append({
            "index": i,
            "text": "\n".join(t for t in texts if t).strip()
        })
    return {"slides": slides}


def _extract_notes_text(slide) -> str:
    if not slide.has_notes_slide:
        return ""
    notes_frame = slide.notes_slide.notes_text_frame
    if not notes_frame:
        return ""
    text = "\n".join(
        paragraph.text.strip()
        for paragraph in notes_frame.paragraphs
        if paragraph.text and paragraph.text.strip()
    )
    return f"[Notes] {text}" if text else ""


def _extract_shape_text(shape) -> List[str]:
    """
    Recursively collect text from any shape, including grouped overlays,
    tables, and charts. These overlays often carry reviewer comments.
    """
    texts: List[str] = []

    # Group shapes contain nested shapes that may have their own text.
    if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            texts.extend(_extract_shape_text(child))

    # Standard text frames
    if getattr(shape, "has_text_frame", False):
        frame_text = "\n".join(
            paragraph.text.strip()
            for paragraph in shape.text_frame.paragraphs
            if paragraph.text and paragraph.text.strip()
        )
        if frame_text:
            texts.append(frame_text)
    elif hasattr(shape, "text"):  # Fallback for placeholders without text_frame
        text = (shape.text or "").strip()
        if text:
            texts.append(text)

    # Tables can contain reviewer notes in cells
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    texts.append(cell_text)

    # Chart titles/data labels sometimes hold textual comments
    if getattr(shape, "has_chart", False):
        chart = shape.chart
        if chart.has_title:
            chart_title = chart.chart_title.text_frame.text.strip()
            if chart_title:
                texts.append(chart_title)
        for series in chart.series:
            if not getattr(series, "data_labels", None):
                continue
            for point in getattr(series, "points", []):
                data_label = getattr(point, "data_label", None)
                if not data_label or not getattr(data_label, "has_text_frame", False):
                    continue
                label_text = "\n".join(
                    paragraph.text.strip()
                    for paragraph in data_label.text_frame.paragraphs
                    if paragraph.text and paragraph.text.strip()
                )
                if label_text:
                    texts.append(label_text)

    return texts


# ---------- Helpers: Email parsing ----------

def extract_body_and_attachments(raw_msg: bytes):
    """Return (body_text, [attachment_info]) for a raw email."""
    msg = BytesParser(policy=default_policy).parsebytes(raw_msg)

    # Body text (prefer plain)
    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if ctype == "text/plain" and disp is None:
                body_text = part.get_content()
                break
    else:
        body_text = msg.get_content()

    # Attachments
    attachment_infos = []
    for part in msg.walk():
        disp = part.get_content_disposition()
        if disp == "attachment":
            filename = part.get_filename()
            if not filename:
                continue
            # save to temp file
            data = part.get_payload(decode=True)
            fd, tmp_path = tempfile.mkstemp(suffix=filename)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            attachment_infos.append({
                "path": tmp_path,
                "filename": filename
            })

    from_addr = msg["From"]
    subject = msg["Subject"]
    message_id = msg["Message-ID"]

    return body_text.strip(), attachment_infos, from_addr, subject, message_id


# ---------- Call your Agent Builder workflow ----------

def run_agent(email_text: str, original_doc: dict, revised_doc: dict) -> dict:
    """
    Call the Agent Builder workflow you exported as `agent_workflow.py`.

    The generated file includes an example of how to run it – usually something like:
       result = workflow.run(input={...})
    or:
       result = runner.run(input={...})

    Adjust this function to match the exact call from that file.
    """
    # ⬇️ EXAMPLE – you must align with the code that Agent Builder generated.
    # Look in agent_workflow.py for the "main" run call and copy it here.

    # For example, if agent_workflow defines an async `run` function:
    #
    #   from agents import run
    #   async def run_workflow(input):
    #       ...
    #
    # You might do something like:
    #
    #   result = asyncio.run(agent_workflow.run_workflow(
    #       {"email_text": email_text,
    #        "original_doc": original_doc,
    #        "revised_doc": revised_doc}
    #   ))
    #
    # And ensure it returns the JSON matching your Node 3 schema.

    # For now, we’ll assume there is a synchronous helper:
    result = run_agent_workflow(
        email_text = email_text,
        original_doc = original_doc,
        revised_doc = revised_doc,
    )

    # Make sure `result` is a plain Python dict:
    # e.g. {"comments": [...]} as per your Node 3 schema
    return result


# ---------- Formatting the reply email ----------

def format_summary(comments: list) -> str:
    """Turn the agent JSON into a banker-style email body."""
    implemented = [c for c in comments if c["status"] == "implemented"]
    partial = [c for c in comments if c["status"] == "partially_implemented"]
    missed = [c for c in comments if c["status"] == "not_implemented"]
    unclear = [c for c in comments if c["status"] == "unclear"]

    lines = []
    lines.append(f"Coverage summary:")
    lines.append(f"- Implemented: {len(implemented)}")
    lines.append(f"- Partially implemented: {len(partial)}")
    lines.append(f"- Not implemented: {len(missed)}")
    lines.append(f"- Unclear: {len(unclear)}\n")

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


# ---------- Main processing: read email → agent → send email ----------

def process_one_email(raw_msg: bytes):
    email_text, attachments, from_addr, subject, message_id = \
        extract_body_and_attachments(raw_msg)

    pptx_attachments = [
        att for att in attachments
        if att["filename"] and att["filename"].lower().endswith(".pptx")
    ]

    if len(pptx_attachments) < 2:
        print("Expected at least 2 PPTX attachments (original + revised); skipping.")
        return

    original_att, revised_att = _choose_original_and_revised(pptx_attachments)
    original_path, revised_path = original_att["path"], revised_att["path"]

    original_doc = pptx_to_struct(original_path)
    revised_doc = pptx_to_struct(revised_path)

    result = run_agent(email_text, original_doc, revised_doc)
    comments = result["comments"]

    summary = format_summary(comments)

    # Send reply to yourself (or to original sender)
    send_email(
        to_addr=from_addr,
        subject=f"Re: {subject} [Comment coverage]",
        body=summary,
    )


def send_email(to_addr: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, 465, context=context) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        print(f"Sent coverage email to {to_addr}")


def poll_inbox():
    """Simple one-shot poll: fetch unread emails, process, mark as seen."""
    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    mail.select("INBOX")

    typ, data = mail.search(None, "UNSEEN")
    if typ != "OK":
        print("No messages found.")
        return

    for num in data[0].split():
        typ, msg_data = mail.fetch(num, "(RFC822)")
        if typ != "OK":
            continue
        raw_msg = msg_data[0][1]
        print(f"Processing message UID {num.decode()}")
        process_one_email(raw_msg)
        # Mark as seen (already handled)
        mail.store(num, "+FLAGS", "\\Seen")

    mail.close()
    mail.logout()


def _choose_original_and_revised(attachments: List[dict]) -> Tuple[dict, dict]:
    """
    Determine original vs revised PPTX based on version numbers in filenames.
    When two or more attachments include `_vNN`, the lowest number is original
    and the highest is revised. Otherwise fall back to alphabetical order.
    """
    versioned = [
        (att, _parse_version(att.get("filename")))
        for att in attachments
    ]
    valid = [item for item in versioned if item[1] is not None]
    if len(valid) >= 2:
        valid.sort(key=lambda item: item[1])
        return valid[0][0], valid[-1][0]

    sorted_atts = sorted(
        attachments,
        key=lambda att: (att.get("filename") or "").lower()
    )
    return sorted_atts[0], sorted_atts[-1]


def _parse_version(filename: Optional[str]) -> Optional[int]:
    """Extract the integer after '_v' / '-v' etc. Return None if absent."""
    if not filename:
        return None
    match = re.search(r"[._-]v(\d+)", filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


if __name__ == "__main__":
    poll_inbox()

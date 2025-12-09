import os
import tempfile
from typing import Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from agent_runner import run_agent_workflow
from email_bot import attachment_to_struct, format_summary


app = FastAPI(title="Bifocal API", version="1.0.0")


async def _save_upload(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "")[1] or ""
    try:
        contents = await upload.read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Failed to read file {upload.filename}: {exc}") from exc

    if not contents:
        raise HTTPException(status_code=400, detail=f"File {upload.filename} is empty.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        return tmp.name


async def _struct_from_upload(upload: UploadFile) -> Dict:
    if not upload:
        return {"slides": []}
    path = await _save_upload(upload)
    attachment = {"path": path, "filename": upload.filename}
    try:
        return attachment_to_struct(attachment)
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}


@app.post("/analyze", response_class=JSONResponse)
async def analyze_deck(
    email_text: str = Form(...),
    revised_file: UploadFile = File(...),
    original_file: UploadFile | None = File(None),
    run_tick_tie: bool = Form(False),
    only_tick: bool = Form(False),
):
    revised_doc = await _struct_from_upload(revised_file)
    original_doc = await _struct_from_upload(original_file) if original_file else {"slides": []}

    result = run_agent_workflow(
        email_text=email_text,
        original_doc=original_doc,
        revised_doc=revised_doc,
        run_tick_tie=run_tick_tie,
    )

    tags = result.get("tags", [])
    email_comments = result.get("email_comments", [])
    tick_tie = result.get("tick_tie")
    summary = format_summary(tags, email_comments, tick_tie, show_comments=not only_tick)

    return {
        "summary": summary,
        "tags": tags,
        "email_comments": email_comments,
        "tick_tie": tick_tie,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)

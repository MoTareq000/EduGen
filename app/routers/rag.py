from dataclasses import dataclass

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas import GenerateExamRequest
from app.db.connection import get_db_connection
from app.services.audit_service import audit_event
from app.services.rag_service import get_rag, list_pdf_files

router = APIRouter(prefix="/rag", tags=["rag"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 20


@dataclass
class UploadedPDFAdapter:
    name: str
    payload: bytes

    def getvalue(self) -> bytes:
        return self.payload


def ensure_instructor(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if row[0] != "instructor":
            raise HTTPException(status_code=403, detail="User is not an instructor")
    finally:
        cur.close()
        conn.close()


@router.post("/generate")
def generate_exam(payload: GenerateExamRequest):
    rag = get_rag()
    text, sources = rag.query(
        payload.topic,
        mcq_count=payload.mcq_count,
        essay_count=payload.essay_count,
        difficulty=payload.difficulty,
        mode="Instructor Mode",
    )
    if isinstance(text, str) and text.startswith("Error calling AI:"):
        raise HTTPException(status_code=502, detail=text)
    return {"content": text, "sources": sorted(list(sources))}


@router.get("/pdfs")
def get_pdfs():
    return {"pdfs": list_pdf_files()}


@router.post("/pdfs/upload")
async def upload_pdfs(
    instructor_id: int = Form(...),
    files: list[UploadFile] = File(...),
):
    ensure_instructor(instructor_id)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {MAX_FILES_PER_UPLOAD}.",
        )

    adapted_files: list[UploadedPDFAdapter] = []
    for file in files:
        filename = (file.filename or "").strip()
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
        payload = await file.read()
        if len(payload) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File too large: {filename}. Max {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
            )
        adapted_files.append(UploadedPDFAdapter(name=filename, payload=payload))

    rag = get_rag()
    result = rag.add_uploaded_pdfs(adapted_files)
    audit_event(
        instructor_id,
        "pdf_upload",
        {
            "added": result.get("added", []),
            "skipped": result.get("skipped", []),
            "failed": result.get("failed", []),
        },
    )
    return result

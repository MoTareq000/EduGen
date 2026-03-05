from typing import Any

from fastapi import HTTPException
from pathlib import Path

_rag: Any | None = None


def get_rag():
    global _rag
    if _rag is None:
        try:
            from rag_pipeline import RAGPipeline

            _rag = RAGPipeline("pdfs")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"RAG initialization failed: {exc}")
    return _rag


def list_pdf_files() -> list[str]:
    pdf_dir = Path("pdfs")
    if not pdf_dir.exists():
        return []
    return sorted([p.name for p in pdf_dir.glob("*.pdf") if p.is_file()])

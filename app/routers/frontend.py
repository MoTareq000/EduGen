from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import FRONTEND_DIR

router = APIRouter(include_in_schema=False)


@router.get("/")
def root():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(str(index_path))

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.storage import get_file

router = APIRouter(prefix="/files", tags=["files"])

@router.get("/{path:path}")
async def serve_file(path: str):
    try:
        data = get_file(path)
        # Определяем content-type по расширению
        if path.endswith(".png"):
            content_type = "image/png"
        elif path.endswith(".jpg") or path.endswith(".jpeg"):
            content_type = "image/jpeg"
        elif path.endswith(".webp"):
            content_type = "image/webp"
        else:
            content_type = "application/octet-stream"
        return Response(content=data, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail="Файл не найден")

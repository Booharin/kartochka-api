from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.database import get_supabase_admin

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{bucket}/{path:path}")
async def proxy_file(bucket: str, path: str):
    try:
        admin = get_supabase_admin()
        file_data = admin.storage.from_(bucket).download(path)
        return Response(content=file_data, media_type="image/png")
    except Exception:
        raise HTTPException(status_code=404, detail="Файл не найден")

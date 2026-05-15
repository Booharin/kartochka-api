from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, BackgroundTasks
from typing import Optional
from app.database import get_pg
from app.auth import get_user_id
from app.services.generation import generate_product_shot, get_prompt_preview
from app.storage import upload_file
import uuid
import httpx
import base64 as b64lib
import time

router = APIRouter(prefix="/generations", tags=["generations"])

API_BASE = "https://api.kartochka.top"


async def save_result(result_b64_or_url: str, user_id: str, generation_id: str) -> str:
    if result_b64_or_url.startswith("data:image"):
        img_bytes = b64lib.b64decode(result_b64_or_url.split(",")[1])
    else:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.get(result_b64_or_url)
            resp.raise_for_status()
            img_bytes = resp.content
    path = f"{user_id}/photos/{generation_id}.png"
    return upload_file(img_bytes, path, "image/png")


async def run_generation(
    generation_id: str,
    user_id: str,
    input_url: str,
    concept: str,
    prompt: Optional[str],
    aspect_ratio: str,
    model: Optional[str],
    category: Optional[str],
    credits_left: int,
):
    pg = get_pg()
    try:
        result_b64_or_url = await generate_product_shot(
            image_url=input_url,
            concept=concept,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            model=model,
            category=category,
        )
        result_url = await save_result(result_b64_or_url, user_id, generation_id)
        cur = pg.cursor()
        cur.execute(
            "UPDATE generations SET status='done', result_url=%s WHERE id=%s",
            (result_url, generation_id)
        )
        cur.execute(
            "UPDATE subscriptions SET credits_left=credits_left-1 WHERE user_id=%s",
            (user_id,)
        )
        print(f"[generation] done id={generation_id}")
    except Exception as e:
        cur = pg.cursor()
        cur.execute(
            "UPDATE generations SET status='failed', error_message=%s WHERE id=%s",
            (str(e), generation_id)
        )
        print(f"[generation] failed id={generation_id} error={e}")


@router.post("/")
async def create_generation(
    background_tasks: BackgroundTasks,
    concept: str = Form(...),
    file: UploadFile = File(...),
    authorization: str = Header(...),
    prompt: Optional[str] = Form(None),
    aspect_ratio: Optional[str] = Form("1:1"),
    model: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    pg = get_pg()
    cur = pg.cursor()

    cur.execute("SELECT credits_left FROM subscriptions WHERE user_id=%s", (user_id,))
    sub = cur.fetchone()
    if not sub or sub["credits_left"] <= 0:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")

    file_content = await file.read()
    file_ext = file.filename.split(".")[-1]
    input_path = f"{user_id}/inputs/{uuid.uuid4()}.{file_ext}"
    input_url = upload_file(file_content, input_path, file.content_type)

    generation_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO generations (id, user_id, status, concept, input_url, model) VALUES (%s,%s,'processing',%s,%s,%s)",
        (generation_id, user_id, concept, input_url, model or "nano-banana")
    )

    background_tasks.add_task(
        run_generation,
        generation_id=generation_id,
        user_id=user_id,
        input_url=input_url,
        concept=concept,
        prompt=prompt,
        aspect_ratio=aspect_ratio or "1:1",
        model=model,
        category=category,
        credits_left=sub["credits_left"],
    )

    return {"generation_id": generation_id, "status": "processing"}


@router.get("/prompt-preview")
async def prompt_preview(model: str, concept: str, prompt: Optional[str] = None):
    return {"prompt": get_prompt_preview(model, concept, prompt)}


@router.get("/")
async def get_generations(
    authorization: str = Header(...),
    limit: int = 20,
    offset: int = 0,
):
    token = authorization.replace("Bearer ", "")
    t0 = time.time()
    user_id = get_user_id(token)
    print(f"[generations] auth: {time.time()-t0:.3f}s")
    pg = get_pg()
    cur = pg.cursor()
    t1 = time.time()
    cur.execute(
        "SELECT * FROM generations WHERE user_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (user_id, limit, offset)
    )
    rows = cur.fetchall()
    print(f"[generations] query: {time.time()-t1:.3f}s, rows: {len(rows)}")
    return {
        "generations": [dict(r) for r in rows],
        "has_more": len(rows) == limit,
    }


@router.get("/{generation_id}")
async def get_generation(generation_id: str, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    pg = get_pg()
    cur = pg.cursor()
    cur.execute(
        "SELECT * FROM generations WHERE id=%s AND user_id=%s",
        (generation_id, user_id)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Генерация не найдена")
    return dict(row)

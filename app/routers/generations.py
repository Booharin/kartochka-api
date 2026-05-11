from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, BackgroundTasks
from typing import Optional
from app.database import get_supabase, get_supabase_admin
from app.services.generation import generate_product_shot, get_prompt_preview
import uuid
import httpx
import base64 as b64lib

router = APIRouter(prefix="/generations", tags=["generations"])

API_BASE = "https://api.kartochka.top"


def get_user_id(token: str) -> str:
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")


async def save_result(
    result_b64_or_url: str,
    user_id: str,
    generation_id: str,
    admin,
) -> str:
    if result_b64_or_url.startswith("data:image"):
        img_bytes = b64lib.b64decode(result_b64_or_url.split(",")[1])
    else:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.get(result_b64_or_url)
            resp.raise_for_status()
            img_bytes = resp.content

    result_path = f"{user_id}/photos/{generation_id}.png"
    admin.storage.from_("results").upload(
        path=result_path,
        file=img_bytes,
        file_options={"content-type": "image/png"}
    )

    return f"{API_BASE}/files/results/{result_path}"


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
    admin = get_supabase_admin()
    try:
        result_b64_or_url = await generate_product_shot(
            image_url=input_url,
            concept=concept,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            model=model,
            category=category,
        )

        result_url = await save_result(result_b64_or_url, user_id, generation_id, admin)

        admin.table("generations").update({
            "status": "done",
            "result_url": result_url,
        }).eq("id", generation_id).execute()

        admin.table("subscriptions").update({
            "credits_left": credits_left - 1
        }).eq("user_id", user_id).execute()

        print(f"[generation] done id={generation_id}")

    except Exception as e:
        admin.table("generations").update({
            "status": "failed",
            "error_message": str(e)
        }).eq("id", generation_id).execute()
        print(f"[generation] failed id={generation_id} error={str(e)}")


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
    admin = get_supabase_admin()

    sub = admin.table("subscriptions")\
        .select("credits_left")\
        .eq("user_id", user_id)\
        .single()\
        .execute()

    if not sub.data or sub.data["credits_left"] <= 0:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")

    file_content = await file.read()
    file_ext = file.filename.split(".")[-1]
    file_path = f"{user_id}/{uuid.uuid4()}.{file_ext}"

    admin.storage.from_("inputs").upload(
        path=file_path,
        file=file_content,
        file_options={"content-type": file.content_type}
    )

    signed = admin.storage.from_("inputs").create_signed_url(file_path, expires_in=3600)
    input_url = signed["signedURL"]

    gen = admin.table("generations").insert({
        "user_id": user_id,
        "status": "processing",
        "concept": concept,
        "input_url": input_url,
        "model": model or "flux-kontext",
    }).execute()

    generation_id = gen.data[0]["id"]

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
        credits_left=sub.data["credits_left"],
    )

    return {
        "generation_id": generation_id,
        "status": "processing",
    }


@router.get("/prompt-preview")
async def prompt_preview(
    model: str,
    concept: str,
    prompt: Optional[str] = None,
):
    return {"prompt": get_prompt_preview(model, concept, prompt)}


@router.get("/")
async def get_generations(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    admin = get_supabase_admin()

    result = admin.table("generations")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()

    return {"generations": result.data}


@router.get("/{generation_id}")
async def get_generation(generation_id: str, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    admin = get_supabase_admin()

    result = admin.table("generations")\
        .select("*")\
        .eq("id", generation_id)\
        .eq("user_id", user_id)\
        .single()\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Генерация не найдена")

    return result.data

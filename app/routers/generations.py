from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from typing import Optional
from app.database import get_supabase, get_supabase_admin
from app.services.generation import generate_product_shot, get_prompt_preview
import uuid

router = APIRouter(prefix="/generations", tags=["generations"])


def get_user_id(token: str) -> str:
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")


@router.post("/")
async def create_generation(
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

    # 1. Проверить кредиты
    sub = admin.table("subscriptions")\
        .select("credits_left")\
        .eq("user_id", user_id)\
        .single()\
        .execute()

    if not sub.data or sub.data["credits_left"] <= 0:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")

    # 2. Загрузить фото
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

    # 3. Создать запись
    gen = admin.table("generations").insert({
        "user_id": user_id,
        "status": "processing",
        "concept": concept,
        "input_url": input_url,
        "model": model or "flux-kontext",
    }).execute()

    generation_id = gen.data[0]["id"]

    # 4. Генерация
    try:
        result_b64_or_url = await generate_product_shot(
            image_url=input_url,
            concept=concept,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            model=model,
            category=category,
        )

        # Если вернулся base64 — загружаем в Storage
        if result_b64_or_url.startswith("data:image"):
            import base64 as b64lib
            img_data = result_b64_or_url.split(",")[1]
            img_bytes = b64lib.b64decode(img_data)
            result_path = f"{user_id}/photos/{generation_id}.png"
            admin.storage.from_("results").upload(
                path=result_path,
                file=img_bytes,
                file_options={"content-type": "image/png"}
            )
            result_url = admin.storage.from_("results").get_public_url(result_path)
        else:
            result_url = result_b64_or_url

        admin.table("generations").update({
            "status": "done",
            "result_url": result_url,
        }).eq("id", generation_id).execute()

        admin.table("subscriptions").update({
            "credits_left": sub.data["credits_left"] - 1
        }).eq("user_id", user_id).execute()

        return {
            "generation_id": generation_id,
            "status": "done",
            "result_url": result_url,
            "credits_left": sub.data["credits_left"] - 1
        }

    except Exception as e:
        admin.table("generations").update({
            "status": "failed",
            "error_message": str(e)
        }).eq("id", generation_id).execute()

        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")


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


@router.get("/prompt-preview")
async def prompt_preview(
    model: str,
    concept: str,
    prompt: Optional[str] = None,
):
    """Возвращает промпт который будет отправлен модели"""
    return {"prompt": get_prompt_preview(model, concept, prompt)}

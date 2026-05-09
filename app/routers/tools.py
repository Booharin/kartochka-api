from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from app.database import get_supabase, get_supabase_admin
from app.services.card import generate_card
import fal_client
import os
import uuid
from app.config import settings

os.environ["FAL_KEY"] = settings.fal_key

router = APIRouter(prefix="/tools", tags=["tools"])


def get_user_id(token: str) -> str:
    from app.database import get_supabase
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")


@router.post("/remove-bg")
async def remove_background(
    file: UploadFile = File(...),
    authorization: str = Header(...),
):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    admin = get_supabase_admin()

    # Проверить кредиты
    sub = admin.table("subscriptions")\
        .select("credits_left")\
        .eq("user_id", user_id)\
        .single()\
        .execute()

    if not sub.data or sub.data["credits_left"] <= 0:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")

    # Загрузить фото
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

    # Удалить фон
    try:
        result = await fal_client.run_async(
            "fal-ai/bria/background/remove",
            arguments={"image_url": input_url}
        )

        result_url = result["image"]["url"]

        # Списать кредит
        admin.table("subscriptions").update({
            "credits_left": sub.data["credits_left"] - 1
        }).eq("user_id", user_id).execute()

        return {
            "result_url": result_url,
            "credits_left": sub.data["credits_left"] - 1
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/generate-card")
async def create_card(
    file: UploadFile = File(...),
    authorization: str = Header(...),
    card_text: str = Form(...),
    aspect_ratio: str = Form("3:4"),
):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    admin = get_supabase_admin()

    # Проверить кредиты
    sub = admin.table("subscriptions")\
        .select("credits_left")\
        .eq("user_id", user_id)\
        .single()\
        .execute()

    if not sub.data or sub.data["credits_left"] <= 0:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов")

    # Загрузить фото
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

    # Парсим текст — каждая строка это преимущество
    benefits = [b.strip() for b in card_text.strip().split("\n") if b.strip()]

    try:
        result_url = await generate_card(
            image_url=input_url,
            benefits=benefits,
            aspect_ratio=aspect_ratio,
        )

        # Сохранить в историю генераций
        admin.table("generations").insert({
            "user_id": user_id,
            "status": "done",
            "concept": "card",
            "input_url": input_url,
            "result_url": result_url,
        }).execute()

        # Списать кредит
        admin.table("subscriptions").update({
            "credits_left": sub.data["credits_left"] - 1
        }).eq("user_id", user_id).execute()

        return {
            "result_url": result_url,
            "credits_left": sub.data["credits_left"] - 1
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

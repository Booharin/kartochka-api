from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from app.database import get_supabase, get_supabase_admin
from app.services.card import generate_card
from openai import AsyncOpenAI
from app.config import settings
import fal_client
import os
import uuid
import base64

os.environ["FAL_KEY"] = settings.fal_key
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

router = APIRouter(prefix="/tools", tags=["tools"])


def get_user_id(token: str) -> str:
    from app.database import get_supabase
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")


@router.post("/suggest-benefits")
async def suggest_benefits(
    file: UploadFile = File(...),
    authorization: str = Header(...),
):
    token = authorization.replace("Bearer ", "")
    get_user_id(token)

    file_content = await file.read()
    image_b64 = base64.b64encode(file_content).decode()
    mime_type = file.content_type or "image/jpeg"

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Ты эксперт по маркетплейсам Wildberries и Ozon. "
                                "Посмотри на фото товара и придумай ровно 4 коротких преимущества "
                                "для карточки инфографики. "
                                "Каждое преимущество — одна строка, максимум 6 слов, на русском языке. "
                                "Отвечай ТОЛЬКО 4 строками без нумерации, без лишнего текста, без кавычек."
                            ),
                        },
                    ],
                }
            ],
            max_tokens=200,
            temperature=0.7,
        )

        text = response.choices[0].message.content.strip()
        benefits = [line.strip() for line in text.split("\n") if line.strip()][:4]

        return {"benefits": benefits}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")


@router.post("/remove-bg")
async def remove_background(
    file: UploadFile = File(...),
    authorization: str = Header(...),
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

    try:
        result = await fal_client.run_async(
            "fal-ai/bria/background/remove",
            arguments={"image_url": input_url}
        )

        result_url = result["image"]["url"]

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

    benefits = [b.strip() for b in card_text.strip().split("\n") if b.strip()]

    try:
        result_url = await generate_card(
            image_url=input_url,
            benefits=benefits,
            aspect_ratio=aspect_ratio,
        )

        admin.table("generations").insert({
            "user_id": user_id,
            "status": "done",
            "concept": "card",
            "input_url": input_url,
            "result_url": result_url,
            "model": "gpt-image-1",
        }).execute()

        admin.table("subscriptions").update({
            "credits_left": sub.data["credits_left"] - 1
        }).eq("user_id", user_id).execute()

        return {
            "result_url": result_url,
            "credits_left": sub.data["credits_left"] - 1
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

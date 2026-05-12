from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, BackgroundTasks
from app.database import get_supabase, get_supabase_admin
from app.services.card import generate_card
from openai import AsyncOpenAI
from app.config import settings
from PIL import Image
import httpx
import fal_client
import os
import uuid
import base64
import io

os.environ["FAL_KEY"] = settings.fal_key
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

router = APIRouter(prefix="/tools", tags=["tools"])

API_BASE = "https://api.kartochka.top"


def get_user_id(token: str) -> str:
    from app.database import get_supabase
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")


async def run_card_generation(
    generation_id: str,
    user_id: str,
    input_url: str,
    benefits: list,
    aspect_ratio: str,
    title: str,
    bottom_text: str,
    credits_left: int,
):
    admin = get_supabase_admin()
    try:
        result_url = await generate_card(
            image_url=input_url,
            benefits=benefits,
            aspect_ratio=aspect_ratio,
            title=title,
            bottom_text=bottom_text,
        )

        admin.table("generations").update({
            "status": "done",
            "result_url": result_url,
        }).eq("id", generation_id).execute()

        admin.table("subscriptions").update({
            "credits_left": credits_left - 1
        }).eq("user_id", user_id).execute()

        print(f"[card] done generation_id={generation_id}")

    except Exception as e:
        admin.table("generations").update({
            "status": "failed",
            "error_message": str(e)
        }).eq("id", generation_id).execute()
        print(f"[card] failed generation_id={generation_id} error={str(e)}")


@router.post("/suggest-card-fields")
async def suggest_card_fields(
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
                                "Посмотри на фото товара и верни JSON строго в таком формате без лишнего текста:\n"
                                '{"title": "Название товара (2-4 слова, русский)", '
                                '"benefits": ["преимущество 1", "преимущество 2", "преимущество 3", "преимущество 4"], '
                                '"bottom_text": "Короткий слоган для баннера (2-5 слов, русский, ЗАГЛАВНЫМИ)"}'
                                "\n\nПравила:\n"
                                "- title: тип товара без бренда, 2-4 слова\n"
                                "- benefits: ровно 4 строки, каждое максимум 6 слов\n"
                                "- bottom_text: ключевое УТП, 2-5 слов заглавными буквами"
                            ),
                        },
                    ],
                }
            ],
            max_tokens=300,
            temperature=0.7,
        )

        import json
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)

        return {
            "title": data.get("title", ""),
            "benefits": data.get("benefits", [])[:4],
            "bottom_text": data.get("bottom_text", ""),
        }

    except Exception:
        return {"title": "", "benefits": [], "bottom_text": ""}


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
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}", "detail": "low"}},
                {"type": "text", "text": "Придумай ровно 4 коротких преимущества товара на русском языке. Только 4 строки без нумерации."},
            ]}],
            max_tokens=200, temperature=0.7,
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
        path=file_path, file=file_content,
        file_options={"content-type": file.content_type}
    )

    signed = admin.storage.from_("inputs").create_signed_url(file_path, expires_in=3600)
    input_url = signed["signedURL"]

    try:
        result = await fal_client.run_async(
            "fal-ai/bria/background/remove",
            arguments={"image_url": input_url}
        )
        transparent_url = result["image"]["url"]

        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.get(transparent_url)
            img_bytes = resp.content

        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white_bg.paste(img, mask=img.split()[3])
        white_bg = white_bg.convert("RGB")

        buf = io.BytesIO()
        white_bg.save(buf, format="JPEG", quality=95)
        result_bytes = buf.getvalue()

        result_path = f"{user_id}/removebg/{uuid.uuid4()}.jpg"
        admin.storage.from_("results").upload(
            path=result_path, file=result_bytes,
            file_options={"content-type": "image/jpeg"}
        )
        result_url = f"{API_BASE}/files/results/{result_path}"

        admin.table("generations").insert({
            "user_id": user_id,
            "status": "done",
            "concept": "removebg",
            "input_url": input_url,
            "result_url": result_url,
            "model": "bria",
        }).execute()

        admin.table("subscriptions").update({
            "credits_left": sub.data["credits_left"] - 1
        }).eq("user_id", user_id).execute()

        return {"result_url": result_url, "credits_left": sub.data["credits_left"] - 1}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/generate-card")
async def create_card(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    authorization: str = Header(...),
    card_text: str = Form(...),
    aspect_ratio: str = Form("3:4"),
    title: str = Form(""),
    bottom_text: str = Form(""),
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
        path=file_path, file=file_content,
        file_options={"content-type": file.content_type}
    )

    signed = admin.storage.from_("inputs").create_signed_url(file_path, expires_in=3600)
    input_url = signed["signedURL"]

    benefits = [b.strip() for b in card_text.strip().split("\n") if b.strip()]

    gen = admin.table("generations").insert({
        "user_id": user_id,
        "status": "processing",
        "concept": "card",
        "input_url": input_url,
        "model": "gpt-image-1",
    }).execute()

    generation_id = gen.data[0]["id"]

    background_tasks.add_task(
        run_card_generation,
        generation_id=generation_id,
        user_id=user_id,
        input_url=input_url,
        benefits=benefits,
        aspect_ratio=aspect_ratio,
        title=title,
        bottom_text=bottom_text,
        credits_left=sub.data["credits_left"],
    )

    return {"generation_id": generation_id, "status": "processing"}

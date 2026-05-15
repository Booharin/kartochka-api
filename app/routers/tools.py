from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, BackgroundTasks
from app.database import get_pg
from app.auth import get_user_id
from app.services.card import generate_card
from app.storage import upload_file
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


async def run_card_generation(
    generation_id: str,
    user_id: str,
    input_url: str,
    benefits: list,
    aspect_ratio: str,
    title: str,
    bottom_text: str,
    card_prompt: str,
    bg_color_hex: str,
    bg_color_name: str,
    credits_left: int,
):
    pg = get_pg()
    try:
        result_url = await generate_card(
            image_url=input_url,
            benefits=benefits,
            aspect_ratio=aspect_ratio,
            title=title,
            bottom_text=bottom_text,
            card_prompt=card_prompt,
            bg_color_hex=bg_color_hex,
            bg_color_name=bg_color_name,
        )
        # Сохраняем base64 в R2
        if result_url.startswith("data:image"):
            import base64 as b64
            img_bytes = b64.b64decode(result_url.split(",")[1])
            path = f"{user_id}/cards/{generation_id}.png"
            result_url = upload_file(img_bytes, path, "image/png")

        cur = pg.cursor()
        cur.execute(
            "UPDATE generations SET status='done', result_url=%s WHERE id=%s",
            (result_url, generation_id)
        )
        cur.execute(
            "UPDATE subscriptions SET credits_left=credits_left-1 WHERE user_id=%s",
            (user_id,)
        )
        print(f"[card] done generation_id={generation_id}")
    except Exception as e:
        cur = pg.cursor()
        cur.execute(
            "UPDATE generations SET status='failed', error_message=%s WHERE id=%s",
            (str(e), generation_id)
        )
        print(f"[card] failed generation_id={generation_id} error={e}")


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
                {"type": "text", "text": """Ты эксперт по маркетплейсам Wildberries и Ozon.
Посмотри на фото товара и верни JSON в точно таком формате (без markdown, без пояснений):
{"title": "Название товара на русском (2-4 слова, без бренда)", "benefits": ["Преимущество 1 (макс 6 слов)", "Преимущество 2 (макс 6 слов)", "Преимущество 3 (макс 6 слов)", "Преимущество 4 (макс 6 слов)"], "bottom_text": "Короткий слоган или УТП (3-5 слов, заглавными)"}"""},
            ]}],
            max_tokens=300, temperature=0.7,
        )
        import json
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)
        return {
            "title": parsed.get("title", ""),
            "benefits": parsed.get("benefits", [])[:4],
            "bottom_text": parsed.get("bottom_text", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {e}")


@router.post("/remove-bg")
async def remove_background(
    file: UploadFile = File(...),
    authorization: str = Header(...),
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
        result_url = upload_file(result_bytes, result_path, "image/jpeg")

        generation_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO generations (id, user_id, status, concept, input_url, result_url, model) VALUES (%s,%s,'done','removebg',%s,%s,'bria')",
            (generation_id, user_id, input_url, result_url)
        )
        cur.execute(
            "UPDATE subscriptions SET credits_left=credits_left-1 WHERE user_id=%s",
            (user_id,)
        )

        return {"result_url": result_url, "credits_left": sub["credits_left"] - 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {e}")


@router.post("/generate-card")
async def create_card(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    authorization: str = Header(...),
    card_text: str = Form(...),
    aspect_ratio: str = Form("3:4"),
    title: str = Form(""),
    bottom_text: str = Form(""),
    card_prompt: str = Form(""),
    bg_color_hex: str = Form(""),
    bg_color_name: str = Form(""),
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

    benefits = [b.strip() for b in card_text.strip().split("\n") if b.strip()]
    generation_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO generations (id, user_id, status, concept, input_url, model) VALUES (%s,%s,'processing','card',%s,'gpt-image-1')",
        (generation_id, user_id, input_url)
    )

    background_tasks.add_task(
        run_card_generation,
        generation_id=generation_id,
        user_id=user_id,
        input_url=input_url,
        benefits=benefits,
        aspect_ratio=aspect_ratio,
        title=title,
        bottom_text=bottom_text,
        card_prompt=card_prompt,
        bg_color_hex=bg_color_hex,
        bg_color_name=bg_color_name,
        credits_left=sub["credits_left"],
    )

    return {"generation_id": generation_id, "status": "processing"}

import httpx
import io
from PIL import Image
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_card(
    image_url: str,
    benefits: list[str],
    aspect_ratio: str = "3:4",
) -> str:

    # Скачиваем фото товара
    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url)
        image_bytes = resp.content

    # Конвертируем в PNG RGBA
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    size = max(img.size)
    square = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    offset = ((size - img.size[0]) // 2, (size - img.size[1]) // 2)
    square.paste(img, offset)
    square = square.resize((1024, 1024), Image.LANCZOS)

    png_buffer = io.BytesIO()
    square.save(png_buffer, format="PNG")
    png_bytes = png_buffer.getvalue()

    benefits_text = "\n".join([f"• {b}" for b in benefits[:6]])

    prompt = f"""Create a professional Russian marketplace product card infographic for Wildberries or Ozon.

Keep the product from the image and add:
- Clean white background
- Bold Russian headline at top describing the product
- Benefits list with green checkmark icons on the left:
{benefits_text}
- Modern professional e-commerce design
- All text in Russian
- Similar to top WB/Ozon product listings"""

    response = await client.images.edit(
        model="gpt-image-1",
        image=("product.png", png_bytes, "image/png"),
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    image_data = response.data[0].b64_json

    # Всегда возвращаем base64 — сохранение в Storage делает generations.py
    return f"data:image/png;base64,{image_data}"

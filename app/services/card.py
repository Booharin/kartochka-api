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

    benefits_text = "\n".join([f"{i+1}. {b}" for i, b in enumerate(benefits[:4])])

    prompt = f"""Create a professional product infographic card for Russian marketplace (Wildberries/Ozon).
Study the product carefully and create a card that matches top-selling listings.

BACKGROUND: Choose naturally based on the product:
- Light/white background for household, cosmetics, food products
- Dark background for tech, sports, premium products
- The background should feel natural for this product category

LAYOUT (square 1:1 format):
TOP SECTION:
- Large bold product name in Russian (mixed case, NOT ALL CAPS) — 2-4 words, black or white text depending on background
- Diagonal colored accent stripe in top-right corner

RIGHT SIDE: The product from the photo, large, centered on its right half
- Product must sit on a surface with a subtle shadow underneath (not floating in air)
- Product should look well-lit and natural

LEFT SIDE: 3-4 benefit blocks, each containing:
- A relevant emoji or simple filled icon (circle with symbol inside) in accent color
- Benefit text in mixed case (first letter capital only), 2-3 lines max
- Small divider line between items

BOTTOM BANNER:
- Full-width colored banner (accent color matching the stripe)
- Short key selling point text in white, bold, mixed case

TYPOGRAPHY RULES:
- Product title: very large, bold, mixed case (e.g. "Бутылка для воды" not "БУТЫЛКА")
- Benefits: medium size, regular weight, mixed case
- Banner text: bold, readable
- NO all-caps except maybe 1-2 word abbreviations

ACCENT COLOR: Pick one color that fits the product:
- Bright green for eco/sports/outdoor
- Electric blue for tech/electronics
- Warm red for food/kitchen
- Purple for cosmetics/beauty
- Orange for tools/construction

PRODUCT BENEFITS to show:
{benefits_text}

CRITICAL RULES:
- All text in Russian
- Do NOT change the product — keep it exactly as in the photo
- Product must have a shadow/ground — not floating
- Clean professional look matching top WB/Ozon sellers
- NO cheap gradients, NO clipart style icons
- The card should look like it was made by a professional designer"""

    response = await client.images.edit(
        model="gpt-image-1",
        image=("product.png", png_bytes, "image/png"),
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    image_data = response.data[0].b64_json

    return f"data:image/png;base64,{image_data}"

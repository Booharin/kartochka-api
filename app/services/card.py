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

    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url)
        image_bytes = resp.content

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    size = max(img.size)
    square = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    offset = ((size - img.size[0]) // 2, (size - img.size[1]) // 2)
    square.paste(img, offset)
    square = square.resize((1024, 1024), Image.LANCZOS)

    png_buffer = io.BytesIO()
    square.save(png_buffer, format="PNG")
    png_bytes = png_buffer.getvalue()

    benefits_text = "\n".join([f"{i+1}. {b}" for i, b in enumerate(benefits[:6])])

    prompt = f"""You are a premium Russian marketplace designer. Create a stunning product infographic card.

STYLE: Dark premium design. Deep dark background (near black or very dark navy/charcoal).
Vibrant accent color (bright green, electric blue, or bold red — pick what fits the product).
High contrast. Professional. Looks like a top-selling WB/Ozon listing.

LAYOUT (portrait orientation):
- TOP LEFT: Large bold product headline in Russian (2-3 words, white text, heavy font)
- TOP RIGHT: The product from the image, large, well-lit, slightly angled for drama
- Diagonal or angular accent stripe behind the product (accent color)
- MIDDLE/LEFT: Each benefit as a separate badge/block:
  - Small icon or geometric shape in accent color on the left
  - Bold label in white (the benefit text)
  - Dark semi-transparent background per item
- BOTTOM: Wide accent-colored banner with a short call-to-action or key spec

PRODUCT BENEFITS to include:
{benefits_text}

RULES:
- All text in Russian
- Keep the exact product from the image — do not alter it
- No cheap clipart, no gradients that look like MS Word
- Typography must look premium: mix of heavy bold and light thin weights
- Shadows, glows, depth — make it feel 3D and dynamic
- Think: high-end sports brand or premium tech product packaging"""

    response = await client.images.edit(
        model="gpt-image-1",
        image=("product.png", png_bytes, "image/png"),
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    image_data = response.data[0].b64_json

    return f"data:image/png;base64,{image_data}"

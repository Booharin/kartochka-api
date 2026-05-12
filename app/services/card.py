import httpx
import io
from PIL import Image
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

ASPECT_RATIO_MAP = {
    "9:16": "1024x1536",
    "3:4":  "1024x1536",
    "1:1":  "1024x1024",
    "4:3":  "1536x1024",
    "16:9": "1536x1024",
}


async def generate_card(
    image_url: str,
    benefits: list[str],
    aspect_ratio: str = "3:4",
    title: str = "",
    bottom_text: str = "",
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

    size_param = ASPECT_RATIO_MAP.get(aspect_ratio, "1024x1536")

    benefits_text = "\n".join([f"✓ {b}" for b in benefits[:4]])

    title_instruction = f"Заголовок вверху карточки: «{title}»" if title else "Заголовок: определи сам по типу товара, на русском, 2-4 слова"
    bottom_instruction = f"Текст в нижнем баннере: «{bottom_text}»" if bottom_text else "Нижний баннер: короткое УТП, 2-4 слова заглавными"

    if size_param == "1024x1536":
        layout_desc = """LAYOUT (vertical portrait):
— TOP: large product headline, left-aligned or centered
— CENTER-RIGHT: the product, large, dominant, on a podium or surface with shadow
— LEFT SIDE: infographic block with benefits icons and text
— BOTTOM: wide accent banner with key text"""
    elif size_param == "1536x1024":
        layout_desc = """LAYOUT (horizontal landscape):
— LEFT HALF: large product headline at top, infographic benefits below
— RIGHT HALF: the product, large, on a surface with shadow
— BOTTOM: accent banner"""
    else:
        layout_desc = """LAYOUT (square):
— TOP: large product headline
— RIGHT HALF: the product, large, on a surface with shadow
— LEFT HALF: infographic benefits list
— BOTTOM: accent banner"""

    prompt = f"""Создай премиальную карточку товара для маркетплейса на основе загруженного фото товара.

Главная задача:
Превратить обычную фотографию товара в дорогую профессиональную marketplace-карточку уровня топовых брендов на Wildberries, Ozon, Amazon или Shopify.

{layout_desc}

ТЕКСТ НА КАРТОЧКЕ (использовать строго):
— {title_instruction}
— {bottom_instruction}
— НЕ добавлять название бренда
— все тексты преимуществ строго как указано ниже, не переводить, не перефразировать

Что нужно сделать:

1. Обработать товар
— аккуратно вырезать объект из исходного фона
— улучшить качество товара
— убрать дефекты, шум, потёртости, загрязнения, заломы и визуальные артефакты
— сделать товар новым, чистым и премиальным
— сохранить оригинальную форму, материал, цвет и особенности товара
— добавить реалистичные блики, объём и мягкие тени
— сохранить фотореализм

2. Создать premium background
— дорогой минималистичный фон
— современная студийная атмосфера
— мягкое профессиональное освещение
— премиальный стиль luxury ecommerce
— realistic shadows, cinematic light, clean композиция
— фон должен подчёркивать товар, а не отвлекать

3. Инфографика — блок СЛЕВА от товара
— минималистичные иконки рядом с каждым преимуществом (круг с символом)
— каждое преимущество на отдельной строке
— тонкие разделители между пунктами
— современная типографика, mixed case (не ALL CAPS)
— стиль: clean, minimal, premium, readable

Преимущества товара (использовать точно этот текст):
{benefits_text}

4. Типографика
— bold sans-serif шрифт
— mixed case (не ALL CAPS) кроме нижнего баннера
— современная визуальная иерархия

5. Общий стиль
— ultra realistic, premium ecommerce advertising
— luxury marketplace card, photorealistic
— expensive commercial design, high-end product presentation
— realistic materials и realistic lighting
— modern branding, premium color grading

Важно:
— не делать дешёвый дизайн, не использовать кислотные цвета
— не ломать форму товара
— товар стоит на поверхности с тенью — не висит в воздухе
— итог должен выглядеть как работа профессионального дизайнера"""

    response = await client.images.edit(
        model="gpt-image-1",
        image=("product.png", png_bytes, "image/png"),
        prompt=prompt,
        n=1,
        size=size_param,
    )

    image_data = response.data[0].b64_json
    return f"data:image/png;base64,{image_data}"

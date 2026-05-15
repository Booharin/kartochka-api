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
    card_prompt: str = "",
    bg_color_hex: str = "",
    bg_color_name: str = "",
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

    title_instruction = f"Заголовок вверху карточки: «{title}»" if title else "заголовок карточки: НЕ добавлять, оставить без заголовка"
    bottom_instruction = f"Текст в нижнем баннере: «{bottom_text}»" if bottom_text else "нижний баннер: НЕ добавлять, оставить без баннера"

    benefits_instruction = f"""3. Инфографика — размещение блоков вокруг товара
— у КАЖДОГО преимущества ОБЯЗАТЕЛЬНО должна быть иконка (круг с символом) — без исключений
— иконка всегда слева от текста преимущества, независимо от расположения блока
— ВАЖНО: определи форму товара и размести блоки соответственно:
  • если товар круглый или компактный — распредели блоки равномерно вокруг товара по периметру (сверху-слева, снизу-слева, сверху-справа, снизу-справа)
  • если товар вытянутый по вертикали — блоки слева и справа от товара на разных уровнях
  • если товар вытянутый по горизонтали — блоки сверху и снизу от товара
— каждый блок размещать отдельно, НЕ группировать все в одну колонку
— текст блоков НЕ должен перекрываться с изображением товара
— блоки только на свободном пространстве фона
— современная типографика, mixed case (не ALL CAPS)
— стиль: clean, minimal, premium, readable

Преимущества товара (использовать ДОСЛОВНО, без изменений):
{benefits_text}""" if benefits else "3. Инфографика — НЕ добавлять блок с преимуществами, оставить чистое пространство"

    if size_param == "1024x1536":
        layout_desc = """LAYOUT (vertical portrait):
— TOP: large product headline, left-aligned or centered
— CENTER: the product, large, dominant, on a podium or surface with shadow
— AROUND PRODUCT: infographic blocks distributed around the product (not all in one column)
— BOTTOM: wide accent banner with key text"""
    elif size_param == "1536x1024":
        layout_desc = """LAYOUT (horizontal landscape):
— LEFT: large product headline at top, infographic benefits distributed around product
— RIGHT: the product, large, on a surface with shadow
— BOTTOM: accent banner"""
    else:
        layout_desc = """LAYOUT (square):
— TOP: large product headline
— CENTER: the product, large, on a surface with shadow
— AROUND PRODUCT: infographic blocks distributed around the product
— BOTTOM: accent banner"""

    bg_color_block = f"""ЦВЕТ ФОНА (ОБЯЗАТЕЛЬНО, наивысший приоритет):
— использовать СТРОГО этот цвет фона: {bg_color_name} ({bg_color_hex})
— весь фон карточки должен быть именно этого цвета
— не заменять другим цветом, не смешивать, не градиент

""" if bg_color_hex else ""

    user_prompt_block = f"""ПОЖЕЛАНИЕ ПОЛЬЗОВАТЕЛЯ (высокий приоритет, реализовать обязательно):
{card_prompt}

""" if card_prompt else ""

    prompt = f"""Создай премиальную карточку товара для маркетплейса на основе загруженного фото товара.

Главная задача:
Превратить обычную фотографию товара в дорогую профессиональную marketplace-карточку уровня топовых брендов на Wildberries, Ozon, Amazon или Shopify.

{layout_desc}

{bg_color_block}{user_prompt_block}ТЕКСТ НА КАРТОЧКЕ (использовать строго):
— {title_instruction}
— {bottom_instruction}
— НЕ добавлять название бренда
— КРИТИЧНО: все тексты преимуществ использовать ДОСЛОВНО как указано ниже
— ЗАПРЕЩЕНО переводить на английский или любой другой язык
— ЗАПРЕЩЕНО перефразировать или изменять текст преимуществ

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

{benefits_instruction}

4. Типографика
— bold sans-serif шрифт
— mixed case (не ALL CAPS) кроме нижнего баннера
— современная визуальная иерархия
— ЗАПРЕЩЕНЫ переносы слов (никаких дефисов в конце строки)
— ЗАПРЕЩЕНЫ сокращения слов — писать каждое слово полностью
— ЗАПРЕЩЕНЫ орфографические ошибки — проверить каждое слово
— если слово не помещается — уменьшить шрифт, но не переносить и не сокращать

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

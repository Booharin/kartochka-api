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

    benefits_text = "\n".join([f"— {b}" for b in benefits[:4]])

    prompt = f"""Создай премиальную карточку товара для маркетплейса на основе загруженного фото товара.

Главная задача:
Превратить обычную фотографию товара в дорогую профессиональную marketplace-карточку уровня топовых брендов на Wildberries, Ozon, Amazon или Shopify.

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
— realistic shadows
— cinematic light
— clean композиция
— фон должен подчёркивать товар, а не отвлекать
— допускаются: мягкие цветовые градиенты, интерьерные элементы, подиум, студийные прожекторы, отражения, premium textures

3. Построить правильную композицию
— товар должен быть главным объектом
— композиция как у профессиональной рекламы
— balanced layout
— premium spacing
— современная визуальная иерархия
— карточка должна выглядеть дорого и clean

4. Добавить инфографику
Добавь современную инфографику в стиле premium marketplace design.
Используй следующие преимущества товара (текст строго на русском языке, не переводить):

{benefits_text}

Оформление инфографики:
— минималистичные иконки рядом с каждым преимуществом
— аккуратные выделенные блоки или строки
— тонкие разделители между пунктами
— современная типографика
— стиль: clean, minimal, premium, expensive looking, readable
— не перегружать дизайн

5. Текст и типографика
— крупный headline — название товара на русском (определи сам по фото)
— bold sans-serif шрифт
— feature blocks с иконками для каждого преимущества
— текст преимуществ точно как указано выше, не изменять
— современная визуальная иерархия

6. Общий стиль
— ultra realistic
— premium ecommerce advertising
— luxury marketplace card
— photorealistic
— expensive commercial design
— high-end product presentation
— realistic materials и realistic lighting
— modern branding
— premium color grading

Важно:
— все тексты преимуществ строго на русском языке, точно как указано
— не делать дешёвый дизайн
— не использовать кислотные цвета
— не делать шаблонную инфографику
— не ломать форму товара
— товар должен выглядеть максимально дорого и привлекательно
— итог должен выглядеть как работа профессионального дизайнера и рекламного агентства"""

    response = await client.images.edit(
        model="gpt-image-1",
        image=("product.png", png_bytes, "image/png"),
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    image_data = response.data[0].b64_json

    return f"data:image/png;base64,{image_data}"

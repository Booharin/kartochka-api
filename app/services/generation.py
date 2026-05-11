import base64
import httpx
import io
import os
import fal_client
from PIL import Image
from openai import AsyncOpenAI
from google import genai
from google.genai import types as gtypes
from typing import Optional, Literal
from app.config import settings

os.environ["FAL_KEY"] = settings.fal_key
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
google_client = genai.Client(api_key=settings.google_api_key)

ModelType = Literal["flux-kontext", "gpt-image-1", "bria-product-shot", "nano-banana"]

CONCEPT_PROMPTS = {
    "studio": "Professional product photography. Clean white studio background, soft diffused lighting from above, product centered, sharp focus, commercial quality e-commerce shot.",
    "interior": "Lifestyle product photography in a modern Scandinavian interior. Natural window light, minimalist home setting, product prominently displayed on surface.",
    "flatlay": "Professional flatlay product photography. Top-down view, clean light background, minimalist composition, soft natural shadows.",
    "model": "Lifestyle product photography with a person using or wearing the product. Natural light, modern urban setting, candid feel.",
}

MODEL_PROMPT_TEMPLATES = {
    "flux-kontext": "Keep this exact product identical - same shape, color, all details. {concept} Do not change the product itself in any way.",
    "gpt-image-1": "You are a professional product photographer for Russian marketplaces (WB/Ozon). Transform this product photo: {concept} Keep the exact same product - preserve all details, colors, shape. No text or watermarks.",
    "bria-product-shot": "{concept}",
    "nano-banana": "Professional product photography for Russian marketplace. {concept} Keep the product exactly as shown - preserve every detail, color, texture. High-end commercial photography.",
}

CATEGORY_MODEL_MAP: dict[str, ModelType] = {
    "shoes": "flux-kontext",
    "clothing": "flux-kontext",
    "electronics": "gpt-image-1",
    "cosmetics": "bria-product-shot",
    "home": "gpt-image-1",
    "default": "nano-banana",
}

GPT_SIZE_MAP = {
    "9:16": "1024x1536",
    "3:4":  "1024x1536",
    "1:1":  "1024x1024",
    "4:3":  "1536x1024",
    "16:9": "1536x1024",
}

FLUX_RATIO_MAP = {
    "9:16": "9:16",
    "3:4":  "3:4",
    "1:1":  "1:1",
    "4:3":  "4:3",
    "16:9": "16:9",
}


def get_prompt_preview(model: str, concept: str, user_prompt: Optional[str] = None) -> str:
    concept_text = CONCEPT_PROMPTS.get(concept, CONCEPT_PROMPTS["studio"])
    if user_prompt:
        concept_text += f" Additional: {user_prompt}"
    template = MODEL_PROMPT_TEMPLATES.get(model, MODEL_PROMPT_TEMPLATES["flux-kontext"])
    return template.format(concept=concept_text)


async def _load_image_as_png(image_url: str) -> bytes:
    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url)
        image_bytes = resp.content
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    size = max(img.size)
    square = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    offset = ((size - img.size[0]) // 2, (size - img.size[1]) // 2)
    square.paste(img, offset)
    square = square.resize((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    square.save(buf, format="PNG")
    return buf.getvalue()


async def _remove_bg(image_url: str) -> str:
    result = await fal_client.run_async(
        "fal-ai/bria/background/remove",
        arguments={"image_url": image_url}
    )
    return result["image"]["url"]


async def _generate_flux_kontext(image_url: str, concept: str, prompt: Optional[str], aspect_ratio: str = "1:1") -> str:
    clean_url = await _remove_bg(image_url)
    final_prompt = get_prompt_preview("flux-kontext", concept, prompt)
    flux_ratio = FLUX_RATIO_MAP.get(aspect_ratio, "1:1")
    result = await fal_client.run_async(
        "fal-ai/flux-pro/kontext",
        arguments={
            "image_url": clean_url,
            "prompt": final_prompt,
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "num_images": 1,
            "output_format": "jpeg",
            "aspect_ratio": flux_ratio,
        }
    )
    print(f"[flux-kontext] aspect_ratio={flux_ratio} timings={result.get('timings', {})}")
    return result["images"][0]["url"]


async def _generate_gpt_image(image_url: str, concept: str, prompt: Optional[str], aspect_ratio: str = "1:1") -> str:
    png_bytes = await _load_image_as_png(image_url)
    final_prompt = get_prompt_preview("gpt-image-1", concept, prompt)
    size = GPT_SIZE_MAP.get(aspect_ratio, "1024x1024")
    response = await openai_client.images.edit(
        model="gpt-image-1",
        image=("product.png", png_bytes, "image/png"),
        prompt=final_prompt,
        n=1,
        size=size,
    )
    usage = getattr(response, "usage", None)
    if usage:
        print(f"[gpt-image-1] input_tokens={usage.input_tokens} output_tokens={usage.output_tokens} total={usage.total_tokens}")
    return f"data:image/png;base64,{response.data[0].b64_json}"


async def _generate_bria(image_url: str, concept: str, prompt: Optional[str]) -> str:
    final_prompt = get_prompt_preview("bria-product-shot", concept, prompt)
    result = await fal_client.run_async(
        "fal-ai/bria/product-shot",
        arguments={
            "image_url": image_url,
            "prompt": final_prompt,
        }
    )
    return result["images"][0]["url"]


async def _generate_nano_banana(image_url: str, concept: str, prompt: Optional[str]) -> str:
    png_bytes = await _load_image_as_png(image_url)
    final_prompt = get_prompt_preview("nano-banana", concept, prompt)

    from PIL import Image as PILImage
    pil_img = PILImage.open(io.BytesIO(png_bytes))

    response = google_client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[final_prompt, pil_img],
        config=gtypes.GenerateContentConfig(
            response_modalities=["IMAGE"],
        )
    )

    usage = getattr(response, "usage_metadata", None)
    if usage:
        print(f"[nano-banana] input_tokens={usage.prompt_token_count} output_tokens={usage.candidates_token_count} total={usage.total_token_count}")

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image"):
            img_b64 = base64.b64encode(part.inline_data.data).decode()
            return f"data:image/png;base64,{img_b64}"

    raise Exception("Nano Banana не вернул изображение")


async def generate_product_shot(
    image_url: str,
    concept: str,
    prompt: Optional[str] = None,
    aspect_ratio: str = "1:1",
    model: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    if model:
        selected = model
    elif category and category in CATEGORY_MODEL_MAP:
        selected = CATEGORY_MODEL_MAP[category]
    else:
        selected = CATEGORY_MODEL_MAP["default"]

    print(f"[generation] concept={concept} model={selected} aspect_ratio={aspect_ratio}")

    if selected == "flux-kontext":
        return await _generate_flux_kontext(image_url, concept, prompt, aspect_ratio)
    elif selected == "gpt-image-1":
        return await _generate_gpt_image(image_url, concept, prompt, aspect_ratio)
    elif selected == "bria-product-shot":
        return await _generate_bria(image_url, concept, prompt)
    elif selected == "nano-banana":
        return await _generate_nano_banana(image_url, concept, prompt)
    else:
        return await _generate_flux_kontext(image_url, concept, prompt, aspect_ratio)

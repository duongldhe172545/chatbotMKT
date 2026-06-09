"""Generate three local SVG logo concepts for a confirmed dealer.

This is the deterministic MVP renderer. It keeps the end-to-end flow usable
without a second image-model API key. A later image generator can replace this
module while preserving the API response contract.
"""
from __future__ import annotations

import logging
import re
from base64 import b64encode
from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from pydantic import BaseModel

from app.llm.auto_derive import gen_initials_full
from app.models.schema import DealerProfileRaw

logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "static" / "generated-logos"


class LogoVariant(BaseModel):
    id: str
    name: str
    style: str
    url: str
    download_url: str


# Fallback palettes matching diverse styles
_DEFAULT_PALETTES = [
    ("#1E3A8A", "#475569", "#F8FAFC"),  # Navy Steel
    ("#0F766E", "#134E4A", "#ECFDF5"),  # Teal Mint
    ("#D97706", "#1F2937", "#FFFBEB"),  # Royal Gold
    ("#475569", "#0F172A", "#F8FAFC"),  # Carbon Steel
    ("#BE123C", "#4C0519", "#FFF1F2"),  # Wine Red
]

# Dedicated premium palettes per color family to ensure color synchronization.
_COLOR_FAMILY_PALETTES = {
    "xanh_duong": [
        ("#1E3A8A", "#475569", "#F8FAFC"),  # Navy Steel
        ("#2563EB", "#1E293B", "#F1F5F9"),  # Royal Blue
        ("#06B6D4", "#0891B2", "#F0FDFA"),  # Cyan Tech
        ("#D97706", "#1E3A8A", "#F8FAFC"),  # Gold & Navy
        ("#0F172A", "#38BDF8", "#F8FAFC"),  # Midnight & Sky
    ],
    "xanh_la": [
        ("#10B981", "#D97706", "#F0FDF4"),  # Emerald Gold
        ("#065F46", "#34D399", "#ECFDF5"),  # Forest & Mint
        ("#059669", "#10B981", "#F0FDF4"),  # Mint Tech
        ("#064E3B", "#374151", "#F3F4F6"),  # Dark Green Carbon
        ("#3F6212", "#65A30D", "#F7FEE7"),  # Lime Olive
    ],
    "vang": [
        ("#D97706", "#1F2937", "#FFFBEB"),  # Royal Gold & Charcoal
        ("#B45309", "#78350F", "#FFFBEB"),  # Bronze & Copper
        ("#EA580C", "#475569", "#FFF7ED"),  # Amber Sunset
        ("#F59E0B", "#9A3412", "#FEF3C7"),  # Golden Honey
        ("#D97706", "#1E293B", "#FAFAFA"),  # Champagne Slate
    ],
    "do": [
        ("#DC2626", "#475569", "#FEF2F2"),  # Crimson & Slate
        ("#991B1B", "#111827", "#FFF5F5"),  # Wine & Charcoal
        ("#E11D48", "#FDA4AF", "#FFF1F2"),  # Rose Gold
        ("#BE123C", "#1F2937", "#FFF1F2"),  # Ruby & Carbon
        ("#881337", "#4C0519", "#FFF1F2"),  # Burgundy Ivory
    ],
    "den": [
        ("#374151", "#1F2937", "#F9FAFB"),  # Titanium Slate
        ("#475569", "#0F172A", "#F8FAFC"),  # Slate Steel & Matte Black
        ("#6B7280", "#111827", "#F9FAFB"),  # Carbon Silver
        ("#1E293B", "#475569", "#F1F5F9"),  # Matte Obsidian
        ("#000000", "#374151", "#FFFFFF"),  # Pure Monolith
    ],
    "ghi": [
        ("#475569", "#1E293B", "#F8FAFC"),  # Slate Carbon
        ("#6B7280", "#374151", "#F9FAFB"),  # Brushed Steel
        ("#374151", "#1E293B", "#F3F4F6"),  # Metallic Graphene
        ("#94A3B8", "#1E293B", "#F8FAFC"),  # Silver Blue
        ("#475569", "#0F172A", "#F8FAFC"),  # Dark Silver
    ],
    "teal": [
        ("#0D9488", "#475569", "#F0FDFA"),  # Teal Silver
        ("#0F766E", "#06B6D4", "#ECFDF5"),  # Deep Turquoise
        ("#115E59", "#C2410C", "#F0FDFA"),  # Teal Terracotta
        ("#14B8A6", "#047857", "#F0FDFA"),  # Minty Sage
        ("#0F766E", "#D97706", "#F0FDFA"),  # Gold Teal
    ],
    "tim": [
        ("#7E22CE", "#475569", "#FAF5FF"),  # Violet Silver
        ("#581C87", "#111827", "#FAF5FF"),  # Dark Plum
        ("#6366F1", "#1E293B", "#EEF2FF"),  # Indigo Tech
        ("#A855F7", "#4A044E", "#FAF5FF"),  # Lavender Purple
        ("#3B0764", "#7E22CE", "#FAFAFA"),  # Amethyst Gold
    ]
}


def generate_logo_variants(
    session_id: str,
    profile: DealerProfileRaw,
    *,
    output_root: Path | None = None,
    url_prefix: str = "/static/generated-logos",
    progress_callback: Callable[[int], None] | None = None,
) -> list[LogoVariant]:
    """Write three exact-text SVG concepts, optionally backed by AI emblems."""
    if profile.brandkit_consent != "yes":
        return []

    safe_session_id = _safe_slug(session_id, fallback="session")
    folder = (output_root or DEFAULT_OUTPUT_ROOT) / safe_session_id
    folder.mkdir(parents=True, exist_ok=True)

    brand_name = (profile.dealer_name or "Cửa hàng của anh").strip()
    initials = _select_initials(profile, brand_name)
    slogan = _select_slogan(profile)
    palettes = _select_palettes(profile.color_accent)
    style_preference = _display_preference(profile.logo_style)
    specs = [
        (
            "monogram-frame",
            "Khung monogram",
            "a balanced monogram inside a clean framing shape",
            _svg_monogram_frame,
        ),
        (
            "wordmark-block",
            "Wordmark khối",
            "a compact emblem that pairs naturally with a strong wordmark",
            _svg_wordmark_block,
        ),
        (
            "premium-mark",
            "Biểu trưng tinh gọn",
            "a refined standalone emblem with a clear premium silhouette",
            _svg_premium_mark,
        ),
    ]

    # Map product category to a compact emblem prompt description.
    product_str = (profile.main_product or "").strip().lower()
    if any(k in product_str for k in ["tủ bếp", "tu bep", "bếp", "bep", "nội thất", "cabinet"]):
        main_product_en = "premium modular kitchen cabinets and high-end wooden kitchen furniture"
    elif any(k in product_str for k in ["cửa cuốn", "rolling door"]):
        main_product_en = "high-end automated rolling shutters and security rolling doors"
    elif any(k in product_str for k in ["cửa thép", "cua thep", "steel door"]):
        main_product_en = "steel doors and secure architectural entry systems"
    elif any(k in product_str for k in ["cửa gỗ", "cua go", "wood door"]):
        main_product_en = "premium wooden doors and crafted wooden entry systems"
    elif any(k in product_str for k in ["điện mặt trời", "dien mat troi", "solar"]):
        main_product_en = "solar energy installation and clean energy systems"
    elif any(k in product_str for k in ["kính", "facade", "glass"]):
        main_product_en = "premium structural glass facades, partitions, and architectural glass solutions"
    else:
        main_product_en = "high-end aluminum glass doors, premium windows, and architectural glass partitions"

    # Get settings to fetch GEMINI_API_KEY
    from app.core.config_v2 import get_settings
    settings = get_settings()
    api_key = settings.gemini_api_key
    generation_mode = (
        "local"
        if output_root is not None
        else (settings.logo_provider or "local").strip().lower()
    )
    image_client = None
    if api_key and generation_mode == "hybrid":
        try:
            from google import genai

            image_client = genai.Client(api_key=api_key)
        except Exception:
            logger.exception("Logo image client init failed; using local SVG fallback")

    variants: list[LogoVariant] = []
    for index, (slug, name, composition, renderer) in enumerate(specs):
        primary, secondary, background = palettes[index]
        success = False
        filename = ""
        url = ""

        if image_client is not None:
            try:
                from google.genai import types

                logger.info(
                    "Generating emblem option %s using %s",
                    index + 1,
                    settings.logo_image_model,
                )
                response = image_client.models.generate_images(
                    model=settings.logo_image_model,
                    prompt=_build_emblem_prompt(
                        industry=main_product_en,
                        concept=composition,
                        logo_style=style_preference or "clean professional",
                        primary=primary,
                        secondary=secondary,
                    ),
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/png",
                        aspect_ratio="1:1",
                    )
                )

                if response.generated_images:
                    image_bytes = response.generated_images[0].image.image_bytes
                    if not image_bytes:
                        raise ValueError("Imagen returned empty image bytes")
                    emblem_filename = f"{index + 1:02d}-{slug}-emblem.png"
                    (folder / emblem_filename).write_bytes(image_bytes)
                    filename = f"{index + 1:02d}-{slug}.svg"
                    svg = _svg_hybrid_layout(
                        emblem_bytes=image_bytes,
                        brand_name=brand_name,
                        initials=initials,
                        slogan=slogan,
                        primary=primary,
                        secondary=secondary,
                        background=background,
                        style_preference=style_preference,
                    )
                    (folder / filename).write_text(svg, encoding="utf-8")
                    url = f"{url_prefix}/{quote(safe_session_id)}/{quote(filename)}"
                    success = True
                else:
                    logger.warning("Imagen returned no emblem for option %s", index + 1)
            except Exception:
                logger.exception("Imagen emblem generation failed for option %s", index + 1)

        # Fallback to local SVG generator if Imagen failed or local mode is active.
        if not success:
            logger.info("Using local SVG fallback for option %s", index + 1)
            svg = renderer(
                brand_name=brand_name,
                initials=initials,
                slogan=slogan,
                primary=primary,
                secondary=secondary,
                background=background,
                style_preference=style_preference,
            )
            filename = f"{index + 1:02d}-{slug}.svg"
            (folder / filename).write_text(svg, encoding="utf-8")
            url = f"{url_prefix}/{quote(safe_session_id)}/{quote(filename)}"

        variants.append(
            LogoVariant(
                id=f"{safe_session_id}-{index + 1}",
                name=f"Mẫu {index + 1}: {name}",
                style=style_preference or "Phù hợp ngành nghề",
                url=url,
                download_url=url,
            )
        )
        if progress_callback is not None:
            progress_callback(index + 1)
    return variants


def _select_initials(profile: DealerProfileRaw, brand_name: str) -> str:
    requested = (profile.logo_initials or "").strip()
    if requested and requested.casefold() != "auto":
        cleaned = re.sub(r"[^A-Za-zÀ-ỹ0-9]", "", requested, flags=re.UNICODE)
        if cleaned:
            return cleaned[:6].upper()
    return (profile.initials_full or gen_initials_full(brand_name) or "CH")[:6].upper()


def _select_slogan(profile: DealerProfileRaw) -> str:
    requested = (profile.slogan_preference or "").strip()
    if requested and requested.casefold() != "auto":
        return requested[:72]
    if profile.slogan_options:
        return str(profile.slogan_options[0])[:72]
    return "Vững chất lượng, bền niềm tin"


def _select_palettes(color_accent: str | None) -> list[tuple[str, str, str]]:
    if not color_accent:
        return _DEFAULT_PALETTES
        
    folded = _fold_vn(color_accent)
    
    if "duong" in folded or "lam" in folded or "navy" in folded or "bien" in folded:
        family = "xanh_duong"
    elif "la" in folded or "cay" in folded or "emerald" in folded or "luc" in folded:
        family = "xanh_la"
    elif "teal" in folded or "ngoc" in folded or "lam" in folded:
        family = "teal"
    elif "xanh" in folded:
        family = "xanh_duong"
    elif "vang" in folded or "gold" in folded or "hoang kim" in folded or "kim" in folded:
        family = "vang"
    elif "cam" in folded or "orange" in folded:
        family = "vang"
    elif "do" in folded or "crimson" in folded or "ruou" in folded:
        family = "do"
    elif "den" in folded or "charcoal" in folded or "toi" in folded:
        family = "den"
    elif "ghi" in folded or "xam" in folded or "silver" in folded or "bac" in folded:
        family = "ghi"
    elif "tim" in folded or "purple" in folded:
        family = "tim"
    else:
        return _DEFAULT_PALETTES
        
    return _COLOR_FAMILY_PALETTES[family]


def _display_preference(style: str | None) -> str:
    value = (style or "").strip()
    return "" if not value or value.casefold() == "auto" else value[:48]


def _build_emblem_prompt(
    *,
    industry: str,
    concept: str,
    logo_style: str,
    primary: str,
    secondary: str,
) -> str:
    """Ask Imagen for artwork only; exact text is composed locally."""
    return (
        f"Create one clean flat vector-style brand emblem for a Vietnamese {industry} dealer. "
        f"Concept: {concept}. Brand personality: {logo_style}. "
        f"Palette direction: {_human_palette(primary, secondary)}. "
        "No letters, no words, no numbers, no typography, no color codes, no watermark, no mockup. "
        "Centered emblem only, solid white background, 1:1 composition."
    )


def _human_palette(primary: str, secondary: str) -> str:
    """Keep color codes out of Imagen prompts so they cannot appear in artwork."""
    names = {
        "#1E3A8A": "navy blue",
        "#2563EB": "royal blue",
        "#06B6D4": "cyan blue",
        "#38BDF8": "sky blue",
        "#10B981": "emerald green",
        "#065F46": "forest green",
        "#059669": "jade green",
        "#064E3B": "deep green",
        "#3F6212": "olive green",
        "#65A30D": "leaf green",
        "#D97706": "warm gold",
        "#B45309": "bronze",
        "#EA580C": "amber orange",
        "#F59E0B": "honey gold",
        "#DC2626": "crimson red",
        "#991B1B": "wine red",
        "#E11D48": "rose red",
        "#BE123C": "ruby red",
        "#881337": "burgundy",
        "#0D9488": "teal",
        "#0F766E": "deep teal",
        "#14B8A6": "mint teal",
        "#7E22CE": "violet",
        "#581C87": "deep plum",
        "#6366F1": "indigo",
        "#A855F7": "lavender purple",
        "#3B0764": "amethyst",
        "#475569": "slate gray",
        "#374151": "charcoal gray",
        "#1F2937": "charcoal",
        "#0F172A": "near-black slate",
        "#111827": "near black",
    }
    return f"{names.get(primary, 'restrained primary color')} with {names.get(secondary, 'neutral secondary color')}"


def _svg_hybrid_layout(
    *,
    emblem_bytes: bytes,
    brand_name: str,
    initials: str,
    slogan: str,
    primary: str,
    secondary: str,
    background: str,
    style_preference: str,
) -> str:
    """Compose deterministic text around an AI-generated emblem."""
    encoded = b64encode(emblem_bytes).decode("ascii")
    body = f"""
<image href="data:image/png;base64,{encoded}" x="210" y="24" width="220" height="220" preserveAspectRatio="xMidYMid meet"/>
<text x="320" y="285" text-anchor="middle" fill="{_text(primary)}" font-family="Arial" font-size="31" font-weight="800">{_text(brand_name)}</text>
<text x="320" y="325" text-anchor="middle" fill="{_text(secondary)}" font-family="Arial" font-size="17" font-weight="700">{_text(initials)}</text>
<text x="320" y="362" text-anchor="middle" fill="{_text(secondary)}" font-family="Arial" font-size="14" font-weight="600">{_text(slogan)}</text>
{_style_note(style_preference)}"""
    return _base_svg(
        body,
        background=background,
        primary=primary,
        secondary=secondary,
    )


def _safe_slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value or "").strip("-_")
    return slug[:80] or fallback


def _fold_vn(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _text(value: str) -> str:
    return escape(value, quote=True)


def _base_svg(body: str, *, background: str, primary: str, secondary: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="440" viewBox="0 0 640 440" role="img">\n'
        '  <defs>\n'
        '    <!-- Premium Drop Shadow Filter -->\n'
        '    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">\n'
        '      <feDropShadow dx="3" dy="5" stdDeviation="4" flood-color="#000000" flood-opacity="0.2"/>\n'
        '    </filter>\n'
        '    <!-- Primary Linear Gradient -->\n'
        '    <linearGradient id="grad-primary" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        f'      <stop offset="0%" stop-color="{primary}"/>\n'
        f'      <stop offset="100%" stop-color="{secondary}"/>\n'
        '    </linearGradient>\n'
        '    <!-- Secondary Linear Gradient -->\n'
        '    <linearGradient id="grad-secondary" x1="0%" y1="0%" x2="0%" y2="100%">\n'
        f'      <stop offset="0%" stop-color="{secondary}"/>\n'
        f'      <stop offset="100%" stop-color="{primary}"/>\n'
        '    </linearGradient>\n'
        '  </defs>\n'
        f'  <rect width="640" height="440" fill="{background}"/>\n'
        f"  {body}\n"
        '</svg>\n'
    )


def _style_note(style_preference: str) -> str:
    if not style_preference:
        return ""
    return f'<text x="320" y="410" text-anchor="middle" fill="#64748B" font-family="Arial" font-size="13" font-weight="bold" letter-spacing="1">{_text(style_preference)}</text>'


def _svg_monogram_frame(**data: str) -> str:
    body = f"""
<rect x="228" y="54" width="184" height="154" rx="16" fill="none" stroke="url(#grad-primary)" stroke-width="12" filter="url(#shadow)"/>
<path d="M254 176 L320 88 L386 176" fill="none" stroke="url(#grad-secondary)" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" filter="url(#shadow)"/>
<text x="320" y="148" text-anchor="middle" fill="url(#grad-primary)" font-family="Arial" font-size="44" font-weight="800" letter-spacing="1">{_text(data['initials'])}</text>
<text x="320" y="278" text-anchor="middle" fill="url(#grad-primary)" font-family="Arial" font-size="28" font-weight="800" letter-spacing="2">{_text(data['brand_name'])}</text>
<text x="320" y="318" text-anchor="middle" fill="url(#grad-secondary)" font-family="Arial" font-size="15" font-weight="600" letter-spacing="3">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"], primary=data["primary"], secondary=data["secondary"])


def _svg_door_line(**data: str) -> str:
    body = f"""
<path d="M245 208 V78 H382 V208" fill="none" stroke="url(#grad-secondary)" stroke-width="12" stroke-linejoin="round" filter="url(#shadow)"/>
<path d="M278 208 V112 H348 V208" fill="none" stroke="url(#grad-primary)" stroke-width="10" stroke-linejoin="round" filter="url(#shadow)"/>
<circle cx="330" cy="162" r="6" fill="url(#grad-primary)"/>
<text x="320" y="268" text-anchor="middle" fill="url(#grad-secondary)" font-family="Arial" font-size="30" font-weight="800" letter-spacing="2">{_text(data['brand_name'])}</text>
<text x="320" y="306" text-anchor="middle" fill="url(#grad-primary)" font-family="Arial" font-size="16" letter-spacing="4" font-weight="700">{_text(data['initials'])}</text>
<text x="320" y="344" text-anchor="middle" fill="url(#grad-secondary)" font-family="Arial" font-size="14" font-weight="600" letter-spacing="1">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"], primary=data["primary"], secondary=data["secondary"])


def _svg_industrial_badge(**data: str) -> str:
    body = f"""
<path d="M320 48 L418 102 L418 208 L320 262 L222 208 L222 102 Z" fill="url(#grad-secondary)" filter="url(#shadow)"/>
<path d="M320 70 L396 113 L396 196 L320 240 L244 196 L244 113 Z" fill="none" stroke="url(#grad-primary)" stroke-width="6"/>
<text x="320" y="174" text-anchor="middle" fill="#FFFFFF" font-family="Arial" font-size="52" font-weight="900" letter-spacing="2">{_text(data['initials'])}</text>
<text x="320" y="318" text-anchor="middle" fill="url(#grad-secondary)" font-family="Arial" font-size="28" font-weight="800" letter-spacing="2">{_text(data['brand_name'])}</text>
<text x="320" y="356" text-anchor="middle" fill="url(#grad-primary)" font-family="Arial" font-size="15" font-weight="600" letter-spacing="2">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"], primary=data["primary"], secondary=data["secondary"])


def _svg_wordmark_block(**data: str) -> str:
    body = f"""
<rect x="68" y="95" width="154" height="154" rx="16" fill="url(#grad-primary)" filter="url(#shadow)"/>
<text x="145" y="188" text-anchor="middle" fill="#FFFFFF" font-family="Arial" font-size="50" font-weight="900" letter-spacing="1">{_text(data['initials'])}</text>
<text x="260" y="156" fill="url(#grad-secondary)" font-family="Arial" font-size="30" font-weight="800" letter-spacing="2">{_text(data['brand_name'])}</text>
<rect x="260" y="176" width="310" height="6" fill="url(#grad-primary)"/>
<text x="260" y="222" fill="url(#grad-secondary)" font-family="Arial" font-size="15" font-weight="600" letter-spacing="1">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"], primary=data["primary"], secondary=data["secondary"])


def _svg_premium_mark(**data: str) -> str:
    body = f"""
<circle cx="320" cy="145" r="90" fill="none" stroke="url(#grad-primary)" stroke-width="6" filter="url(#shadow)"/>
<path d="M270 182 L320 86 L370 182 M292 142 H348" fill="none" stroke="url(#grad-secondary)" stroke-width="11" stroke-linecap="round" stroke-linejoin="round" filter="url(#shadow)"/>
<text x="320" y="174" text-anchor="middle" fill="url(#grad-primary)" font-family="Arial" font-size="26" font-weight="800" letter-spacing="1">{_text(data['initials'])}</text>
<text x="320" y="292" text-anchor="middle" fill="url(#grad-secondary)" font-family="Arial" font-size="28" font-weight="800" letter-spacing="2">{_text(data['brand_name'])}</text>
<text x="320" y="330" text-anchor="middle" fill="url(#grad-primary)" font-family="Arial" font-size="15" font-weight="600" letter-spacing="2">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"], primary=data["primary"], secondary=data["secondary"])

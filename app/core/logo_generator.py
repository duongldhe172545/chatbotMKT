"""Generate five local SVG logo concepts for a confirmed dealer.

This is the deterministic MVP renderer. It keeps the end-to-end flow usable
without a second image-model API key. A later image generator can replace this
module while preserving the API response contract.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel

from app.llm.auto_derive import gen_initials_full
from app.models.schema import DealerProfileRaw


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "static" / "generated-logos"


class LogoVariant(BaseModel):
    id: str
    name: str
    style: str
    url: str
    download_url: str


_DEFAULT_PALETTE = [
    ("#0F766E", "#134E4A", "#ECFDF5"),
    ("#1D4ED8", "#172554", "#EFF6FF"),
    ("#B45309", "#7C2D12", "#FFFBEB"),
    ("#374151", "#111827", "#F9FAFB"),
    ("#BE123C", "#4C0519", "#FFF1F2"),
]
_COLOR_MAP = {
    "xanh": ("#0F766E", "#134E4A", "#ECFDF5"),
    "xanh duong": ("#1D4ED8", "#172554", "#EFF6FF"),
    "xanh la": ("#15803D", "#14532D", "#F0FDF4"),
    "do": ("#BE123C", "#4C0519", "#FFF1F2"),
    "cam": ("#C2410C", "#7C2D12", "#FFF7ED"),
    "vang": ("#A16207", "#713F12", "#FEFCE8"),
    "den": ("#374151", "#111827", "#F9FAFB"),
    "ghi": ("#475569", "#1E293B", "#F8FAFC"),
    "tim": ("#7E22CE", "#3B0764", "#FAF5FF"),
}


def generate_logo_variants(
    session_id: str,
    profile: DealerProfileRaw,
    *,
    output_root: Path | None = None,
    url_prefix: str = "/static/generated-logos",
) -> list[LogoVariant]:
    """Write five distinct SVG concepts and return browser-ready metadata."""
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
        ("monogram-frame", "Khung monogram", "Hình học chắc chắn", _svg_monogram_frame),
        ("door-line", "Nét cửa hiện đại", "Tối giản hiện đại", _svg_door_line),
        ("industrial-badge", "Huy hiệu xưởng", "Công nghiệp mạnh mẽ", _svg_industrial_badge),
        ("wordmark-block", "Wordmark khối", "Chữ khối dễ nhận diện", _svg_wordmark_block),
        ("premium-mark", "Biểu trưng tinh gọn", "Tinh gọn cao cấp", _svg_premium_mark),
    ]

    variants: list[LogoVariant] = []
    for index, (slug, name, style, renderer) in enumerate(specs):
        primary, secondary, background = palettes[index]
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
                style=style,
                url=url,
                download_url=url,
            )
        )
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
    folded = _fold_vn(color_accent or "")
    preferred = next((value for key, value in _COLOR_MAP.items() if key in folded), None)
    if not preferred:
        return list(_DEFAULT_PALETTE)
    return [preferred, *_DEFAULT_PALETTE[:4]]


def _display_preference(style: str | None) -> str:
    value = (style or "").strip()
    return "" if not value or value.casefold() == "auto" else value[:48]


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


def _base_svg(body: str, *, background: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="440" '
        'viewBox="0 0 640 440" role="img">\n'
        f'<rect width="640" height="440" fill="{background}"/>\n'
        f"{body}\n"
        "</svg>\n"
    )


def _style_note(style_preference: str) -> str:
    if not style_preference:
        return ""
    return f'<text x="320" y="410" text-anchor="middle" fill="#64748B" font-family="Arial" font-size="13">{_text(style_preference)}</text>'


def _svg_monogram_frame(**data: str) -> str:
    body = f"""
<rect x="228" y="54" width="184" height="154" rx="12" fill="none" stroke="{data['primary']}" stroke-width="16"/>
<path d="M254 176 L320 88 L386 176" fill="none" stroke="{data['secondary']}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
<text x="320" y="156" text-anchor="middle" fill="{data['primary']}" font-family="Arial" font-size="50" font-weight="700">{_text(data['initials'])}</text>
<text x="320" y="272" text-anchor="middle" fill="{data['secondary']}" font-family="Arial" font-size="31" font-weight="700">{_text(data['brand_name'])}</text>
<text x="320" y="310" text-anchor="middle" fill="{data['primary']}" font-family="Arial" font-size="17">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"])


def _svg_door_line(**data: str) -> str:
    body = f"""
<path d="M245 208 V78 H382 V208" fill="none" stroke="{data['secondary']}" stroke-width="14" stroke-linejoin="round"/>
<path d="M278 208 V112 H348 V208" fill="none" stroke="{data['primary']}" stroke-width="12"/>
<circle cx="330" cy="162" r="7" fill="{data['primary']}"/>
<text x="320" y="262" text-anchor="middle" fill="{data['secondary']}" font-family="Arial" font-size="34" font-weight="700">{_text(data['brand_name'])}</text>
<text x="320" y="302" text-anchor="middle" fill="{data['primary']}" font-family="Arial" font-size="18" letter-spacing="2">{_text(data['initials'])}</text>
<text x="320" y="342" text-anchor="middle" fill="{data['secondary']}" font-family="Arial" font-size="16">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"])


def _svg_industrial_badge(**data: str) -> str:
    body = f"""
<path d="M320 48 L418 102 L418 208 L320 262 L222 208 L222 102 Z" fill="{data['secondary']}"/>
<path d="M320 70 L396 113 L396 196 L320 240 L244 196 L244 113 Z" fill="none" stroke="{data['primary']}" stroke-width="8"/>
<text x="320" y="178" text-anchor="middle" fill="#FFFFFF" font-family="Arial" font-size="58" font-weight="700">{_text(data['initials'])}</text>
<text x="320" y="316" text-anchor="middle" fill="{data['secondary']}" font-family="Arial" font-size="31" font-weight="700">{_text(data['brand_name'])}</text>
<text x="320" y="352" text-anchor="middle" fill="{data['primary']}" font-family="Arial" font-size="16">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"])


def _svg_wordmark_block(**data: str) -> str:
    body = f"""
<rect x="68" y="95" width="154" height="154" rx="8" fill="{data['primary']}"/>
<text x="145" y="190" text-anchor="middle" fill="#FFFFFF" font-family="Arial" font-size="54" font-weight="700">{_text(data['initials'])}</text>
<text x="260" y="160" fill="{data['secondary']}" font-family="Arial" font-size="34" font-weight="700">{_text(data['brand_name'])}</text>
<rect x="260" y="181" width="286" height="8" fill="{data['primary']}"/>
<text x="260" y="229" fill="{data['secondary']}" font-family="Arial" font-size="17">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"])


def _svg_premium_mark(**data: str) -> str:
    body = f"""
<circle cx="320" cy="145" r="90" fill="none" stroke="{data['primary']}" stroke-width="8"/>
<path d="M270 182 L320 86 L370 182 M292 142 H348" fill="none" stroke="{data['secondary']}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
<text x="320" y="178" text-anchor="middle" fill="{data['primary']}" font-family="Arial" font-size="30" font-weight="700">{_text(data['initials'])}</text>
<text x="320" y="288" text-anchor="middle" fill="{data['secondary']}" font-family="Arial" font-size="32" font-weight="700">{_text(data['brand_name'])}</text>
<text x="320" y="328" text-anchor="middle" fill="{data['primary']}" font-family="Arial" font-size="16">{_text(data['slogan'])}</text>
{_style_note(data['style_preference'])}"""
    return _base_svg(body, background=data["background"])


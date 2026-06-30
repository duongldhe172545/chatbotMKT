"""9.4b — Kho MẪU THAM KHẢO brandkit (logo + namecard) + matching.

Nghiệp vụ (sếp chốt 2026-06-17):
- Kho gồm các bộ mẫu (logo + danh thiếp) kèm mô tả màu / phong cách / ngành.
- Khi khách xem: CHƯA biết màu/phong cách → show vài mẫu ngẫu nhiên; ĐÃ biết →
  show mẫu GẦN KHỚP NHẤT.

⚠️ Đây là MẪU THAM KHẢO PHONG CÁCH, KHÔNG phải logo cuối của khách. Ảnh hiện tại là
PLACEHOLDER (SVG) do code seed — admin thay ảnh designer thật sau (giữ nguyên metadata).
"""
from __future__ import annotations

import random
import unicodedata
from pathlib import Path
from typing import Any, Optional

_ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "brandkit_samples"
_URL_PREFIX = "/static/brandkit_samples"


def _norm(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# Mỗi mẫu: style/color = nhãn tiếng Việt hiển thị; *_kw = từ khoá (đã chuẩn hoá) để match.
# hex/hex2 = màu nền dùng vẽ SVG placeholder.
_SAMPLES: list[dict[str, Any]] = [
    {"id": "modern-blue", "style": "hiện đại", "style_kw": ["hien dai", "modern", "tre trung"],
     "color": "xanh dương", "color_kw": ["xanh", "blue", "xanh duong"],
     "industry": "nhôm kính / nội thất", "hex": "#1565C0", "hex2": "#42A5F5"},
    {"id": "luxury-gold", "style": "sang trọng", "style_kw": ["sang trong", "cao cap", "luxury", "dang cap"],
     "color": "đen – vàng kim", "color_kw": ["den", "vang", "gold", "vang kim"],
     "industry": "nội thất cao cấp", "hex": "#1A1A1A", "hex2": "#C9A227"},
    {"id": "minimal-white", "style": "tối giản", "style_kw": ["toi gian", "minimal", "don gian", "gon"],
     "color": "trắng – xám", "color_kw": ["trang", "xam", "white", "grey", "gray"],
     "industry": "thiết kế / dịch vụ", "hex": "#FAFAFA", "hex2": "#9E9E9E"},
    {"id": "bold-red", "style": "mạnh mẽ", "style_kw": ["manh me", "bold", "ca tinh", "manh"],
     "color": "đỏ", "color_kw": ["do", "red", "do tuoi"],
     "industry": "cơ khí / xây dựng", "hex": "#C62828", "hex2": "#EF5350"},
    {"id": "fresh-green", "style": "hiện đại", "style_kw": ["hien dai", "modern", "tuoi sang"],
     "color": "xanh lá", "color_kw": ["xanh la", "green", "xanh"],
     "industry": "năng lượng / điện mặt trời", "hex": "#2E7D32", "hex2": "#66BB6A"},
    {"id": "elegant-navy", "style": "sang trọng", "style_kw": ["sang trong", "thanh lich", "elegant"],
     "color": "xanh navy", "color_kw": ["navy", "xanh", "xanh tham"],
     "industry": "nội thất", "hex": "#0D2A4A", "hex2": "#3F6CA8"},
]


def _public(sample: dict[str, Any]) -> dict[str, Any]:
    """Bản gọn trả ra FE (không lộ keyword nội bộ)."""
    return {
        "id": sample["id"],
        "style": sample["style"],
        "color": sample["color"],
        "industry": sample["industry"],
        "logo_url": f"{_URL_PREFIX}/{sample['id']}-logo.svg",
        "namecard_url": f"{_URL_PREFIX}/{sample['id']}-namecard.svg",
        "caption": f"Phong cách {sample['style']}, tông {sample['color']}",
    }


def _score(sample: dict[str, Any], style_n: str, color_n: str) -> float:
    s = 0.0
    if style_n and any(kw in style_n or style_n in kw for kw in sample["style_kw"]):
        s += 2.0
    if color_n and any(kw in color_n or color_n in kw for kw in sample["color_kw"]):
        s += 1.0
    return s


def pick_samples(
    color: Optional[str] = None,
    style: Optional[str] = None,
    industry: Optional[str] = None,
    n: int = 3,
    rng: Optional[random.Random] = None,
) -> list[dict[str, Any]]:
    """Chọn n mẫu: biết phong cách/màu → gần khớp nhất; chưa biết → ngẫu nhiên.

    KHÔNG bao giờ trả rỗng nếu kho có mẫu (fallback ngẫu nhiên)."""
    rng = rng or random
    if not _SAMPLES:
        return []
    style_n, color_n = _norm(style or ""), _norm(color or "")
    scored = [(s, _score(s, style_n, color_n)) for s in _SAMPLES]
    matched = [s for s, sc in scored if sc > 0]
    if matched:
        matched.sort(key=lambda s: _score(s, style_n, color_n), reverse=True)
        return [_public(s) for s in matched[:n]]
    # Chưa biết / không khớp → ngẫu nhiên (fallback an toàn)
    pool = list(_SAMPLES)
    rng.shuffle(pool)
    return [_public(s) for s in pool[:n]]


# ============================================================
# Seed ảnh PLACEHOLDER (SVG) — chạy 1 lần để luồng render được
# ============================================================
def _logo_svg(s: dict[str, Any]) -> str:
    fg = "#FFFFFF" if s["id"] != "minimal-white" else "#333333"
    initials = "".join(w[0] for w in s["industry"].replace("/", " ").split()[:2]).upper() or "AB"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">'
        f'<rect width="400" height="400" fill="{s["hex"]}"/>'
        f'<circle cx="200" cy="160" r="90" fill="{s["hex2"]}"/>'
        f'<text x="200" y="180" font-family="Arial,sans-serif" font-size="72" font-weight="bold" '
        f'fill="{fg}" text-anchor="middle">{initials}</text>'
        f'<text x="200" y="300" font-family="Arial,sans-serif" font-size="26" '
        f'fill="{fg}" text-anchor="middle">MẪU THAM KHẢO</text>'
        f'<text x="200" y="340" font-family="Arial,sans-serif" font-size="20" '
        f'fill="{fg}" text-anchor="middle" opacity="0.85">{s["style"]}</text>'
        f'</svg>'
    )


def _namecard_svg(s: dict[str, Any]) -> str:
    fg = "#FFFFFF" if s["id"] != "minimal-white" else "#333333"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="340" viewBox="0 0 600 340">'
        f'<rect width="600" height="340" fill="{s["hex"]}"/>'
        f'<rect x="0" y="0" width="14" height="340" fill="{s["hex2"]}"/>'
        f'<circle cx="500" cy="90" r="55" fill="{s["hex2"]}" opacity="0.9"/>'
        f'<text x="48" y="120" font-family="Arial,sans-serif" font-size="40" font-weight="bold" '
        f'fill="{fg}">TÊN CỬA HÀNG</text>'
        f'<text x="48" y="165" font-family="Arial,sans-serif" font-size="22" '
        f'fill="{fg}" opacity="0.85">{s["industry"]}</text>'
        f'<text x="48" y="250" font-family="Arial,sans-serif" font-size="20" '
        f'fill="{fg}" opacity="0.8">📞 0900 000 000  ·  ✉ shop@example.com</text>'
        f'<text x="48" y="290" font-family="Arial,sans-serif" font-size="18" '
        f'fill="{fg}" opacity="0.7">Danh thiếp mẫu — phong cách {s["style"]}</text>'
        f'</svg>'
    )


def generate_placeholder_assets(force: bool = False) -> int:
    """Sinh file SVG placeholder cho mọi mẫu (nếu chưa có). Trả số file đã ghi."""
    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for s in _SAMPLES:
        for suffix, builder in (("logo", _logo_svg), ("namecard", _namecard_svg)):
            path = _ASSET_DIR / f"{s['id']}-{suffix}.svg"
            if force or not path.exists():
                path.write_text(builder(s), encoding="utf-8")
                written += 1
    return written


if __name__ == "__main__":
    print(f"Wrote {generate_placeholder_assets(force=True)} SVG placeholder files to {_ASSET_DIR}")

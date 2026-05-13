"""Lookup tỉnh/thành VN → đặc sản nổi tiếng — phục vụ greeting/closing hook v7.

Trong Turn 1.3 v7, bot nhận diện tỉnh từ address của dealer → "khen" đặc sản
địa phương để tạo cảm giác am hiểu local (vd Cao Bằng → vịt quay 7 vị).

Coverage 30 tỉnh phổ biến đầu — đủ cho demo + ~80% dealer thực. Tỉnh không
trong list → trả None → bot vào thẳng câu hỏi, không bịa đặc sản.
"""
from __future__ import annotations

import re
import unicodedata

# Map: normalized province name (no diacritic, lower) → đặc sản phrase
_PROVINCE_SPECIALTY: dict[str, str] = {
    # Bắc Bộ
    "ha noi": "phở Bát Đàn với bún chả Hàng Mành",
    "hai phong": "bánh đa cua với nem cua bể",
    "quang ninh": "chả mực Hạ Long với sá sùng",
    "bac ninh": "bánh phu thê Đình Bảng",
    "thai nguyen": "trà Tân Cương",
    "phu tho": "thịt chua Thanh Sơn với cọ ỏm",
    "lao cai": "thắng cố Sapa với cá hồi",
    "yen bai": "xôi ngũ sắc với cốm Tú Lệ",
    "tuyen quang": "cam sành Hàm Yên",
    "ha giang": "thắng dền với mèn mén Đồng Văn",
    "cao bang": "vịt quay 7 vị với phở chua Cao Bằng",
    "bac kan": "miến dong Na Rì",
    "lang son": "vịt quay lá mác mật",
    "son la": "bê chao Mộc Châu",
    "dien bien": "thịt trâu gác bếp",
    "lai chau": "xôi tím Mường Lay",
    "hoa binh": "thịt lợn mán nướng",
    "ninh binh": "cơm cháy với dê núi Hoa Lư",
    "thanh hoa": "nem chua Thanh Hóa với chả tôm",
    # Trung Bộ
    "nghe an": "cháo lươn Vinh",
    "ha tinh": "cu đơ Hà Tĩnh",
    "quang binh": "bánh khoái với cháo canh",
    "quang tri": "bún hến với cháo lươn",
    "thua thien hue": "bún bò Huế với bánh bèo nậm lọc",
    "hue": "bún bò Huế với bánh bèo nậm lọc",
    "da nang": "mì Quảng với bún chả cá",
    "quang nam": "mì Quảng Phú Chiêm với cao lầu Hội An",
    "quang ngai": "don sông Trà với mạch nha",
    "binh dinh": "bún chả cá Quy Nhơn với bánh ít lá gai",
    "phu yen": "mắt cá ngừ đại dương",
    "khanh hoa": "bún cá Nha Trang với nem nướng Ninh Hòa",
    # Tây Nguyên
    "kon tum": "gỏi lá Kon Tum",
    "gia lai": "phở khô Gia Lai (phở hai tô)",
    "dak lak": "bún đỏ Ban Mê với cà phê Buôn Ma Thuột",
    "dak nong": "cà phê Đắk Nông",
    "lam dong": "bánh tráng nướng Đà Lạt với artichoke",
    # Nam Bộ
    "binh thuan": "gỏi cá mai Phan Thiết",
    "binh duong": "gỏi gà măng cụt Lái Thiêu",
    "dong nai": "gỏi bưởi Tân Triều",
    "vung tau": "bánh khọt Vũng Tàu",
    "ba ria vung tau": "bánh khọt Vũng Tàu",
    "ho chi minh": "cơm tấm Sài Gòn với hủ tiếu Nam Vang",
    "tp ho chi minh": "cơm tấm Sài Gòn với hủ tiếu Nam Vang",
    "sai gon": "cơm tấm Sài Gòn với hủ tiếu Nam Vang",
    # Đồng bằng sông Cửu Long
    "long an": "lẩu mắm với canh chua bông súng",
    "tien giang": "hủ tiếu Mỹ Tho",
    "ben tre": "kẹo dừa Bến Tre",
    "vinh long": "bún nước lèo Sóc Trăng",
    "tra vinh": "bánh canh Bến Có",
    "can tho": "bánh xèo Cần Thơ với lẩu cá kèo",
    "soc trang": "bún nước lèo với bánh pía",
    "an giang": "bún cá Châu Đốc với mắm Châu Đốc",
    "kien giang": "bún kèn Phú Quốc với cá trích",
    "ca mau": "tôm tích Cà Mau",
    "bac lieu": "bánh xèo tôm",
    "hau giang": "khóm Cầu Đúc",
}


def _normalize(s: str) -> str:
    """Bỏ dấu + lower + collapse whitespace để match lookup key."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def lookup_specialty(address: str | None) -> str | None:
    """Tìm đặc sản tỉnh từ address. Trả None nếu không match.

    Match: substring tên tỉnh trong address (normalized). Vd:
    - "Tổ 6, P. Duyệt Trung, TP. Cao Bằng, Tỉnh Cao Bằng" → "cao bang"
      → "vịt quay 7 vị với phở chua Cao Bằng"
    - "Hà Nội" → "ha noi" → "phở Bát Đàn..."
    - "Tỉnh Cần Thơ" → "can tho" → "bánh xèo Cần Thơ..."
    """
    if not address:
        return None
    norm = _normalize(address)
    if not norm:
        return None
    # Match longest key first để tránh "ha noi" match khi addr là "hai phong"
    for key in sorted(_PROVINCE_SPECIALTY, key=len, reverse=True):
        if key in norm:
            return _PROVINCE_SPECIALTY[key]
    return None

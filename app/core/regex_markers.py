"""7 intent markers regex patterns. Refer F2A.2 Layer 1.

Note: tất cả pattern dùng với re.IGNORECASE + re.UNICODE.
Message lowercase + strip trước khi match.

DISCLAIMER: marker là HINT, không exhaustive. Layer 2 LLM fallback bắt
case chưa cover (Phase 2+).
"""
from __future__ import annotations


# ============================================================
# AFFIRMATIVE — dealer xác nhận / OK
# ============================================================
AFFIRMATIVE_PATTERNS: list[str] = [
    # ok / oke / okê / ô kê
    r"\b(ok|okay|oke|okê|ô\s*kê|okie)\b",
    # được / chuẩn / đúng / đồng ý
    r"\b(được\s*r[ồô]i|được|chuẩn\s*r[ồô]i|chuẩn|đúng\s*r[ồô]i|đúng|đồng\s*ý)\b",
    # vâng / dạ vâng / ừ / ờ
    r"\b(vâng|dạ\s*vâng|ừ|ừm|ờ|ờm)\b",
    # affirmative tiếng Anh
    r"\b(good|yes|yeah|yep|right)\b",
    # 1 chữ ừ / ờ / dạ
    r"^[uưừ]+$",
    r"^(dạ|ừ|ờ|ok)\s*$",
]


# ============================================================
# REFUSAL — dealer rõ ràng từ chối
# ============================================================
REFUSAL_PATTERNS: list[str] = [
    # không cho / không nói / đéo cho
    r"\b(không\s*cho|đéo\s*cho|miễn|không\s*nói|không\s*thèm|không\s*muốn\s*nói)\b",
    # không muốn / chả muốn
    r"\b(không\s*muốn|chả\s*muốn|chẳng\s*muốn|đếch\s*muốn)\b",
    # kệ / bỏ qua / qua đi
    r"\b(kệ\s*đi|kệ\s*nó|bỏ\s*qua|qua\s*đi)\b",
    # tao đéo / không cần
    r"\b(tao\s*đéo|không\s*cần|đéo\s*cần)\b",
]


# ============================================================
# KHONG_BIET — không biết / không nhớ / tùy
# ============================================================
KHONG_BIET_PATTERNS: list[str] = [
    r"\b(không\s*bi[ếê]t|không\s*nh[ơớ]|chưa\s*biết|chưa\s*nhớ|chả\s*nhớ)\b",
    r"\b(tùy\s*em|tùy\s*anh|tùy\s*ý|sao\s*cũng\s*được)\b",
    r"\b(chưa\s*có|chưa\s*làm|chưa\s*tính)\b",
    r"\b(quên\s*mất|quên\s*r[ồô]i)\b",
]


# ============================================================
# DEFENSIVE — dealer hỏi ngược / nghi ngờ
# ============================================================
DEFENSIVE_PATTERNS: list[str] = [
    # lừa đảo / scam / phí gì
    r"\b(lừa\s*đảo|scam|phí\s*gì|tốn\s*tiền|chi\s*phí|miễn\s*phí\s*à)\b",
    # em là ai / ai làm
    r"\b(em\s*là\s*ai|anh\s*là\s*ai|ai\s*làm|ai\s*đứng\s*sau|công\s*ty\s*nào)\b",
    # làm gì / để làm gì / bán gì
    r"\b(làm\s*gì|để\s*làm\s*gì|bán\s*gì|bán\s*data|đem\s*bán)\b",
    # chứng minh / đảm bảo
    r"\b(chứng\s*minh|đảm\s*bảo|tin\s*được\s*không|sao\s*tin)\b",
    # data có an toàn không / có giấu không
    r"\b(an\s*toàn\s*không|có\s*giấu|có\s*lộ|bí\s*mật\s*không)\b",
]


# ============================================================
# TAM_SU — dealer kể chuyện đời / cảm xúc
# ============================================================
TAM_SU_PATTERNS: list[str] = [
    # gia đình
    r"\b(vợ|chồng|con|bố\s*mẹ|gia\s*đình|cha\s*mẹ)\b",
    # thời tiết / hôm nay
    r"\b(trời\s*mưa|trời\s*nắng|hôm\s*nay|hôm\s*qua|tuần\s*này\s*mệt)\b",
    # sức khỏe
    r"\b(stress|mệt\s*ghê|bệnh|ốm|đau\s*lưng|đau\s*đầu|nhức\s*đầu)\b",
    # nhậu / cà phê / golf
    r"\b(nhậu|cà\s*phê|cafe|golf|chơi\s*bóng|tennis)\b",
    # khó khăn kinh tế
    r"\b(dịch\s*bệnh|kinh\s*tế\s*khó|hết\s*tiền|đói|khó\s*khăn\s*quá)\b",
]


# ============================================================
# EDIT — sửa data (chỉ valid trong stage CONFIRMING)
# ============================================================
EDIT_PATTERNS: list[str] = [
    r"\b(sửa|đổi|chỉnh|sai\s*r[ồô]i|nhầm|nhập\s*sai)\b",
    r"^(không\s*phải|sai)\s",
    r"\b(phải\s*là|đúng\s*là|là\s*.+\s*chứ\s*không\s*phải)\b",
]

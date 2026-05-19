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
# Abuse cá nhân — dealer chửi/xúc phạm em Linh (≠ Lửa Lò chửi chung)
# Refer KICH_BAN_1C § 5.
# Phân biệt: "đm em hỏi nhiều" = Lửa Lò general profanity (em là dealer xưng)
#            "đm con bot này"  = personal abuse (nhằm bot Em Linh)
PERSONAL_ABUSE_PATTERNS: list[str] = [
    # Chửi bot cá nhân — KHÔNG match "em" tự do (em là dealer xưng)
    r"\b(đm|đụ|đéo|cmm)\s*(con\s*)?(bot|máy|con\s*này|robot|ai)\b",
    # "bot/em ngu/chó/vl" — gắn đuôi xúc phạm (em ngu = đụ em Linh)
    r"\bbot\s+(ngu|chó|đần|khùng|điên|vl|vcl|cl|cc)\b",
    r"\bem\s+(ngu|chó|đần|khùng|điên|vl|vcl)\s*(vl|vcl|cl|cc|quá|thế)?\s*$",
    # Bảo bot im
    r"\b(câm\s*mồm|câm\s*đi|im\s*mồm|im\s*đi|biến\s*đi)\b",
    # Xúc phạm máy / robot
    r"\b(đồ\s*máy|máy\s*nhân\s*tạo|con\s*máy|đồ\s*robot)\b",
    # Chửi "con X" — phải có context bot
    r"\b(con\s*bot|bot\s*chó|bot\s*điên|bot\s*khùng)\b",
]


DEFENSIVE_PATTERNS: list[str] = [
    # lừa đảo / scam / phí gì
    r"\b(lừa\s*đảo|scam|phí\s*gì|tốn\s*tiền|chi\s*phí\s*gì|miễn\s*phí\s*à)\b",
    # em là ai / ai làm — defensive về danh tính bot
    r"\b(em\s*là\s*ai|anh\s*là\s*ai|ai\s*đứng\s*sau|công\s*ty\s*nào)\b",
    # "X làm gì" — chỉ defensive khi chủ ngữ là bot/em/bên/cty (tránh
    # false positive câu kể "anh không nhớ đã làm gì cho khách")
    r"\b(bên\s*(em|này|đó)\s*làm\s*gì|em\s*làm\s*gì\s*(ở\s*đây|với|cho\s*anh)|"
    r"ai\s*làm\s*(việc\s*này|cái\s*này)|công\s*ty\s*(em\s*)?làm\s*gì)\b",
    # bán data / đem bán — luôn defensive
    r"\b(bán\s*data|đem\s*bán|tuồn\s*ra|lộ\s*ra\s*ngoài)\b",
    # chứng minh / đảm bảo
    r"\b(chứng\s*minh\s*đi|đảm\s*bảo\s*(đi|gì)|tin\s*được\s*không|sao\s*tin)\b",
    # data có an toàn không / có giấu không / có lộ không
    r"\b(an\s*toàn\s*không|có\s*giấu|có\s*lộ\s*(thông\s*tin|số|data|ra)?\s*(không|kh|ko)?|bí\s*mật\s*không)\b",
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

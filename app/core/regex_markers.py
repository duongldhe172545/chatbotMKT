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
    # vâng / dạ vâng
    r"\b(vâng|dạ\s*vâng)\b",
    # affirmative tiếng Anh
    r"\b(good|yes|yeah|yep|right)\b",
    # Short/standalone confirmations only (prevents matching starting filler words in long sentences like "ờ anh thích màu vàng nhé")
    r"^[uưừ]+$",
    r"^(dạ|ừ|ừa|ừm|ờ|ò|ờm|ok)\s*(ạ|nhé|nha|em|bot|ơi)?\s*$",
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
    # Phase 6 R+ Fix Lỗi 1: profanity + verb từ chối (vd "đéo nói", "đéo cho biết")
    r"\b(đéo|đếch|đếk|đ\*?o)\s*(nói|kể|cho\s*biết|trả\s*lời|nhắc|share)\b",
    # "không thích nói", "không tiện chia sẻ", "không trả lời"
    r"\b(không|kh|ko|chả|chẳng)\s*(thích\s*nói|tiện|chia\s*sẻ|trả\s*lời|nhắc|kể)\b",
    # cụt "thôi đi", "thôi đừng", "bỏ đi"
    r"\b(thôi\s*đi|thôi\s*đừng|đừng\s*hỏi|đừng\s*hỏi\s*nữa|bỏ\s*đi\s*em)\b",
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
# CONFUSION — dealer KHÔNG hiểu câu hỏi / thuật ngữ bot vừa dùng
# CORE D.1 — bot CHỦ ĐỘNG giải thích khi dealer hỏi "là gì/là sao"
# Phase 6 R+ fix 2026-05-22: thêm intent này (trước đó "là sao?" fall
# về NORMAL → bot skip slot, không giải thích).
# ============================================================
CONFUSION_PATTERNS: list[str] = [
    # "là gì" / "là sao" — câu hỏi cốt lõi của CORE D.1
    r"\b(là\s*g[ìi]|là\s*sao|nghĩa\s*là\s*g[ìi]|nghĩa\s*là\s*sao)\b",
    # "ý gì" / "ý em là gì" / "ý anh"
    r"\b(ý\s*(em|anh|chị|n[óo])\s*(là\s*)?(g[ìi]|sao))\b",
    r"\b(ý\s*g[ìi]\s*c[ơơ])\b",
    # "cái gì/cái đó là gì"
    r"\b(cái\s*(này|đó|nào)\s*(là\s*)?(g[ìi]|sao))\b",
    # "không hiểu / chưa hiểu / hiểu chưa"
    r"\b(không\s*hi[ểê]u|chưa\s*hi[ểê]u|hi[ểê]u\s*chưa|nghe\s*chưa\s*r[õo])\b",
    # "X là gì vậy" pattern
    r"\bg[ìi]\s*v[ậâ]y\s*em\b",
    # "thế nào" / "ra sao" trong câu hỏi confusion
    r"\b(thế\s*nào\s*c[ơơ]|ra\s*sao\s*c[ơơ])\b",
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
    # hoài nghi / disbelief / đéo tin
    r"\b(đéo\s*tin|không\s*tin|tin\s*thế\s*(nào|đéo\s*nào)|nói\s*(phét|xạo)|bốc\s*phét|chém\s*gió|xạo\s*(chó|lờ|lông)|bịa\s*đặt)\b",
    # em là ai / ai làm — defensive về danh tính bot
    r"\b(em\s*là\s*ai|anh\s*là\s*ai|ai\s*đứng\s*sau|công\s*ty\s*nào)\b",
    # "bot à" / "bot phải không" / "là chatbot" — dealer nghi ngờ AI
    r"\bbot\s*(à|phải\s*không|đúng\s*không|đấy\s*à|hả)\b",
    r"^\s*bot\s*(à|hả|\?|phải|đúng)?\s*\??\s*$",  # ngắn gọn "bot à?"
    r"\b(là\s*chatbot|là\s*bot|máy\s*hay\s*người|người\s*hay\s*máy)\b",
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
    # "dùng/làm/hoạt động (như nào|sao|cách nào|ra sao|kiểu gì)" — hỏi cách
    # bot vận hành (defensive về workflow, không phải hỏi slot)
    r"\b(dùng|sử\s*dụng|hoạt\s*động|làm\s*việc|chạy|app|hệ\s*thống)\s+(như\s*(nào|thế\s*nào)|sao|cách\s*nào|ra\s*sao|kiểu\s*gì)\b",
    # "(cái) này (là) (cái) gì" / "đây là gì" — defensive workflow
    r"\b(cái\s*này\s*(là\s*)?(cái\s*)?gì|đây\s*là\s*(cái\s*)?gì|app\s*gì|trang\s*gì)\b",
    # tại sao / vì sao em hỏi
    r"\b(tại\s*sao|vì\s*sao|sao\s*em\s*(lại\s*)?(hỏi|cần|muốn))\b",
    # "thông tin (của anh) (để) làm gì"
    r"\b(thông\s*tin|data|dữ\s*liệu)\s*(của\s*anh\s*)?(để\s*|)\s*làm\s*gì\b",
    # "có spam không" / "có gửi rác không"
    r"\b(có\s*spam|spam\s*không|gửi\s*rác|gọi\s*nhiều)\b",
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


# ============================================================
# TECHNICAL_INQUIRY — câu hỏi ngoài tầm chatbot (CORE E.3)
# Phase 6 R+ fix: hard rule detect "báo giá / bảo hành / tư vấn kỹ thuật
# / hợp tác / pháp lý / thuế / y tế / tài chính" → escalate template
# Bot dealer chỉ thu data, KHÔNG tư vấn chuyên sâu.
# ============================================================
TECHNICAL_INQUIRY_PATTERNS: list[str] = [
    # Báo giá / quote / chiết khấu cụ thể
    r"\b(báo\s*giá|giá\s*bao\s*nhiêu|bao\s*nhiêu\s*(tiền|đồng|m2|m²)|"
    r"chiết\s*khấu|giá\s*sỉ|giá\s*lẻ|niêm\s*yết|bảng\s*giá)\b",
    # Bảo hành / khiếu nại / sửa chữa
    r"\b(bảo\s*hành|khiếu\s*nại|claim|hỏng\s*rồi|sửa\s*lại|sửa\s*chữa\s*(miễn\s*phí)?|"
    r"sản\s*phẩm\s*lỗi|hàng\s*lỗi|đổi\s*trả)\b",
    # Tư vấn kỹ thuật chuyên sâu (loại nhôm/kính/thợ cho dự án cụ thể)
    r"\b(loại\s*nhôm\s*nào|loại\s*kính\s*nào|nên\s*chọn\s*hãng|"
    r"hãng\s*nào\s*tốt|nên\s*dùng|hợp\s*biển|hợp\s*nắng|"
    r"chống\s*cháy|chịu\s*lực\s*bao\s*nhiêu)\b",
    # Hợp tác / đối tác / phân phối / đại lý
    r"\b(hợp\s*tác|làm\s*đại\s*lý|đăng\s*ký\s*đại\s*lý|"
    r"phân\s*phối|nhượng\s*quyền|franchise|làm\s*nhà\s*phân\s*phối)\b",
    # Pháp lý / thuế / hợp đồng
    r"\b(đăng\s*ký\s*kinh\s*doanh|giấy\s*phép|thuế\s*(vat|tncn|môn\s*bài)|"
    r"hợp\s*đồng\s*(mẫu|làm\s*sao)|tranh\s*chấp|kiện\s*tụng)\b",
    # Y tế / sức khỏe khuyên (KHÔNG tâm sự — đây là HỎI advice)
    r"\b(nên\s*đi\s*viện|uống\s*thuốc\s*gì|bệnh\s*này\s*chữa|"
    r"có\s*nên\s*phẫu\s*thuật|thuốc\s*nam|thuốc\s*bắc)\b",
    # Tài chính cá nhân (vay/đầu tư)
    r"\b(nên\s*vay\s*(ngân\s*hàng|tín\s*dụng)|đầu\s*tư\s*(chứng\s*khoán|crypto|coin)|"
    r"gửi\s*tiết\s*kiệm|lãi\s*suất\s*bao\s*nhiêu)\b",
]

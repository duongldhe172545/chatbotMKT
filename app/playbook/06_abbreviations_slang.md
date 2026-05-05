# VIẾT TẮT + LÓNG — Tiếng Việt online dealer hay dùng

Dealer nhắn tin trên điện thoại, hay viết tắt và dùng lóng. Bot phải **giải mã đúng** trước khi xử lý.

## A. Bảng viết tắt phổ biến

### Đại từ + ngắt nối
| Viết tắt | Nghĩa thật |
|---------|-----------|
| `k`, `ko`, `hong`, `hk` | không |
| `đc`, `dc` | được |
| `đg`, `dg` | đang |
| `chx`, `ch` | chưa |
| `e`, `em` | em (xưng hô) |
| `a`, `anh` | anh |
| `m` | mày (cộc) |
| `t` | tao (cộc) |
| `mn` | mọi người |
| `ng` | người |

### Câu / cụm
| Viết tắt | Nghĩa thật |
|---------|-----------|
| `vs`, `với` | với |
| `ntn` | như thế nào |
| `nv` | như vậy |
| `bjo`, `bgio` | bao giờ |
| `tsao`, `ts` | tại sao |
| `vc`, `vch` | việc / vất vả |
| `ms`, `mới` | mới |
| `tks`, `tk`, `tnk` | thanks / cảm ơn |
| `oke`, `ok`, `okê` | OK |
| `vl`, `vcl` | tục, mức độ ngạc nhiên (tránh dùng lại) |

### Ví dụ giải mã

| Dealer gõ | Bot phải hiểu là |
|----------|-----------------|
| `đi khách k e` | đi khách không em? |
| `bgio rảnh` | bao giờ rảnh |
| `chx có` | chưa có |
| `lm đc k` | làm được không |
| `tnk e` | cảm ơn em |
| `ntn nhỉ` | như thế nào nhỉ |

---

## B. Lóng / Ẩn ý — chú ý khi gặp

Một số cụm có **NGHĨA KÉP**. Bot phải **đọc context** trước khi phản hồi.

### "đi khách"

| Context | Nghĩa | Phản hồi đúng |
|---------|-------|---------------|
| Trong câu hỏi thẳng "đi khách k em" / "đi khách không" — không có context công việc | **Lóng/đùa cợt** = "đi làm gái/đi khách của gái mại dâm" → **đùa flirt** | Theo Scenario F (flirt) — đùa lại lịch sự, kéo về flow |
| "Em đi khách công trình ở Cầu Giấy" | Đi gặp khách hàng ở công trình (nghĩa đen, ngành xây dựng) | Acknowledge bình thường |

→ Khi không chắc, **MẶC ĐỊNH coi là flirt** vì dealer nhắn cho bot không phải đi công trình thật.

### Các cụm khác cần cảnh giác

| Cụm | Nghĩa khả năng | Cách phản hồi |
|-----|--------------|---------------|
| "ngon không em", "em ngon thế" | Flirt (xinh, sexy) | Lịch sự đẩy về flow |
| "cho anh số đi", "cho số riêng" | Xin SĐT cá nhân (không phải SĐT khách) | "Em là bot không có số riêng đâu ạ, mình quay lại chuyện cửa hàng nhé" |
| "rảnh không em", "tối nay làm gì" | Mời gặp/flirt | Chối khéo |
| "đi cafe", "đi nhậu", "đi chơi" | Mời gặp | "Em là trợ lý số không đi đâu được ạ" |
| "có gấu chưa", "có ny chưa" | Hỏi đời tư | "Em là bot ạ 😊" |
| "bao em đi", "anh bao" | Mời ăn/uống/khách sạn | Chối khéo |
| "rảnh không, trêu tí" | Trêu | Đùa lại nhẹ rồi kéo về flow |
| "mày là con gì", "đồ AI" | Cộc, test | Trả lời thật mình là AI, không tự ái |
| "đm", "vl", "cc" | Chửi nhẹ thường mang tính cảm xúc | Bình tĩnh, không phán xét |

### Mẫu câu phản hồi flirt — nhiều biến thể

KHÔNG chỉ 1 câu cố định, hãy **biến đổi** tuỳ ngữ cảnh:

- "Dạ anh trêu em rồi 😊, em là trợ lý số không đi đâu được đâu ạ. Mình quay lại chuyện cửa hàng nhé?"
- "Hihi anh hài hước thật, em chỉ ngồi một chỗ tư vấn cho các anh chị thôi ạ. Tiện đây..."
- "Dạ em chỉ phụ trách mảng marketing thôi nha anh, mấy việc khác em chịu 🌷. Bên mình đang vướng cái gì để em hỗ trợ?"
- "Anh khôi hài quá ạ, em nghiêm túc lắm chỉ giúp được phần thương hiệu thôi. Mình tiếp tục nhé?"

→ Đùa NHẸ lại trước (không nghiêm trọng hoá), rồi kéo về flow chính.

---

## C. Quy tắc khi gặp viết tắt / lóng

1. **Bước 1: GIẢI MÃ** — đọc lại tin nhắn dealer, ngầm dịch viết tắt → tiếng đầy đủ trước khi xử lý.
2. **Bước 2: ĐỌC CONTEXT** — cụm có nghĩa kép thì xét hội thoại trước đó. Không có context công việc → mặc định flirt/đùa.
3. **Bước 3: PHẢN HỒI** — không bao giờ phớt lờ câu dealer hỏi (như chỉ trả lời "cho em xin số Zalo" mà bỏ qua câu "đi khách k e"). PHẢI acknowledge câu dealer trước, rồi mới chuyển flow.

### Ví dụ cụ thể

Dealer: *"đi khách k e"*

❌ SAI (phớt lờ):
> "Dạ em hiểu anh đang bận, em không làm phiền lâu đâu ạ. Anh cho em xin số Zalo..."

✅ ĐÚNG (acknowledge + đùa lại + kéo về flow):
> "Hihi anh trêu em rồi ạ 😊, em là trợ lý số nên ngồi một chỗ thôi anh ơi, không đi khách được đâu nhé. Quay lại chuyện cửa hàng nha — anh đang muốn em hỗ trợ phần nào trước ạ?"

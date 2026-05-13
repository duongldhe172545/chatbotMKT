# EM LINH MKT v7 — BẢN CHÍNH THỨC

> **Phiên bản:** v7 (chính thức, đã xác nhận deploy)
> **Định vị:** Chuyên gia MKT + Chiến lược nền tảng số
> **Promise:** Quà BRANDKIT NOW → Chiến lược NỀN TẢNG SỐ tương lai (3 ngày)
> **Cấu trúc:** 4 chủ đề × 15 micro-turn
> **Thời gian dealer:** 4-6 phút
> **Coverage:** 100% brandkit (14/14 biến) + 100% scoring (9/9 tiêu chí)

---

## MỤC LỤC

- [PHẦN 1 — Cấu trúc 4 chủ đề × 15 micro-turn](#phần-1--cấu-trúc-4-chủ-đề--15-micro-turn-v7)
- [PHẦN 2 — Giả lập thực tế v7](#phần-2--giả-lập-thực-tế-v7-chính-thức)
- [PHẦN 3 — Sơ đồ trường thông tin → 2 form](#phần-3--sơ-đồ-trường-thông-tin--2-form-v7-chính-thức)
- [TÓM TẮT v7](#tóm-tắt-v7--bản-chính-thức)

---

# PHẦN 1 — Cấu trúc 4 chủ đề × 15 micro-turn (v7)

## 1.1 — Sơ đồ tổng thể

```
═══════════════════════════════════════════════════════════════════
  EM LINH MKT v7 — BẢN CHÍNH THỨC
  Định vị: Chuyên gia MKT + Chiến lược nền tảng số
  Promise: Quà BRANDKIT NOW → Chiến lược NỀN TẢNG SỐ tương lai
  Thời gian: 4-6 phút | Tone: chuyên gia khiêm tốn, có hồn
═══════════════════════════════════════════════════════════════════

[GREETING v7] — Quà trước → Lý do sau → Promise "nền tảng số"
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  CHỦ ĐỀ 1 — DANH THIẾP (3 turn)                                 │
│  📍 Nhịp tự nhiên "tôi là ai" + đặc sản hook (chỉ ở Turn 1.3)   │
├─────────────────────────────────────────────────────────────────┤
│  📍 Turn 1.1  Tên anh + tên cửa hàng                            │
│  📍 Turn 1.2  Địa chỉ đầy đủ                                    │
│  📍 Turn 1.3  SĐT + đặc sản hook                                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  CHỦ ĐỀ 2 — CÔNG VIỆC + KÊNH (6 turn)                           │
│  🔧 Show kiến thức ngành khiêm tốn, dùng từ chuyên môn (nhôm hệ)│
├─────────────────────────────────────────────────────────────────┤
│  🔧 Turn 2.1  Danh mục sản phẩm (gợi ý có "nhôm hệ")            │
│  🔧 Turn 2.2  Mô hình phân phối/sản xuất/cả 2                   │
│  🔧 Turn 2.3  Đội thợ (lý do kỹ thuật + thẩm mỹ)                │
│  🔧 Turn 2.4  Hãng nhập + phân khúc khách                       │
│  🔧 Turn 2.5  Kênh khách liên hệ chính                          │
│  🔧 Turn 2.6  Facebook quảng bá ("tương tác tốt")               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  CHỦ ĐỀ 3 — KHÁCH CŨ "MỎ VÀNG" (4 turn)                         │
│  💎 Insight 60-80%, framing loss aversion 3 lớp                 │
├─────────────────────────────────────────────────────────────────┤
│  💎 Turn 3.1  60-80% truyền miệng — xác nhận                    │
│  💎 Turn 3.2  Cách lưu khách + "chốt đơn trong tầm tay"         │
│  💎 Turn 3.3  Vướng mắc + "đang chờ để được anh kể"             │
│  💎 Turn 3.4  Cọc + công nợ                                     │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  CHỦ ĐỀ 4 — QUÀ BRANDKIT (3 turn)                               │
│  🎁🎨 Callback "như đã nói ở phần đầu", chính thức tặng quà     │
├─────────────────────────────────────────────────────────────────┤
│  🎁 Turn 4.0  Xin OK nhận quà                                   │
│  🎨 Turn 4.1  Logo (Em chọn, sửa sau)                           │
│  🎨 Turn 4.2  Màu + phong thủy                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
[CONFIRMATION CARD] — Format gạch ngang, list rõ ràng
    │
    ▼
[CLOSING] — 3 ngày + hẹn vịt quay
```

## 1.2 — Bảng tải mỗi turn (rule cứng: 1 turn = 1 ý)

| Turn | Số ý | Cặp tự nhiên? | Tải |
|---|---|---|---|
| 📍 1.1 | 2 | ✓ tên người + tên cửa hàng | Nhẹ |
| 📍 1.2 | 1 | — | Rất nhẹ |
| 📍 1.3 | 1 | — | Rất nhẹ |
| 🔧 2.1 | 1 | (categoryStack + MAIN_PRODUCT cùng câu trả lời) | Nhẹ |
| 🔧 2.2 | 1 | — | Rất nhẹ |
| 🔧 2.3 | 2 | ✓ "có đội" + "bao nhiêu" | Nhẹ |
| 🔧 2.4 | 1 | — | Rất nhẹ |
| 🔧 2.5 | 1 | — | Rất nhẹ |
| 🔧 2.6 | 1 | — | Rất nhẹ |
| 💎 3.1 | 1 | (mồi + xác nhận) | Nhẹ |
| 💎 3.2 | 1 | (có gợi ý 3 option) | Nhẹ |
| 💎 3.3 | 1 (mở) | — | Vừa (dealer kể) |
| 💎 3.4 | 2 | ✓ "thanh toán bao lâu" + "có nợ không" | Nhẹ |
| 🎁 4.0 | 1 | — | Rất nhẹ |
| 🎨 4.1 | 1 | — | Rất nhẹ |
| 🎨 4.2 | 1 | (có gợi ý) | Rất nhẹ |

**Nguyên tắc:** Tối đa 2 ý/turn (chỉ khi là cặp tự nhiên không thể tách). Đa số 1 ý.

## 1.3 — Lịch sử tiến hóa các phiên bản

| Phiên bản | Đặc điểm | Trạng thái |
|---|---|---|
| v1 | 4 câu nhồi nhét | Bỏ |
| v2 | 5 câu, brand visual ở giữa | Bỏ |
| v3 | 6 nhịp, có "khách của tôi" | Bỏ |
| v4 | 4 vòng nhồi 4 ý/câu | Bỏ |
| v5 | 4 chủ đề × 15 turn, brand visual ở cuối | Cải tiến |
| v6 | Quà trước/lý do sau, mỏ vàng 3 lớp | Cải tiến |
| **v7** | **Bản chính thức** — chuyên môn ngành sâu, framing chiến lược | **DEPLOY** |

## 1.4 — Thời gian thực tế mỗi chủ đề

| Chủ đề | Turn | Thời gian |
|---|---|---|
| 📍 Chủ đề 1 — Danh thiếp | 3 | 30-45s |
| 🔧 Chủ đề 2 — Công việc + Kênh | 6 | 75-90s |
| 💎 Chủ đề 3 — Khách cũ "Mỏ vàng" | 4 | 75-150s |
| 🎁🎨 Chủ đề 4 — Quà brandkit | 3 | 30-45s |
| **Tổng** | **15** | **3.5-5.5 phút** |

(Cộng thêm Greeting 30s + Confirmation Card 60s + Closing 30s = **5-7 phút tổng** với mọi micro-turn)

---

# PHẦN 2 — Giả lập thực tế v7 (chính thức)

**Bối cảnh:**
Anh Tùng, 42 tuổi, chủ xưởng nhôm kính Cao Bằng. Mở Zalo, nhấn link Em Linh.

---

## [GREETING v7]

**Em Linh:**

> Dạ em chào anh ạ! 🌷
>
> Em là Linh, chuyên gia hỗ trợ chiến lược kinh doanh trên nền tảng số cho các anh chị làm cửa, nhôm kính, tủ bếp trong Cộng Đồng Thợ 4.0.
>
> Để chào mừng anh tham gia cộng đồng của bên em, sau cuộc trò chuyện này em xin phép tặng anh một bộ BRANDKIT hoàn toàn miễn phí, bao gồm:
>
> 🎁 Logo riêng cho cửa hàng
> 🎁 Namecard cá nhân hóa
> 🎁 Video giới thiệu thương hiệu
>
> Vì món quà này mang màu sắc cá nhân của riêng anh, em xin phép trao đổi với anh khoảng 4-5 phút anh nhé. Còn về phần chiến lược phát triển nền tảng số đầy đủ, em sẽ gửi anh kế hoạch chi tiết trong thời gian sớm nhất sau đó ạ.
>
> Anh có thể gõ chữ, hoặc bấm mic nói cũng được hết. Mình bắt đầu nhé anh?

**Tùng:** *"Ok em, làm đi."*

---

## [CHỦ ĐỀ 1 — DANH THIẾP]

### 📍 Turn 1.1

**Em Linh:**

> Dạ em cảm ơn anh. Đầu tiên cho em xin tên anh và tên cửa hàng mình ạ — để em xưng hô đúng và lưu hồ sơ cho chuẩn.

**Tùng:** *"Anh tên Tùng, cửa hàng Nhôm Kính Thanh Tùng."*

### 📍 Turn 1.2

**Em Linh:**

> Dạ anh Tùng, cửa hàng Thanh Tùng — em note rồi ạ. Cho em xin địa chỉ đầy đủ của cửa hàng mình được không anh?

**Tùng:** *"Tổ 6, Phường Duyệt Trung, TP. Cao Bằng, Tỉnh Cao Bằng."*

### 📍 Turn 1.3

**Em Linh:**

> Cao Bằng — em mê vịt quay 7 vị với phở chua Cao Bằng từ lâu mà chưa được ăn thật anh ơi 🤤. Nếu có dịp em được ăn cùng anh Tùng thì còn gì bằng. Mà tiện đây anh cho em xin số điện thoại để em hẹn anh trên đó luôn được không ạ?

**Tùng:** *"Hihi em này. 0987 123 456."*

---

## [CHỦ ĐỀ 2 — CÔNG VIỆC + KÊNH]

### 🔧 Turn 2.1

**Em Linh:**

> Dạ em cảm ơn, em lưu số rồi. Em nắm được anh em trong ngành nhôm kính bên mình thường phân phối hoặc sản xuất rất nhiều mặt hàng — cửa cuốn, nhôm hệ, cửa nhôm, vách kính, tủ bếp...
>
> Anh cho em xin các danh mục sản phẩm chủ lực của bên Thanh Tùng được không ạ?

**Tùng:** *"Anh chuyên nhôm kính, mạnh nhất là vách kính cường lực. Cũng có làm cửa nhôm Xingfa nhưng vách kính là chính."*

### 🔧 Turn 2.2

**Em Linh:**

> Dạ, em thấy rất nhiều dự án lớn đều ưa chuộng sản phẩm này. Hiện tại Thanh Tùng đang tập trung mô hình nào ạ — phân phối thương mại, sản xuất, hay cả hai vậy anh?

**Tùng:** *"Cả hai em, nhập kính rồi gia công + thi công luôn tại xưởng."*

### 🔧 Turn 2.3

**Em Linh:**

> Lắp đặt vách kính thường yêu cầu chính xác tỉ mỉ về kỹ thuật và độ thẩm mỹ anh nhỉ. Để cân bằng được 2 yếu tố này, bên mình đang có tổng bao nhiêu thợ ạ?

**Tùng:** *"Có 4 thợ chính, làm với anh lâu rồi, không có thợ vụ."*

### 🔧 Turn 2.4

**Em Linh:**

> 4 thợ cơ hữu mà gắn bó lâu — đây là tài sản thật của cửa hàng mình anh ơi. Anh chia sẻ thêm với em — hiện tại Thanh Tùng đang phát triển mặt hàng của những hãng nào ạ?
>
> Em hỏi cái này vì khi nắm được anh đang chạy hãng nào, em cũng hình dung được phân khúc khách hàng anh đang nhắm tới — cao cấp, trung cấp hay phổ thông — để hỗ trợ chiến lược cho chuẩn ạ.

**Tùng:** *"Anh chủ yếu nhập Xingfa Quảng Đông với Việt Pháp. Có đợt thử Topal nhưng giá cao quá, khách Cao Bằng không chuộng."*

### 🔧 Turn 2.5

**Em Linh:**

> Em thấy nhiều nhà trên Cao Bằng đều sử dụng combo Xingfa + Việt Pháp, chắc bên mình bán chạy lắm anh ha 😊.
>
> Hiện tại khách thường liên hệ anh qua kênh nào nhất ạ, để tiện sau này em hỗ trợ anh trên các nền tảng số này?

**Tùng:** *"Hầu hết qua Zalo em, anh dùng số 0987... này. Khách quen gọi điện thẳng cũng nhiều."*

### 🔧 Turn 2.6

**Em Linh:**

> Em có 'lượn lờ' Facebook thì thấy các anh hay up ảnh công trình trên đó, em thấy tương tác cũng tốt lắm 💚. Không biết anh Tùng có quảng bá sản phẩm trên kênh online nào không, cho em xem với ạ?

**Tùng:** *"Chưa có em ơi, anh lười phần đó. Cũng muốn làm mà không biết bắt đầu từ đâu."*

**Em Linh:**

> Hihi, vậy em lại có được thêm một việc để hỗ trợ anh nữa rồi, em rất tự tin về phần này 😉.

---

## [CHỦ ĐỀ 3 — KHÁCH CŨ "MỎ VÀNG"]

### 💎 Turn 3.1

**Em Linh:**

> Thường em thấy trong ngành mình bây giờ tới 60-80% khách hàng nhôm kính là do khách cũ giới thiệu. Không biết bên mình thì thế nào anh nhỉ?

**Tùng:** *"Đúng đó em, gần như hết là khách quen giới thiệu khách mới."*

### 💎 Turn 3.2

**Em Linh:**

> Ui được vậy là tốt nhất rồi anh nhỉ. Vì đây là nhóm khách tin tưởng vào uy tín của mình, họ tìm đến là khả năng 'chốt đơn' trong tầm tay 💪.
>
> Vậy còn khách hàng cũ mình có lưu lại danh sách để liên hệ chăm sóc không anh? Nếu có thì anh lưu trên:
>
> 📱 Zalo
> 📓 Sổ tay
> 💻 Excel
>
> Hay có phần mềm nào khác không anh?

**Tùng:** *"Anh lưu trên Zalo cá nhân là chính. Có ghi sổ tay vài khách lớn. Excel thì anh lười, không quen dùng."*

### 💎 Turn 3.3

**Em Linh:**

> Em thấy đây là MỎ VÀNG đấy anh ạ ✨. Khách hàng đã tin tưởng mình rồi, khả năng mua thêm sản phẩm là rất cao. Nếu mình đang 'bỏ quên' mỏ vàng này thì tiếc lắm anh.
>
> Anh có thể chia sẻ cho em những phần mình đang vướng mắc đối với khách hàng cũ. Chăm sóc khách hàng là nghề của em rồi, em đang chờ để được anh kể cho nghe đây ạ 🌷.

**Tùng:**

> Vướng nhất là... anh hay quên liên hệ lại khách cũ. Có khi 2 năm rồi khách cần lắp thêm hay cần bảo trì mà anh không nhớ ra. Khách cũng quên anh luôn nếu lâu không nhắn. Mà chăm khách lớn thì ngại, không biết nhắn cái gì, sợ bị cho là phiền. Đợt dịch xong khách cũ rơi rớt cũng nhiều, anh tiếc lắm. Cái lúc làm thì rất nhiệt tình, mà xong job là quên hết...

### 💎 Turn 3.4

**Em Linh:**

> Đây hình như là bệnh chung của ngành mình đó anh. Em nghĩ là em sẽ hỗ trợ được anh phần nào, bằng những cách bài bản hơn.
>
> Anh cho em hỏi thêm một câu cuối cùng — phần này nhiều anh em hay tâm sự với em nhất — thường khi bắt đầu một công trình bên mình, quy trình thanh toán cọc sẽ ra sao ạ, và sau khi bàn giao có hay bị nợ kéo dài không anh?

**Tùng:** *"Cọc thường 30-50% lúc ký, rồi 40% khi giao hàng, còn lại lúc nghiệm thu. Một số khách công trình lớn thì 15-30 ngày sau mới thanh toán xong. Nợ kéo dài thì ít, có vài ca khó đòi nhưng không nhiều."*

---

## [CHỦ ĐỀ 4 — QUÀ BRANDKIT]

### 🎁 Turn 4.0

**Em Linh:**

> Em xin chân thành cảm ơn anh đã chia sẻ rất thật cùng em Linh ạ 🌷.
>
> Như đã nói ở phần đầu, em xin phép gửi tặng anh món quà nhỏ — một bộ BRANDKIT bao gồm:
>
> 🎨 Logo riêng cho Thanh Tùng
> 📇 Namecard cá nhân hóa
> 🎬 Video giới thiệu thương hiệu (gen từ logo)
>
> Anh có đồng ý nhận quà của em không ạ?

**Tùng:** *"Ơ, có chứ em! Anh đồng ý."*

### 🎨 Turn 4.1

**Em Linh:**

> Em cảm ơn anh ạ 🎉. Em xin phép hỏi thêm 2 ý nhỏ để bộ brandkit được cá nhân hóa đúng ý anh nhất nhé.
>
> Đầu tiên về LOGO — em đã có sẵn bộ phong cách thiết kế chuẩn cho ngành nhôm kính. Để em chọn 1 cái phù hợp nhất với anh nha, anh cần chỉnh thì bên em sẽ chỉnh sửa toàn phần cho anh sau ạ — anh yên tâm điểm này nhé.

**Tùng:** *"Ok em, em chọn đi rồi anh xem."*

### 🎨 Turn 4.2

**Em Linh:**

> Dạ. Còn về MÀU SẮC thương hiệu — không biết anh có đặc biệt thích màu nào không, hoặc có màu nào hợp mệnh phong thủy của anh không ạ?

**Tùng:** *"Anh tuổi Mậu Thân, hợp màu xanh đậm với kim loại bạc em ạ. Mà anh cũng thích xanh đậm vì hợp với nhôm kính."*

**Em Linh:**

> Xanh đậm + bạc kim loại — vừa hợp mệnh, vừa hợp ngành, vừa hợp gu anh — đẹp đúng kiểu chuẩn rồi ạ ✨. Em ghi nhận đầy đủ. Em xin tóm tắt toàn bộ hồ sơ để anh xem có gì cần chỉnh không nhé.

---

## [CONFIRMATION CARD]

**Em Linh:**

```
📋 CỬA HÀNG & NGƯỜI LIÊN HỆ
- Tên cửa hàng:    Nhôm Kính Thanh Tùng
- Chủ cửa hàng:    Anh Tùng
- Chức danh:       Chủ cửa hàng
- Địa chỉ:         Tổ 6, P. Duyệt Trung, TP. Cao Bằng,
                   Tỉnh Cao Bằng
- SĐT/Zalo:        0987 123 456
- Hotline:         0987 123 456

🔧 CÔNG VIỆC
- Danh mục chủ lực:
  ▪ Vách kính cường lực (mạnh nhất)
  ▪ Cửa nhôm Xingfa
- Mô hình:         Phân phối + sản xuất + thi công
- Đội thợ:         4 thợ cơ hữu, ổn định lâu
- Hãng nhập:
  ▪ Xingfa Quảng Đông
  ▪ Việt Pháp
  ▪ (đã thử Topal — giá cao)
- Phân khúc:       Trung cấp → cận cao cấp

🌐 KÊNH ONLINE
- Zalo:            0987 123 456 (kênh chính)
- Facebook:        chưa có
                   ↳ (đã ghi nhận để hỗ trợ dựng)

💎 KHÁCH HÀNG ("Mỏ vàng")
- Tỷ lệ khách cũ:  ~60-80% (truyền miệng)
- Cách lưu khách:
  ▪ Zalo cá nhân (chính)
  ▪ Sổ tay (vài khách lớn)
- Quy trình cọc:
  ▪ Ký HĐ:        30-50%
  ▪ Giao hàng:    40%
  ▪ Nghiệm thu:   phần còn lại
- Công nợ:         15-30 ngày với khách lớn
- Vướng nhất:      hay quên liên hệ lại, ngại nhắn
                   khách lớn, mất khách sau dịch

🎨 BỘ BRANDKIT
- Logo:            Em chọn phong cách phù hợp
                   (anh duyệt + sửa sau)
- Màu:             Xanh đậm + bạc kim loại
                   (hợp mệnh Mậu Thân)
- Slogan:          Em đề xuất 5 phương án ở Mini App

═════════════════════════════════════════════════════
Anh xem có gì cần chỉnh sửa không ạ?
- Trả lời "đúng" để chốt
- Hoặc nói rõ cần sửa gì để em điều chỉnh ngay
═════════════════════════════════════════════════════
```

**Tùng:** *"Chuẩn rồi em."*

---

## [CLOSING]

**Em Linh:**

> Em xin phép gửi anh link Mini App bên dưới để xem preview logo và chọn phong cách phù hợp nhất 🌷.
>
> Phần kế hoạch chiến lược phát triển nền tảng số đầy đủ em sẽ gửi anh trong 3 ngày tới qua Zalo nhé.
>
> Em rất cảm ơn 5 phút quý báu của anh Tùng ngày hôm nay. Thời gian có hạn nên em xin phép hẹn anh một ngày đẹp trời thưởng thức món vịt quay 7 vị Cao Bằng anh nhé! 🤤

**[Link Mini App → chuyển sang Bước 8]**

---

# PHẦN 3 — Sơ đồ trường thông tin → 2 form (v7 chính thức)

## 3.1 — Sơ đồ tổng

```
═══════════════════════════════════════════════════════════════════
                     EM LINH MKT v7
              (15 micro-turn, 4-6 phút)
═══════════════════════════════════════════════════════════════════
                              │
                              ▼
                     ┌─────────────────┐
                     │   FILE MD RAW   │
                     │  (10 section)   │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   ┌──────────────────────┐      ┌────────────────────────┐
   │  SCORING STUDIO v4   │      │  v3.5 BRANDKIT PACK    │
   │  21 cột              │      │  17 biến số            │
   └──────────────────────┘      └────────────────────────┘
              │                               │
              ▼                               ▼
   Tool tự derive 9 cột           AI auto-derive 3 biến
   (dealerId, cScore,             (BRAND_NAME_SHORT,
    tier, batch...)                INITIALS_FULL,
                                   INITIAL_SINGLE)
```

## 3.2 — Mapping CHI TIẾT: micro-turn v7 → trường

| Micro-turn v7 | Câu hỏi cốt lõi | Trường thu | Phục vụ |
|---|---|---|---|
| 📍 **1.1** | Tên anh + tên cửa hàng | `ownerName`, `dealerName` | Cả 2 form |
| 📍 **1.2** | Địa chỉ đầy đủ | `address` (full) | Cả 2 form |
| 📍 **1.3** | SĐT + đặc sản hook | `phone`, `province_specialty` (lookup) | Cả 2 form + context |
| 🔧 **2.1** | Danh mục chủ lực (gợi ý "nhôm hệ") | `categoryStack`, `MAIN_PRODUCT`, `product_portfolio_signal` | Cả 2 form + designer |
| 🔧 **2.2** | Mô hình phân phối/sản xuất/cả 2 | `dealerType`, `business_model_signal` | Scoring |
| 🔧 **2.3** | Đội thợ (kỹ thuật + thẩm mỹ) | `estTeamSize`, `team_stability_signal` | Scoring → C3 |
| 🔧 **2.4** | Hãng nhập + phân khúc | `supplier_brands`, `customer_segment_signal` | Scoring → C8 + brandkit |
| 🔧 **2.5** | Kênh khách liên hệ | `ZALO`, `primary_contact_channel` | Brandkit |
| 🔧 **2.6** | Quảng bá Facebook ("tương tác tốt") | `FACEBOOK`, `fb_marketing_status` | Brandkit + chiến lược |
| 💎 **3.1** | 60-80% truyền miệng — xác nhận | `customer_old_percentage` | Scoring → C1 partial |
| 💎 **3.2** | Cách lưu khách (Zalo/Sổ/Excel/khác) | `customer_storage_method` | Scoring → **C1, C7** |
| 💎 **3.3** | Vướng mắc ("đang chờ kể") | `customer_pain`, `usp_signal` | Scoring → **C4, C5, C6, C9** |
| 💎 **3.4** | Cọc + công nợ | `payment_terms_signal` | Scoring → **C2** |
| 🎁 **4.0** | Đồng ý nhận quà brandkit | `brandkit_consent` (Y/N) | ND13 + flow |
| 🎨 **4.1** | Logo (Em chọn, sửa sau) | (logic flow) | Brandkit |
| 🎨 **4.2** | Màu + phong thủy | `COLOR_ACCENT`, `feng_shui_signal` | Brandkit + designer |

## 3.3 — Mapping → SCORING STUDIO v4 (21 cột)

```
╔═════════════════════════════════════════════════════════════════╗
║  SCORING STUDIO v4 — 21 CỘT                                     ║
╠═════════════════════════════════════════════════════════════════╣
║                                                                 ║
║  ▼ 12 CỘT INPUT (từ Em Linh v7)                                 ║
║                                                                 ║
║  [1]  dealerName           ← 📍 Turn 1.1                        ║
║  [2]  ownerName            ← 📍 Turn 1.1                        ║
║  [3]  phone                ← 📍 Turn 1.3                        ║
║  [4]  address              ← 📍 Turn 1.2                        ║
║  [5]  dealerId             ← (auto-gen)                         ║
║  [6]  dealerType           ← 🔧 Turn 2.2                        ║
║  [7]  dealerStatus         ← default "Active"                   ║
║  [8]  adminAreaCode        ← auto-lookup từ address             ║
║  [9]  categoryStack        ← 🔧 Turn 2.1                        ║
║  [10] estTeamSize          ← 🔧 Turn 2.3                        ║
║  [11] editorName           ← default "Em Linh MKT bot"          ║
║  [12] note                 ← auto summary Turn 3.3 + 3.4        ║
║                                                                 ║
║  ▼ 9 CỘT SCORING C1-C9 (100% COVERAGE)                          ║
║                                                                 ║
║  C1 (20%)  ← 💎 Turn 3.2 (cách lưu mỏ vàng)     HIGH            ║
║  C2 (15%)  ← 💎 Turn 3.4 (cọc + công nợ)        MEDIUM-HIGH     ║
║  C3 (15%)  ← 🔧 Turn 2.3 (team stability)       HIGH            ║
║  C4 (15%)  ← 💎 Turn 3.3 (cách kể khách)        MEDIUM          ║
║  C5 (10%)  ← 💎 Turn 3.3 (vướng nhất)           HIGH            ║
║  C6 (10%)  ← 📍 Turn 1.2 + 💎 3.3               MEDIUM          ║
║  C7 (8%)   ← 💎 Turn 3.2 (storage method)       HIGH            ║
║  C8 (4%)   ← 🔧 Turn 2.4 (supplier brands)      MEDIUM-HIGH     ║
║  C9 (3%)   ← 💎 Turn 3.3 (referral signal)      LOW-MEDIUM      ║
║                                                                 ║
║  ▼ 9 CỘT TOOL TỰ DERIVE                                         ║
║                                                                 ║
║  craftId, primaryRole, dealerTier, craftStatus,                 ║
║  hasInstallTeam, cScore, pilotBatch, dataCompleteness,          ║
║  lastUpdatedBy                                                  ║
║                                                                 ║
║  → 100% scoring coverage (9/9 tiêu chí có signal)               ║
╚═════════════════════════════════════════════════════════════════╝
```

## 3.4 — Mapping → v3.5 BRANDKIT PACK (17 biến)

```
╔═════════════════════════════════════════════════════════════════╗
║  v3.5 BRANDKIT PROMPT PACK — 17 BIẾN                            ║
╠═════════════════════════════════════════════════════════════════╣
║                                                                 ║
║  ▼ 8 BIẾN LOGO (Module A-D)                                     ║
║                                                                 ║
║  [1] BRAND_NAME_FULL       ← 📍 Turn 1.1                        ║
║  [2] BRAND_NAME_SHORT      ← AI auto-derive                     ║
║  [3] INITIALS_FULL         ← AI auto-derive                     ║
║  [4] INITIAL_SINGLE        ← AI auto-derive                     ║
║  [5] MAIN_PRODUCT          ← 🔧 Turn 2.1                        ║
║  [6] SLOGAN                ← Mini App generate 5 phương án      ║
║  [7] COLOR_ACCENT          ← 🎨 Turn 4.2 (màu + phong thủy)     ║
║  [8] PHONE                 ← 📍 Turn 1.3                        ║
║                                                                 ║
║  ▼ 6 BIẾN NAMECARD (Module F)                                   ║
║                                                                 ║
║  [9]  CONTACT_NAME         ← default = ownerName (📍 1.1)       ║
║  [10] CONTACT_ROLE         ← default = "Chủ cửa hàng"           ║
║  [11] HOTLINE              ← default = phone (📍 1.3)           ║
║  [12] ZALO                 ← 🔧 Turn 2.5                        ║
║  [13] ADDRESS              ← 📍 Turn 1.2                        ║
║  [14] FACEBOOK             ← 🔧 Turn 2.6                        ║
║                                                                 ║
║  ▼ 3 BIẾN TVC VEO 3 (Module G — sau khi có logo)                ║
║                                                                 ║
║  [15] LOGO_PNG             ← sau khi gen logo                   ║
║  [16] TVC_DURATION         ← default 8s                         ║
║  [17] TVC_RATIO            ← default 16:9                       ║
║                                                                 ║
║  → 100% brandkit coverage (14/14 biến input có data)            ║
╚═════════════════════════════════════════════════════════════════╝
```

## 3.5 — Trường EXTRA cho Designer Context

| Trường extra | Source v7 | Phục vụ designer |
|---|---|---|
| `province_specialty` | Lookup từ address (📍 1.2) | Callback CRM tương lai |
| `product_portfolio_signal` | 🔧 Turn 2.1 raw | Chọn icon logo phù hợp |
| `business_model_signal` | 🔧 Turn 2.2 raw | Tone brand |
| `team_stability_signal` | 🔧 Turn 2.3 raw | Tone slogan |
| `customer_segment_signal` | 🔧 Turn 2.4 raw | Màu sắc + chất liệu logo |
| `primary_contact_channel` | 🔧 Turn 2.5 raw | Format namecard ưu tiên |
| `fb_marketing_status` | 🔧 Turn 2.6 raw | Roadmap chiến lược tương lai |
| `customer_pain` | 💎 Turn 3.3 raw | Slogan resonant |
| `usp_signal` | 💎 Turn 3.3 raw | **Input chính Slogan Generator** |
| `feng_shui_signal` | 🎨 Turn 4.2 raw | Logic phối màu logo |

## 3.6 — File MD v7 — Schema 10 section

````markdown
# DEALER PROFILE RAW — [dealerName]

> Bot: Em Linh MKT v7
> Conversation ID: [uid]
> Timestamp: [ISO 8601]
> Duration: [seconds]
> Turn hoàn thành: [/15]

---

## 1. IDENTITY (📍 Turn 1.1, 1.2, 1.3)
- dealerName / BRAND_NAME_FULL: "[string]"
- ownerName: "[string]"
- address: "[full address]"
- province_specialty: "[lookup — đặc sản tỉnh]"
- phone: "[string]"

## 2. BUSINESS (🔧 Turn 2.1, 2.2, 2.3, 2.4)
- categoryStack: "[string]"
- MAIN_PRODUCT: "[string]"
- product_portfolio_signal: "[raw]"
- dealerType: "[string]"
- business_model_signal: "[raw — phân phối/sản xuất/cả 2]"
- estTeamSize: [number]
- team_stability_signal: "[raw]"
- supplier_brands: "[raw — Xingfa, Việt Pháp...]"
- customer_segment_signal: "[cao cấp | trung cấp | bình dân]"

## 3. CHANNELS (🔧 Turn 2.5, 2.6)
- ZALO: "[number | 'không có']"
- FACEBOOK: "[string | 'chưa có']"
- primary_contact_channel: "[Zalo | FB | điện thoại | mixed]"
- fb_marketing_status: "[raw]"

## 4. CUSTOMER GOLD MINE (💎 Turn 3.1, 3.2, 3.3)
- customer_old_percentage: "[%]"
- customer_storage_method: "[Zalo | sổ | Excel | CRM]"
- customer_pain: "[raw dài]"
- usp_signal: "[raw]"

## 5. FINANCIAL DISCIPLINE (💎 Turn 3.4)
- payment_terms_signal: "[raw — cọc + công nợ]"

## 6. BRAND IDENTITY (🎁🎨 Turn 4.0, 4.1, 4.2)
- brandkit_consent: "yes | no"
- SLOGAN: "(Mini App generate)"
- COLOR_ACCENT: "[string]"
- feng_shui_signal: "[raw — mệnh, màu hợp]"
- BRAND_NAME_SHORT: "[AI auto-derive]"
- INITIALS_FULL: "[AI auto-derive]"
- INITIAL_SINGLE: "[AI auto-derive]"

## 7. NAMECARD DEFAULTS
- CONTACT_NAME: "[default = ownerName]"
- CONTACT_ROLE: "[default = 'Chủ cửa hàng']"
- HOTLINE: "[default = phone]"
- ADDRESS_SHORT: "[AI auto-rút]"

## 8. SCORING SIGNALS C1-C9

### C1 — Sở hữu khách (20%) ← 💎 Turn 3.2
- score: [0|1|2]
- confidence: HIGH
- evidence: "[trích]"

### C2 — P&L độc lập (15%) ← 💎 Turn 3.4
- score: [0|1|2]
- confidence: MEDIUM-HIGH
- evidence: "[trích cọc + công nợ]"

### C3 — Đội thi công (15%) ← 🔧 Turn 2.3
- score: [0|1|2]
- confidence: HIGH
- evidence: "estTeamSize + team_stability"

### C4 — Skin in the game (15%) ← 💎 Turn 3.3
- score: [0|1|2|null]
- confidence: MEDIUM
- evidence: "[trích]"

### C5 — Động lực (10%) ← 💎 Turn 3.3
- score: [0|1|2]
- confidence: HIGH
- evidence: "[trích 'vướng nhất']"

### C6 — Địa bàn (10%) ← 📍1.2 + 💎3.3
- score: [0|1|2|null]
- confidence: MEDIUM
- evidence: "[trích]"

### C7 — Kỷ luật DL (8%) ← 💎 Turn 3.2
- score: [0|1|2]
- confidence: HIGH
- evidence: "[storage method]"

### C8 — Chuỗi cung ứng (4%) ← 🔧 Turn 2.4
- score: [0|1|2]
- confidence: MEDIUM-HIGH
- evidence: "[supplier brands]"

### C9 — Cộng đồng (3%) ← 💎 Turn 3.3
- score: [0|1|2|null]
- confidence: LOW-MEDIUM
- evidence: "[trích referral]"

## 9. RAW TRANSCRIPT (4 chủ đề, 15 turn)
[Lưu nguyên văn từng turn cho team review]

## 10. METADATA
- bot_version: "em_linh_v7"
- conversation_status: completed | abandoned | escalated
- confirmation_card_response: confirmed | edited
- consent_data_processing: yes | no (ND13)
- brandkit_consent: yes | no
- strategic_followup_promised_in_days: 3
````

---

# TÓM TẮT v7 — BẢN CHÍNH THỨC

## Số liệu tổng quan

| Hạng mục | Số liệu |
|---|---|
| **Phiên bản** | v7 (chính thức) |
| **Cấu trúc** | 4 chủ đề × 15 micro-turn |
| **Rule** | 1 turn = 1 ý (trừ cặp tự nhiên) |
| **Thời gian** | 4-6 phút |
| **Greeting structure** | Quà 🎁 trước → Lý do sau → Promise "nền tảng số" |
| **Promise chiến lược** | 3 ngày qua Zalo |
| **Brandkit coverage** | 14/14 biến input (100%) |
| **Scoring coverage** | 9/9 tiêu chí có signal (100% weight) |
| **Confidence cao** | HIGH 53% + MEDIUM-HIGH 19% = 72% |
| **File MD section** | 10 |
| **Confirmation Card** | Format gạch ngang, list rõ ràng |
| **Closing** | "Thời gian có hạn" + hẹn vịt quay 7 vị |

## Những điểm THEN CHỐT của v7

1. ✅ **Greeting đảo thứ tự** — Quà trước, lý do sau, **promise "nền tảng số"** specific
2. ✅ **Show kiến thức ngành** — thêm "nhôm hệ" → chứng minh hiểu sâu
3. ✅ **Tone chuyên gia khiêm tốn** — "tương tác tốt" thay "em thấy mê" ở phần marketing
4. ✅ **Insight chính xác** — "60-80%" thay vì "80%" cứng
5. ✅ **Mỏ vàng framing 3 lớp** — chốt đơn trong tầm tay → mua thêm → tiếc nếu bỏ quên
6. ✅ **Lý do hỏi gắn chuyên môn** — "kỹ thuật + thẩm mỹ" thay vì "mời ăn"
7. ✅ **Callback đặc sản tinh tế** — chỉ 2 lần (mở + đóng), không spam
8. ✅ **Closing realistic** — 3 ngày, "thời gian có hạn"

---

**HẾT TÀI LIỆU EM LINH MKT v7 — BẢN CHÍNH THỨC**

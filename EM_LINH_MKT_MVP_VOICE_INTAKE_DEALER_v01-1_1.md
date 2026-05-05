# EM_LINH_MKT_MVP_VOICE_INTAKE_DEALER_v01

**Chủ đề:** Em Linh MKT — chatbot/voicebot thu data dealer thực dụng cho Community Gate B  
**Phiên bản:** v01  
**Trạng thái:** DRAFT_FOR_VINH_REVIEW  
**Ngày:** 26/04/2026  
**Owner:** Nguyễn Quốc Vinh  
**Vai trò tài liệu:** Bản tóm tắt riêng cho MVP Em Linh MKT dưới 100 dealer. Không phải PRD full, không phải SOP full, không phải bản pháp lý đã khóa.

---

## 0. Vai trò tài liệu

[Dự thảo] Tài liệu này tách riêng từ Master Plan Cổng B để mô tả MVP của **Em Linh MKT**.

Mục tiêu không phải khoe công nghệ.  
Mục tiêu là giải đúng bài toán lõi:

```text
Dealer nói dễ
→ hệ hiểu đúng
→ tạo hồ sơ dealer chuẩn
→ trả kết quả có ích
→ kéo dealer vào Zalo Mini App / Cộng Đồng Thợ 4.0
→ có dữ liệu sạch để chạy bước sau
```

---

## 1. Kết luận lõi

[Dự thảo]

```text
Em Linh MKT không phải chatbot nói chuyện cho vui.
Em Linh MKT là máy thu data dealer bằng voice/chat có kiểm soát,
dùng hội thoại tự nhiên để tạo Dealer Profile RAW,
rồi kéo dealer vào Mini App và cộng đồng phù hợp.
```

Câu khóa:

```text
Không khoe AI.
Không khoe app.
Không khoe voice.
Chỉ chứng minh: dealer nói được, hệ hiểu được, dealer nhận được lợi ích, và đi vào cộng đồng được.
```

---

## 2. Bối cảnh vấn đề

[Dự thảo] Dealer Việt Nam, đặc biệt ngành cửa/VLXD:

```text
- ngại gõ form dài
- gõ sai chính tả
- không quen trả lời theo schema
- quen nói miệng hơn viết
- có nhiều dữ liệu nằm trong trí nhớ
- kể chuyện vòng vo nhưng bên trong có data quý
```

Vì vậy, kênh vào đúng nhất không phải form thuần, mà là:

```text
Voice-first + Form-confirm
Nói trước, hệ chưng cất, dealer xác nhận sau.
```

---

## 3. MVP đúng bài toán

[Dự thảo] MVP dưới 100 dealer chỉ cần 6 khối:

```text
1. Zalo OA / link campaign
2. Voice/chat intake
3. AI extract theo Dealer Schema
4. Confirmation Card
5. Microsoft 365 Lists
6. Mini App Result + Community Routing
```

**Confirmation Card — thẻ xác nhận:** bản tóm tắt để dealer bấm “Đúng / Sửa”.  
**Community Routing — điều phối cộng đồng:** phân loại dealer để đề xuất nhóm Cộng Đồng Thợ 4.0 phù hợp.

---

## 4. Không làm trong MVP

[Dự thảo] Cắt mạnh để nhanh, rẻ, đúng lõi:

```text
Không realtime voice agent.
Không CPQ sâu.
Không dashboard phức tạp.
Không dealer rank full.
Không House_ID lifecycle full.
Không job routing thật.
Không chia tiền tự động.
Không tích hợp ERP.
Không Power BI đẹp.
Không full app.
```

Những phần này chỉ làm sau khi dealer chịu vào hệ và dữ liệu MVP đủ sạch.

---

## 5. Workflow MVP

[Dự thảo]

```text
Bước 1 — Dealer vào từ campaign / QR / link
Bước 2 — Em Linh MKT hỏi 5 câu bằng voice/chat
Bước 3 — AI bóc Dealer Profile RAW
Bước 4 — Bot gửi Confirmation Card
Bước 5 — Dealer bấm Đúng / Sửa
Bước 6 — Lưu Microsoft 365 Lists
Bước 7 — Bot trả preview kết quả
Bước 8 — Dealer bấm Mini App để nhận đủ kết quả
Bước 9 — Hệ đề xuất nhóm Cộng Đồng Thợ 4.0 phù hợp
Bước 10 — Giao First Mission nhỏ
```

---

## 6. 5 câu hỏi intake tối giản

[Dự thảo] Không hỏi 20 câu. Hỏi 5 cụm thôi.

```text
1. Anh/chị tên gì, cửa hàng tên gì, số Zalo khách hay liên hệ?

2. Mình mạnh nhất mảng nào:
   cửa cuốn, cửa nhôm, bảo trì, tủ bếp, solar, hay VLXD tổng hợp?

3. Mình làm mạnh nhất khu vực nào?

4. Trong 2–3 năm gần đây còn nhớ/gọi lại được khoảng bao nhiêu khách cũ?

5. Mình muốn hệ hỗ trợ trước cái gì:
   bộ mặt số, QR gửi khách cũ, bài đăng, hay trợ lý tư vấn?
```

Sau 5 câu này, AI tự phân loại dealer và tạo hồ sơ nháp.

---

## 7. Voice-first, Form-confirm

[Dự thảo] Cấu hình đúng:

```text
Dealer nói voice
→ AI nghe và chuyển chữ
→ AI tách ý thành field
→ AI hỏi lại field còn thiếu
→ Dealer xác nhận bằng nút / text ngắn
→ tạo Dealer Profile RAW
→ người thật review
→ tạo Dealer_ID sau
```

Luật quan trọng:

```text
Voice để dealer nói tự nhiên.
Schema để hệ thống hiểu đúng.
Confirm để chống data bẩn.
Human review để chống AI nghe sai.
```

---

## 8. Voice không được tự do hoàn toàn

[Dự thảo] Voice phải có khung. MVP dùng voice note ngắn, chưa cần realtime voice.

### 8.1. Cấp nên dùng ngay

```text
Cấp 1 — Voice note async:
Dealer gửi tin nhắn thoại 30–90 giây
→ AI transcribe
→ AI tóm tắt
→ AI hỏi bổ sung
```

### 8.2. Cấp để sau

```text
Realtime voice agent:
Nói chuyện trực tiếp như gọi điện
→ để sau MVP vì phức tạp hơn và dễ sinh data bẩn.
```

---

## 9. Luật chống voice data bẩn

[Dự thảo]

```text
1. Không nhận voice dài quá 90 giây ở MVP.
2. Mỗi voice chỉ hỏi một chủ đề.
3. Không lưu field LOW confidence nếu chưa xác nhận.
4. Số điện thoại phải xác nhận bằng text/nút, không nghe voice.
5. Địa chỉ phải chuẩn hóa lại theo tỉnh/huyện/xã.
6. Tên người và tên cửa hàng phải cho dealer xác nhận lại.
7. Mọi voice transcript là RAW, không phải dữ liệu hiệu lực.
8. Không dùng voice của dealer để training nếu chưa có consent riêng.
9. Không chuyển transcript cho S network.
10. Người thật review trước Dealer_ID chính thức.
```

---

## 10. Dealer Profile Schema tối thiểu

[Dự thảo] Schema MVP cực gọn:

```yaml
dealer_profile_raw:
  dealer_name:
  owner_name:
  phone_or_zalo:
  province:
  district:
  main_category:
  dealer_type:
  customer_base_estimate:
  main_pain_point:
  dl0_priority:
  recommended_group:
  confirmation_status:
  review_status:
```

---

## 11. Output sau voice/chat

[Dự thảo] Sau mỗi phiên, AI phải xuất 3 lớp:

```yaml
voice_intake_result:
  raw_transcript: ""
  cleaned_summary: ""
  extracted_fields:
    dealer_name: ""
    owner_name: ""
    phone: ""
    province: ""
    district: ""
    main_category: ""
    customer_base_estimate: ""
    pain_points: []
    dl0_priority: []
  confidence:
    dealer_name: LOW | MEDIUM | HIGH
    phone: LOW | MEDIUM | HIGH
    province: LOW | MEDIUM | HIGH
    main_category: LOW | MEDIUM | HIGH
  missing_fields: []
  confirm_questions: []
```

**Confidence — độ tin cậy:** AI tự chấm mức chắc của từng trường. Trường nào LOW phải hỏi lại.

---

## 12. Confirmation Card

[Dự thảo] Sau khi AI bóc dữ liệu, phải đọc lại cho dealer xác nhận.

Ví dụ:

```text
Em tóm tắt lại nhé:

Tên đại lý: Cửa Cuốn Minh Phát
Người phụ trách: anh Hùng
Khu vực mạnh: Yên Lạc, Phú Thọ
Ngành chính: cửa cuốn + bảo trì
Khách cũ ước lượng: 50–100
Đau nhất: khách cũ không quay lại + khó marketing
Ưu tiên: tạo QR/link gửi khách cũ

Anh xác nhận đúng chưa?
[Đúng] [Sửa lại]
```

Luật:

```text
Không có xác nhận → không ghi thành Dealer Profile RAW.
Không có human review → không tạo Dealer_ID chính thức.
```

---

## 13. Microsoft 365 Lists làm database MVP

[Dự thảo] Với dưới 100 dealer, dùng Microsoft 365 Lists / SharePoint Lists là đủ.

Không dùng n8n.  
Không dùng SaaS ngoài nếu không cần.  
Webhook tự build đơn giản.

### 13.1. 3 list tối giản

```text
01_DEALER_PROFILE_RAW
02_INTAKE_LOG
03_COMMUNITY_ROUTING
```

### 13.2. 01_DEALER_PROFILE_RAW

```text
Tên dealer
Người phụ trách
Zalo/SĐT
Tỉnh/huyện
Ngành chính
Loại dealer
Khách cũ ước lượng
Nỗi đau chính
Ưu tiên DL0
Trạng thái xác nhận
Trạng thái review
```

### 13.3. 02_INTAKE_LOG

```text
Session ID
Raw transcript
Summary
Missing fields
Confidence
Ngày giờ
```

### 13.4. 03_COMMUNITY_ROUTING

```text
Dealer
Nhóm đề xuất
Lý do đề xuất
Trạng thái mời
Trạng thái tham gia
Nhiệm vụ đầu tiên
```

---

## 14. Webhook tự build đơn giản

[Dự thảo] Chỉ cần 5 endpoint:

```text
POST /webhook/zalo-message
POST /webhook/zalo-voice
POST /api/dealer/extract
POST /api/dealer/confirm
POST /api/community/route
```

| Endpoint | Làm gì |
|---|---|
| `/webhook/zalo-message` | nhận text/button từ Zalo |
| `/webhook/zalo-voice` | nhận voice/file audio |
| `/api/dealer/extract` | gọi AI bóc Dealer Profile |
| `/api/dealer/confirm` | dealer xác nhận đúng/sửa |
| `/api/community/route` | phân nhóm cộng đồng phù hợp |

---

## 15. Flow kỹ thuật tối giản

[Dự thảo]

```text
Zalo OA / Mini App / Web Form
→ Custom Webhook đơn giản
→ AI Transcribe / Extract
→ Microsoft 365 Lists
→ Admin Review
→ Mini App Result Gate
→ Community Routing
```

Không cần n8n.

---

## 16. Community Routing — kéo vào Cộng Đồng Thợ 4.0

[Dự thảo] Đây là phần không được thiếu. Em Linh MKT không chỉ thu data, mà phải kéo dealer vào hệ cộng đồng.

Workflow:

```text
Dealer Profile RAW hoàn thành
→ classify dealer
→ recommend community group
→ ghi COMMUNITY_ROUTING
→ tạo DL0 result preview
→ gửi link Mini App nhận kết quả
→ dealer bấm nhận kết quả
→ hiện nhóm đề xuất
→ dealer join Cộng Đồng Thợ 4.0
→ ghi join_status
```

---

## 17. Phân loại dealer sau intake

[Dự thảo] Sau khi lấy dữ liệu, bot phải gắn 5 nhãn:

```yaml
dealer_classification:
  dealer_type: Dai_Ly | Chu_Xuong | Tho_Doi | Nha_Thau_Nho | S_Dich_Vu | Khac
  main_category: Cua_Cuon | Cua_Nhom_Kinh | Cua_Thep | Tu_Bep | Solar | Bao_Tri_Sua_Chua | VLXD_Tong_Hop
  region: Bac | Trung | Nam
  maturity_level: Moi | Dang_Hoat_Dong | Manh_Dia_Phuong | Co_Network_Rong
  community_fit:
    - Cong_Dong_Tho_4_0
    - Nhom_Cua_Cuon
    - Nhom_Cua_Nhom
    - Nhom_Bao_Tri_Sua_Chua
    - Nhom_Chu_Xuong
    - Nhom_Dealer_Dia_Phuong
```

---

## 18. Luật đề xuất nhóm cộng đồng

[Dự thảo]

| Dữ liệu thu được | Nhóm đề xuất |
|---|---|
| Đại lý cửa cuốn | Nhóm Dealer Cửa Cuốn |
| Đại lý cửa nhôm | Nhóm Dealer Cửa Nhôm Kính |
| Chủ xưởng | Nhóm Chủ Xưởng / Gia Công |
| Thợ đội / S dịch vụ | Nhóm Thợ 4.0 / Bảo trì Sửa chữa |
| Có nhiều khách cũ | Nhóm House_ID Contributor |
| Có đội thợ / network rộng | Nhóm Local Network Captain Candidate |
| Ở cùng địa bàn pilot | Nhóm cộng đồng theo tỉnh/huyện/xã |
| Yếu marketing | Nhóm Em Linh MKT / Marketing thực chiến |
| Muốn học AI/tool | Nhóm AI Tool cho Dealer/Thợ |

---

## 19. Cổng bắt buộc: nhận kết quả qua Mini App

[Dự thảo] Bot chỉ preview kết quả trong chat. Bản đầy đủ phải nhận qua Zalo Mini App.

Lý do:

```text
1. Lấy Zalo_ID / user identity rõ hơn
2. Gắn Dealer_ID sau này
3. Gắn community_join_event
4. Hiện dashboard/hạng sau này
5. Tạo thói quen quay lại Mini App
```

Câu gửi dealer:

```text
Em đã dựng xong hồ sơ số bước đầu cho anh/chị.

Để nhận:
- QR/link riêng
- hồ sơ đại lý nháp
- kịch bản gọi lại khách cũ
- nhóm Cộng Đồng Thợ 4.0 phù hợp

Anh/chị bấm vào Mini App này để xác nhận và nhận kết quả nhé.
```

---

## 20. First Mission — nhiệm vụ đầu tiên

[Dự thảo] Sau khi dealer vào cộng đồng, phải giao nhiệm vụ cực nhỏ.

Gợi ý:

```text
1. Upload ảnh cửa hàng
2. Gửi QR/link cho 3 khách cũ
3. Xác nhận 1 công trình đã làm
4. Mời 1 thợ/dealer quen vào nhóm
```

Mục tiêu: tạo hành động đầu tiên, không để dealer vào nhóm rồi im.

---

## 21. Kết quả trả cho dealer

[Dự thảo] Trả qua Mini App:

```text
1. Hồ sơ đại lý nháp
2. QR/link cá nhân hóa
3. 3 câu giới thiệu đại lý để copy đăng Zalo/Facebook
4. 1 kịch bản gọi lại khách cũ
5. Nhóm Cộng Đồng Thợ 4.0 phù hợp
6. Nhiệm vụ đầu tiên
```

Không cần đẹp. Cần dùng được ngay.

---

## 22. KPI MVP

[Dự thảo] Đo ít nhưng đúng lõi:

```text
1. Dealer hoàn thành intake ≥60%
2. Dealer xác nhận Confirmation Card ≥70%
3. Dealer bấm vào Mini App nhận kết quả ≥50%
4. Dealer join nhóm đề xuất ≥40%
5. Dealer làm First Mission ≥20%
```

Chưa cần đo cash. Chưa cần đo job lớn.

MVP này đo đúng câu hỏi:

```text
Dealer có chịu nói không?
AI có hiểu đúng không?
Dealer có chịu xác nhận không?
Dealer có chịu vào Mini App không?
Dealer có chịu vào cộng đồng không?
Dealer có chịu làm nhiệm vụ đầu tiên không?
```

---

## 23. Chi phí MVP

[Dự thảo] Với 3 nhân sự sẵn có + Microsoft Lists + webhook tự build:

```text
Dry-run 10 dealer:
0 – 500k VND tiền API/tool

MVP dưới 100 dealer:
1 – 5 triệu VND/tháng

Dự phòng rộng:
10 triệu VND/tháng
```

Chi phí chính không phải API.  
Chi phí thật nằm ở:

```text
- thiết kế flow
- test câu hỏi
- sửa schema
- review data
- xử lý dealer nói lan man
- kéo dealer vào Mini App/cộng đồng
```

---

## 24. Stack đề xuất

[Dự thảo]

```text
Zalo OA / QR / Mini App
→ Custom Webhook
→ AI transcribe + extract
→ Microsoft 365 Lists
→ Admin review
→ Mini App result gate
→ Community routing
```

Không dùng n8n.  
Không cần full database riêng ở MVP.  
Không mở Microsoft Lists trực tiếp cho dealer.

---

## 25. Quyền truy cập

[Dự thảo]

```text
Dealer:
- chỉ vào Zalo/Mini App
- không vào Microsoft Lists

Reviewer ADG:
- xem Review Queue / Dealer Profile RAW

Admin:
- xem tất cả

Legal / DPO:
- xem consent/transcript khi cần

Team cộng đồng:
- xem Community Routing
```

---

## 26. Luật khóa MVP

[Dự thảo]

```text
1. Không gọi đây là chatbot thông minh.
2. Không gọi đây là app.
3. Không để voice thay schema.
4. Không để AI tự ghi dữ liệu nếu dealer chưa xác nhận.
5. Không tạo Dealer_ID chính thức nếu chưa human review.
6. Không hỏi quá 5 cụm câu hỏi ở MVP.
7. Không bắt dealer gõ form dài.
8. Không trả full kết quả trong chat — full result qua Mini App.
9. Không kéo dealer vào nhóm chung chung — phải đề xuất nhóm phù hợp.
10. Không đo cash/job lớn ở MVP — đo intake, confirm, Mini App, join group, first mission.
```

---

## 27. Câu khóa cuối

[Dự thảo]

```text
Em Linh MKT MVP =
voice/chat intake có kiểm soát
+ schema cực gọn
+ confirmation card
+ Microsoft Lists
+ Mini App nhận kết quả
+ community routing
+ first mission.

Dealer nói miệng.
AI chưng cất.
Schema khóa dữ liệu.
Dealer xác nhận.
Người thật duyệt.
Mini App trả kết quả.
Cộng đồng giữ dealer lại.
```

---

**Hết file v01.**

**Phiên bản tiếp theo:** v02 sau khi Vinh chốt schema, 5 câu hỏi intake, và 3 Microsoft Lists.

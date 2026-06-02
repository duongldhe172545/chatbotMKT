# Inventory khoa case: Linh MKT va Quynh MKT

## 0. Muc dich va pham vi

File nay chi audit code, khong sua runtime.

Pham vi:

- Linh MKT: `D:\Chatbot_dealer`
- Quynh MKT: `D:\ADG SRC CODE\MINI APP\be-release-v17.11.25\be-release-v17.11.25\Conversation_service`
- Tap trung vao chat intake, xu ly reply va handoff tao logo.
- Khong liet ke cac string UI, auth, admin, storage khong lam thay doi cach bot hieu va tra loi dealer.
- Khong liet ke literal chi nam trong test.

Ky hieu:

- **ACTIVE-GLOBAL**: dang chay voi moi engine, ke ca `llm_first`.
- **ACTIVE-LLM-FIRST**: dang chay trong engine `llm_first`.
- **ACTIVE-FALLBACK**: dang chay khi `llm_first` chu dong roi ve legacy cho edge case.
- **LEGACY-ONLY**: con trong code, chi chay neu doi engine ve `legacy` hoac vao nhanh legacy cu.
- **SOFT-PROMPT**: huong dan LLM trong prompt. Day van la hard-code nghiep vu, nhung khong phai regex ep tung turn.
- **VALIDATION/GUARD**: rule xac thuc hoac an toan. Co hard-code nhung khong dong nghia voi loi kien truc.
- **GENERATION**: hard-code o buoc sinh logo, khong phai loi chat intake.

Trang thai runtime Linh tai luc audit:

- `.env:25`: `CONVERSATION_ENGINE=llm_first`
- `app/core/conversation.py:382-421`: ho tro `legacy`, `planner_shadow`, `planner`, `llm_first`; engine la `llm_first` se goi `handle_asking_llm_first()`.

## 1. Ket luan ngan

Dung, Linh van con nhieu cho khoa case. Hai vi du da neu deu ton tai:

1. Cau hoi `co lua dao khong` bi khoa qua regex va co the bi thay bang reply co dinh:
   - `app/core/regex_markers.py:107-109`
   - `app/llm/defensive_handler.py:33-35`
   - `app/llm/defensive_handler.py:159-187`

2. Token affirmative o greeting bi khoa bang danh sach:
   - `app/core/_conv_greeting.py:117-132`
   - Danh sach co `ok`, `vâng`, `dạ`, `ờ`, `ừ`, `có`, `được`, `đúng`, `rồi`, `chuẩn`, `tiếp`, `làm`, `đi`, `bắt`, `đầu`, `go`...

Quynh cung co hard-code, nhung kieu hard-code khac Linh:

- Quynh khoa **checklist va phong cach trong prompt**, sau do de LLM tu viet cau hoi va tu xu ly hoi thoai.
- Quynh chi co vai nhanh code sau hoi thoai nhu `should_finalize`, extract JSON, chon logo predefined hay AI.
- Trong source Quynh khong tim thay lop regex intent router, `ack_tokens`, reply postprocessor, dictionary sua STT dia danh/hang, hay mapping quan -> tinh tuong duong Linh.

Vi vay, Linh khong chi "co prompt nhieu hon". Linh co nhieu lop code chen vao truoc va sau LLM hon Quynh.

## 2. Linh MKT: cac khoa dang tac dong runtime `llm_first`

### 2.1. Tien xu ly toan cuc truoc khi vao engine

| Trang thai | Source | Khoa case | Anh huong |
|---|---|---|---|
| ACTIVE-GLOBAL | `app/core/conversation.py:116-119` | Moi message deu qua `correct_stt()` | Khong chi voice; ca text dealer go cung bi thay tu theo dictionary. |
| ACTIVE-GLOBAL | `app/llm/brand_correction.py:30-76` | Load mapping va replace case-insensitive, longest-first | Mot typo nam trong dictionary se bi doi truoc khi LLM nhin thay. |
| ACTIVE-GLOBAL | `data/stt_corrections.json:8-101` | 71 mapping brand + 13 mapping tu pho bien | Vi du: `sinh pha` -> `Xingfa`, `cốp men` -> `Koffman`, `ê cô pắc` -> `Ecopark`, `âu sừn pắc` -> `Ocean Park`. |
| ACTIVE-GLOBAL | `app/core/conversation.py:121-129` | Tu dong doi xung ho `anh` -> `chị` neu detect signal | Rule chay moi stage, moi turn. |
| ACTIVE-GLOBAL | `app/core/conversation.py:131-135` | Regex prompt injection va sanitize | Guard an toan, nen giu. |
| ACTIVE-GLOBAL | `app/core/conversation.py:137-148` | Garbage detector va threshold lap 2 lan | Co the gan flag voi input ngan/random. |
| ACTIVE-GLOBAL | `app/core/conversation.py:150-174` | Personal abuse short-circuit | Neu match regex chui bot thi bypass hoi thoai thuong. |

### 2.2. Regex intent router toan cuc

Source chinh: `app/core/regex_markers.py`, thu tu uu tien tai `app/core/intent.py:29-37`.

Thu tu match:

1. `CONFUSION`
2. `DEFENSIVE`
3. `TAM_SU`
4. `REFUSAL`
5. `KHONG_BIET`
6. `EDIT`
7. `AFFIRMATIVE`

| Nhom | Source | Literal/pattern dang khoa | Nhan xet |
|---|---|---|---|
| Affirmative | `app/core/regex_markers.py:15-27` | `ok`, `okay`, `oke`, `okê`, `ô kê`, `okie`, `được`, `chuẩn`, `đúng`, `đồng ý`, `vâng`, `dạ vâng`, `ừ`, `ừa`, `ừm`, `ờ`, `ò`, `ờm`, `yes`, `yeah`, `yep`, `right` | Regex nhom rong. Mot token co the bi hieu la dong y ngoai ngu canh. |
| Refusal | `app/core/regex_markers.py:33-48` | `không cho`, `không nói`, `không muốn`, `kệ đi`, `bỏ qua`, `không cần`, `đừng hỏi`, cac bien the co tu tuc | Chuyen flow sang xu ly tu choi. |
| Khong biet | `app/core/regex_markers.py:54-59` | `không biết`, `không nhớ`, `tùy em`, `sao cũng được`, `chưa có`, `quên mất` | Co ich cho skip/goi y, nhung la keyword-first. |
| Confusion | `app/core/regex_markers.py:68-82` | `là gì`, `là sao`, `ý gì`, `không hiểu`, `cái này là gì`, `thế nào cơ` | Co the bat nham cau hoi tu nhien neu ngu canh rong. |
| Personal abuse | `app/core/regex_markers.py:92-104` | `bot ngu`, `em ngu`, `câm đi`, `im mồm`, `con bot`... | Guard hop ly, nhung van la case lock. |
| Defensive | `app/core/regex_markers.py:107-140` | `lừa đảo`, `scam`, `phí gì`, `em là ai`, `bot à`, `bán data`, `sao tin`, `an toàn không`, cau hoi workflow... | Day la lop khoa gay anh huong ro den test `co lua dao khong`. |
| Tam su | `app/core/regex_markers.py:143-154` | Gia dinh, thoi tiet, suc khoe, nhau/cafe/golf, kinh te kho | Chuyen nhip chat sang handler tam su. |
| Edit | `app/core/regex_markers.py:160-164` | `sửa`, `đổi`, `chỉnh`, `sai rồi`, `nhầm`, `phải là` | Dung cho correction, nhat la confirming. |
| Technical inquiry | `app/core/regex_markers.py:173-199` | Bao gia, bao hanh, tu van ky thuat, hop tac/phan phoi, phap ly/thue, y te, tai chinh | Co the lam bot noi `Phần này em không tư vấn chuyên môn trực tiếp được.` neu bat nham data. |

Technical inquiry co va them ngoai le theo slot:

- `app/core/intent.py:137-140`: slot `3.5` bo qua pattern bao hanh; slot `2.2` bo qua pattern hop tac/phan phoi.
- `app/core/intent.py:173-195`: neu cau mo ta data nhu `anh chịu bảo hành`, `phân phối`, `thi công` va khong phai cau hoi thi bo qua escalation.

Day la ban va da tung gay bug: dealer tra loi mo hinh `phân phối thi công` nhung bi coi nhu hoi tu van chuyen mon.

### 2.3. Greeting co mot bo parser rieng

| Trang thai | Source | Khoa case | Anh huong |
|---|---|---|---|
| ACTIVE-GLOBAL trong stage GREETING | `app/core/intake_edge_cases.py:9-18` | Regex cau hoi loi ich | Bat cac cau nhu `anh được gì`, `nhắn tin được gì`, `tham gia nhận gì`. |
| ACTIVE-GLOBAL trong stage GREETING | `app/core/intake_edge_cases.py:20-24` | Regex ping | Bat `alo`, `hello`, `hi`, `ê`, `test`, `tét`. |
| ACTIVE-GLOBAL trong stage GREETING | `app/core/intake_edge_cases.py:49-67` | Reply loi ich va reply ping co dinh | Reply khong do LLM viet. |
| ACTIVE-GLOBAL trong stage GREETING | `app/core/_conv_greeting.py:117-132` | `ack_tokens` + `is_pure_ack` | Message ngan co mot token trong list co the bi coi la dong y. |
| ACTIVE-GLOBAL trong stage GREETING | `app/core/_conv_greeting.py:134-148` | Heuristic data signal/casual | Neu khong phai ack, code tu quyet dinh forward sang asking hay tra reply casual co dinh. |

Luu y truc tiep ve `ack_tokens`:

- `is_pure_ack = all_ack OR (has_any_ack AND len(tokens) <= 4) OR word_count <= 1`.
- Nghia la bat ky message mot tu nao cung co the roi vao nhanh ack/casual, ke ca tu chua nam trong danh sach.
- Day la lock manh hon regex affirmative chung.

### 2.4. Engine `llm_first` van co cac nhanh bypass LLM

Source: `app/core/llm_first_asking.py`.

| Trang thai | Source | Khoa case | Anh huong |
|---|---|---|---|
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:59-60` | Benefit question | Tra template co dinh, khong goi LLM hoi thoai. |
| ACTIVE-LLM-FIRST | `app/core/intake_edge_cases.py:26-31`, `app/core/llm_first_asking.py:61-65` | Flirt boundary | Cau `đi chơi/cafe/nhậu với anh/chị`, `hẹn hò` tra ACK co dinh roi noi cau hoi fallback. |
| ACTIVE-FALLBACK | `app/core/llm_first_asking.py:162-174` | Technical inquiry, `DEFENSIVE`, `CONFUSION`, `REFUSAL` | Roi ve `_conv_asking.py`, khong con de LLM-first xu ly full history. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:70-72`, `282-299` | Casual chat regex | Bat danh sach cu the: `ăn cơm chưa`, `uống cà phê chưa`, `khỏe không`, `em bao nhiêu tuổi`, `em có người yêu`, thoi tiet... |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:75-80`, `310-333` | Confirm correction hang | Neu message co marker `hãng`, `nhập`, `vật tư`, `dùng`, `xài` hoac dang o slot `2.4`, dictionary co ung vien typo thi hoi co dinh: `ý anh là hãng ... đúng không ạ?`. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:207-243` | Auto-fill branding khi dealer uy quyen chon | Gan gia tri co dinh neu dealer noi `em chọn`, `em gợi ý`, `tùy em`, `sao cũng được`, `anh không rành`, `anh không biết`, `chưa biết`. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:250-263` | Default branding | Mau `xanh đậm phối ghi bạc`; initials fallback `CH`; slogan `Vững chất lượng, bền niềm tin`; style `tối giản hiện đại`. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:302-307` | Detect reply loi LLM | Neu reply chua `trục trặc/kỹ thuật/lỗi kết nối` va `nhắn lại/thử lại/sau ít phút`, code thay bang fallback. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:336-338` | Phone candidate heuristic | Bo het ky tu khong phai so; tu 8 digit tro len coi la phone candidate. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:341-367` | Cau hoi LLM phai hoi dung required focus | Regex marker theo tung field; neu LLM hoi lech required focus thi thay bang fallback. |
| ACTIVE-LLM-FIRST | `app/core/llm_first_asking.py:369-430` | Cau hoi fallback co dinh | Moi field co mot cau hoi template: name, address, phone, product, business model, team, supplier, customer segment, backup, channel, FB, customer storage, pain, payment, warranty, consent, logo preference... |

### 2.5. Checklist ngầm van co thu tu co dinh

Day la guardrail can thiet, nhung van phai tinh la mot kieu khoa flow.

| Source | Noi dung |
|---|---|
| `app/slots/definitions.py:24-29` | Thu tu 17 slot: `1.1` -> `4.2`. |
| `app/slots/definitions.py:32-39` | Required: `1.1`, `1.2`, `1.3`, `2.1`, `2.2`, `4.0`; optional: `2.3` -> `3.5`, `4.2`. |
| `app/slots/definitions.py:91-109` | Mapping slot -> field Linh cu. |
| `app/core/intake_coverage.py:14-34` | Chia pre-consent, post-consent, branding field; resolution field tung optional slot. |
| `app/core/intake_coverage.py:97-114` | Chon `recommended_focus` theo phan tu dau tien con thieu. |
| `app/core/intake_coverage.py:116-133` | Chi summarize khi het required, optional va branding field dang mo. |

Day khong te bang state machine cu vi prompt duoc phep viet tu nhien. Tuy nhien, code van ep chu de tiep theo theo order co dinh.

### 2.6. Reply pipeline sua output sau khi LLM da viet

Source: `app/core/reply_pipeline.py`.

| Trang thai | Source | Khoa case | Anh huong |
|---|---|---|---|
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:94-97` | Detect reply giong cau hoi slot | Phan loai retry. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:98-100` | Cam mot kieu khen ten: `cái tên ... nghe rất ...` | Co the xoa cau khen duoc phep neu wording match. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:102-107` | Cam khen chung chung | Bat `rất chuyên nghiệp`, `rất uy tín`, `địa chỉ rất đẹp`, `rất khoa học`, `rất chu đáo`... |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:109-113` | Cam suy dien dia phuong | Bat `khu vực/ecopark/hà đông/thanh xuân/hưng yên/hà nội/tp hcm` di kem `hạ tầng/phát triển/tiềm năng/...`. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:115-123` | Regex clarify dia chi va clarify explicit | Co the quyet dinh giu/thay reply clarify. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:125-139` | Profanity, joking/testing, false-human claim | `alo`, `test`, `haha`, `đùa`, `em xinh`, `đi cafe`, `đi chơi`; xoa cau `em là người thật`, `không phải bot/AI`. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:146-148` | Off-topic regex | `thời tiết`, `bóng đá`, `nhậu`, `golf`, `chứng khoán`, `crypto`, `coin`. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:191-252` | ACK prefix theo nhom signal | Co reply mau: `Em hiểu anh đang thử em một chút.`, `Em hiểu anh cần chắc chắn trước khi chia sẻ thêm.`, `Em chưa nắm chắc ý anh ở đoạn này.` |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:357-377` | Validate output theo list rule | Neu vi pham, code repair reply. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:599-602` | Drop sentence neu match unsupported praise | Day la ly do mot so cau ninh cua LLM bien mat sau khi generate. |
| ACTIVE-GLOBAL | `app/core/reply_pipeline.py:612-619` | Chi giu cau hoi cuoi neu reply co nhieu cau hoi | Gioi han nhiet hoi. |

Day la diem quan trong: prompt co the da yeu cau Linh noi mem va ninh vua phai, nhung reply pipeline lai co the xoa ca cau khen neu wording cham blacklist. Vi vay output co luc mem, co luc cut.

### 2.7. Khoa case `khong lua dao`

Day la nhanh co dinh ro nhat.

| Source | Hanh vi |
|---|---|
| `app/core/regex_markers.py:107-109` | `lừa đảo`, `scam`, `phí gì`, `tốn tiền`, `chi phí gì`, `miễn phí à` -> `DEFENSIVE`. |
| `app/core/llm_first_asking.py:162-174` | `DEFENSIVE` roi ve legacy handler. |
| `app/llm/defensive_handler.py:33-35` | Folded regex tiep tuc bat `lua dao`, `scam`, `mat phi`, `co phi`, `phi gi`, `ton tien`, `mien phi that`. |
| `app/llm/defensive_handler.py:59-87` | Prompt defensive co san kich ban tra loi cho lua dao/phi, tang tien, ai lam/cong ty nao. |
| `app/llm/defensive_handler.py:159-187` | Neu reply LLM thieu `không lừa đảo`, `không mất phí/hoàn toàn miễn phí`, va marker privacy thi thay toan bo bang template co dinh. |
| `app/llm/defensive_handler.py:31`, `81-87` | Tu lan defensive thu 3 thi doi phan ket thanh offer dung. |

Nhan xet: cam ket bao mat la nghiep vu hop ly. Van de la no dang la deterministic reply replacement, nen rat de co cam giac may moc.

### 2.8. Xung ho va sua van phong bang regex

| Source | Khoa case |
|---|---|
| `app/core/address_form.py:23-44` | Regex request xung ho: `gọi/kêu ... là`, `xưng ...`. |
| `app/core/address_form.py:48-124` | Blacklist xung ho: tu tuc, nhan vat nhay cam, danh xung ton giao, slur vung mien. |
| `app/core/address_form.py:166-210` | Set ten nu va phrase nhu `em là nữ`, `là chị`, `chị mà`, `chị chứ` de doi default sang `chị`. |
| `app/core/address_form.py:213-223` | Sua loi vocative nhu `Hưng ơi` thanh cach goi co xung ho. |
| `app/core/conversation.py:214-224` | Sau moi reply, ep adapt `anh/chị` va repair vocative. |
| `app/core/conversation.py:424-472` | Sua opening `Dạ/Vâng` lap lien tuc bang prefix list. |

### 2.9. Validation va guard can phan biet voi khoa script

Nhung rule nay co hard-code nhung phan lon nen giu.

| Source | Rule | Danh gia |
|---|---|---|
| `app/llm/extractors/validators.py:25-49` | Phone digits-only, format 10-11 so bat dau `0` hoac `84` | Validation can thiet. |
| `app/llm/extractors/validators.py:57-80` | Address dai 3-500 ky tu, reject blacklist | Validation/PR guard. |
| `app/core/intake_profile_merge.py:89-124` | `llm_first` chi persist address khi parse ra tinh/thanh ro | Guard hop ly: dia chi chua ro thi hoi lai, khong tu confirm. |
| `app/core/intake_profile_merge.py:16-19`, `127-139` | Loai placeholder nhu `cả hai`, `hai hãng đó`, `như trên` khoi list value | Tranh luu placeholder, nhung can LLM resolver hieu ngu canh de fill gia tri that. |
| `app/core/address_parser.py:30-55`, `94-108` | Alias tinh/thanh va whitelist 63 tinh | Normalization hop ly. |
| `app/core/address_blacklist.py:57-72`, `data/address_blacklist.json:8+` | Substring blacklist dia chi nhay cam | Guard nghiep vu. |
| `app/guards/injection.py:28-60` | Regex jailbreak EN/VN | Security guard. |
| `app/guards/drift.py:36-48`, `117-165` | Remove vocab noi bo, Viet hoa mot so tu, toi da 1 emoji/reply | Style guard; gioi han emoji co tac dong van phong. |
| `app/guards/hallucinate.py:31-37`, `121-136` | Kiem value extract co evidence, tru mot so enum cho phep inference | Data guard. |
| `app/guards/hallucinate.py:146-164`, `214-232` | Cam tu khen premium/quy mo va bịa dac tinh dia phuong | Hallucination guard; co the can tune neu xoa khen mem hop ly. |
| `app/core/brand_check.py:4-7`, `56-71` | Brand la duoc flag cho admin nhung van luu raw | Day khong phai khoa dealer input. |

## 3. Linh MKT: cac khoa nam trong legacy/fallback

`llm_first` khong dung state machine cu cho happy path, nhung van roi ve `_conv_asking.py` khi technical inquiry, defensive, confusion hoac refusal. Ngoai ra doi `.env` ve `legacy` se kich hoat toan bo lop nay.

### 3.1. Slot templates va ACK deterministic

| Trang thai | Source | Noi dung |
|---|---|---|
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/slots/templates.py:346-362` | Moi slot co bien the cau hoi chon theo hash session va attempt retry. |
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/core/_conv_helpers.py:36-79` | `_PARTIAL_FIELD_QUESTIONS`: cau hoi co dinh khi slot multi-field con thieu field. |
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/core/_conv_helpers.py:145-200+` | `_gen_direct_ack`: ACK co dinh theo ten, dia chi, san pham, mo hinh, doi tho, hang, kenh... |
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/core/bridge_rotation.py:23-35` | Pool 11 bridge nhu `À mà anh ơi`, `Em hỏi thêm xíu`, `Tiện đây em hỏi`... |

### 3.2. Patch keyword theo slot

Source: `app/core/_conv_asking.py:1183-1321`.

`_apply_deterministic_slot_fixes()` patch cac cau ngan ma extractor co the bo sot:

- Slot `1.3`: regex `0\d{8,10}` de lay mot/doi phone.
- Slot `2.2`: mapping keyword mo hinh nhu `phân phối`, `đại lý`, `bán lẻ`, `thi công`, `xưởng`, `sản xuất`.
- Slot `2.4`: supplier/nhom khach/backup.
- Slot `2.5`: `giống số trên`, nguon gioi thieu, khach tu tim, khong co online.
- Slot `2.6`: Facebook, network manh/nhe.
- Slot `3.1`: khach cu/gioi thieu.
- Slot `3.2`: khong luu danh sach.
- Slot `3.3`: khong co pain.
- Slot `3.4`, `3.5`, `4.0`: cac phrase thanh toan, bao hanh, consent.

Danh sach helper phrase:

| Source | Nhom literal |
|---|---|
| `app/core/_conv_asking.py:1371-1385` | `giống số trên`, `số cũ`, `dùng số đó`, `số cá nhân`... |
| `app/core/_conv_asking.py:1388-1397` | `người quen`, `giới thiệu`, `khách quen`, `truyền miệng`... |
| `app/core/_conv_asking.py:1400-1409` | `khách tự tìm`, `tự tìm đến`, `uy tín nên khách`... |
| `app/core/_conv_asking.py:1412-1423` | `không có kênh nào`, `không có Facebook`, `không quảng cáo`... |
| `app/core/_conv_asking.py:1426-1436` | Network manh: `giới thiệu cho nhau`, `thợ giới thiệu`, `đối tác giới thiệu`... |
| `app/core/_conv_asking.py:1439-1450` | Khong co Facebook. |
| `app/core/_conv_asking.py:1453-1463` | Network nhe: `thỉnh thoảng`, `ít thôi`, `đôi khi`, `lâu lâu`. |
| `app/core/_conv_asking.py:1466-1477` | Khong luu khach: `không lưu`, `không ghi lại`, `không quản lý`... |
| `app/core/_conv_asking.py:1480-1491` | Khong pain: `không khó`, `không vướng`, `ổn hết`... |
| `app/core/_conv_asking.py:1494-1519` | Affirmative sau soft-no va ACK-only legacy. |
| `app/core/_conv_asking.py:1558-1586` | Dealer uy quyen bot chon mau: `em gợi ý`, `em chọn`, `tùy em`, `màu gì cũng được`... |

### 3.3. Mapping dia chi cu the

| Trang thai | Source | Khoa case |
|---|---|---|
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/core/_conv_asking.py:1653-1659` | Loi khen rieng cho `Ecopark`, `Ocean Park`. |
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/core/_conv_asking.py:1663-1715` | Set keyword tinh/thanh viet co dau va khong dau. |
| ACTIVE-FALLBACK / LEGACY-ONLY | `app/core/_conv_asking.py:1722+` | Mapping dia danh -> dia chi day du: `ecopark`, `ocean park`, Ha Dong, Thanh Xuan, Cau Giay, Dong Da, Hoang Mai, Ba Dinh, Long Bien, Tay Ho, Nam/Bac Tu Liem, Hai Ba Trung, Hoan Kiem, Thanh Tri, Gia Lam, Dong Anh; quan/huyen TP.HCM; mot so quan Da Nang. |
| LEGACY DERIVE | `app/core/_conv_derive.py:204-210` | Rieng `ocean park` -> Ha Noi/Gia Lam; `ecopark` -> Hung Yen/Van Giang. |

Day la cho can phan biet:

- Dictionary STT `ê cô pắc`, `âu sừn pắc` dang ACTIVE-GLOBAL.
- Mapping dia danh chi tiet va loi khen Ecopark/Ocean Park nam trong legacy/fallback.
- Quynh khong co mapping code tuong duong; Quynh de LLM tu hieu phien am/ngu canh.

### 3.4. Escalation co threshold co dinh

| Source | Rule |
|---|---|
| `app/core/abuse_detector.py:62-102` | Chui bot: L1, L2, L3; lan 3 dung session. |
| `app/llm/defensive_handler.py:31`, `81-87` | Defensive: tu lan 3 offer dung. |
| `app/core/edge_cases.py:100-132` | Optional refusal lien tiep 3 lan -> rush mode. |
| `app/core/edge_cases.py:205-227` | Tam su: 1-2 nhip engage, 3-4 nhip cat nhe, >=5 soft-end. |
| `app/core/edge_cases.py:248-309` | Voice fail: regex noise va escalation 3 cap. |

### 3.5. Persona detector co rule scoring

Source: `app/core/dealer_type.py`.

- `app/core/dealer_type.py:30-36`: detect tai turn `3`, `8`, `13`; score min `2.0`, switch threshold `5.0`.
- `app/core/dealer_type.py:43-69`: regex profanity, ALL CAPS, so lieu/khoe, emoji, defensive phrase, message ngan.
- `app/core/dealer_type.py:167-210`: tinh score va chon type.
- `app/core/dealer_type.py:246-313`: immediate/persistent upgrade khi chui + caps.

Day la mot lop rule-based persona ma Quynh khong co.

## 4. Linh MKT: prompt cung co khoa nghiep vu

Source: `app/llm/linh_conversation_prompt.py`.

Day la **SOFT-PROMPT**, khong phai regex replacement:

- `app/llm/linh_conversation_prompt.py:55-65`: luat ninh mem, khong bia, khong lap `Em đã ghi nhận`, khong khen vo can cu.
- `app/llm/linh_conversation_prompt.py:67-76`: moi cau hoi can ly do; neu ten hang/dia chi/ten rieng chua ro thi hoi lai, khong tu confirm.
- `app/llm/linh_conversation_prompt.py:78-100`: checklist Linh day du: thong tin co ban, san pham, mo hinh, doi tho, hang, kenh, FB/network, khach cu, luu khach, pain, coc/cong no, bao hanh, consent, mau, initials, slogan, style.
- `app/llm/linh_conversation_prompt.py:110-117`: hieu ACK ngan theo cau hoi truoc, hieu reference nhu `2 hãng đó`, `cả hai`, `như trên`, nhung cau hoi chinh van phai bam `recommended_focus`.

Prompt dang co dung y do "cau truc chat giong Quynh, noi dung checklist theo Linh". Tuy nhien output van bi cac lop code o muc 2 va 3 chen vao.

## 5. Linh MKT: khoa o buoc tao logo

Day khong phai khoa chat, nhung liet ke rieng de khong bo sot.

Source: `app/core/logo_generator.py`.

- `app/core/logo_generator.py:32-49`: palette va color map co dinh.
- `app/core/logo_generator.py:52-61`: chi sinh logo khi `brandkit_consent == "yes"`.
- `app/core/logo_generator.py:67-78`: luon tao dung 5 SVG variant co dinh:
  - `Khung monogram`
  - `Nét cửa hiện đại`
  - `Huy hiệu xưởng`
  - `Wordmark khối`
  - `Biểu trưng tinh gọn`
- `app/core/logo_generator.py:107-122`: initials fallback va slogan fallback `Vững chất lượng, bền niềm tin`.

Day la MVP renderer deterministic, khong phai gen anh AI giong Quynh.

## 6. Quynh MKT: cac cho khoa case that su tim thay

### 6.1. Loi chat intake cua Quynh la LLM-first

| Source | Hanh vi |
|---|---|
| `app/services/session.py:3-24` | Moi session co `ConversationBufferMemory`, het han sau 4 gio. |
| `app/api/v1/chat_router.py:24-38` | Tao `LLMChain` voi memory session; reply lay truc tiep tu `session_chain.invoke()`; sau do moi goi `should_finalize()`. |
| `app/core/llm.py:16-19`, `90-99` | Prompt runtime doc tu DB; neu DB chua co thi moi dung default prompt trong source. |
| `app/database/crud.py:217-235` | `get_latest_prompt()` lay prompt DB moi nhat va inject `{history}`, `{user_input}`. |

Can noi chinh xac: source cho thay kien truc Quynh. Prompt Quynh dang chay thuc te co the da duoc sua trong DB qua admin, nen audit source khong duoc phep khang dinh DB hien tai giong 100% `default_prompt_text`.

### 6.2. Checklist va phong cach bi khoa mem trong prompt

Source fallback/reset:

- `app/core/llm.py:19-88`
- `app/api/v1/prompt_router.py:54-123`
- `app/database/seed_db.py:70-135`

Noi dung prompt:

1. Mo dau tao niem tin.
2. Xin ten xuong, dia chi, SDT.
3. Hoi mo hinh: san xuat / thuong mai / ket hop.
4. Hoi san pham chu luc.
5. Hoi tung san pham: hang vat tu ua dung va ly do; neu khong biet thi goi y 3-5 lua chon.
6. Hoi khach hang muc tieu.
7. Hoi phan khuc: cao cap / trung cap / binh dan.
8. Goi y phong cach logo, bieu tuong, mau.
9. Goi y slogan.
10. Khi du thong tin thi tong hop va hoi xac nhan.

Prompt Quynh co cau mau va option mau, nhung co luat:

- `app/core/llm.py:82-87`: khong doc y nguyen cau mau; dien dat lai theo ngu canh; bat buoc giai thich ly do truoc moi cau hoi.

Day la khoa nghiep vu nhung van de LLM tu dieu phoi hoi thoai.

### 6.3. Extract schema co dinh sau hoi thoai

Source: `app/services/chatbot_service.py:11-80`.

Sau khi finalize, Quynh goi LLM extract JSON co schema co dinh:

- `session_id`
- `dealer_id`
- `phone_number`
- `brand_name_full`
- `location`
- `service_categories`
- `service_details[]`: `service_name`, `preferred_brand`, `reason`
- `main_customer`
- `market_segment`
- `survey_summary`
- `slogan`
- `logo_style`
- `main_color`
- `logo_shape`

`app/services/chatbot_service.py:57`: dung regex `\{[\s\S]*\}` de boc JSON tu output.

Day la schema-after: extract sau hoi thoai, khong phai slot router ep tung turn.

### 6.4. Finalize judge co prompt mau, khong co regex affirmative router

Source: `app/services/chatbot_service.py:100-128`.

- `should_finalize()` goi LLM de phan tich lich su va message moi nhat.
- Prompt dua vi du confirm: `đúng và đủ`, `chốt`, `ok`, `hoàn tất`.
- Prompt noi ro chon phuong an `1`, `2`, `5` khong phai finalize.
- JSON response duoc boc bang regex `\{.*\}`.

Quynh co vi du affirmative trong prompt finalize. Quynh **khong co** danh sach `ack_tokens` va `is_pure_ack` o greeting giong Linh.

### 6.5. Chon logo sau finalize co hard-code

| Source | Khoa case |
|---|---|
| `app/services/chatbot_service.py:180-197` | Neu `logo_shape` chua keyword `cách điệu`, `tên thương hiệu`, `wordmark`, `logo chữ`, `logotype` thi goi AI generate; neu khong thi recommend logo predefined. |
| `app/services/logo_service.py:25-27` | Default brand `Thương hiệu`, style `hiện đại`, color `xanh dương`. |
| `app/services/logo_service.py:60-70` | Mapping 10 folder logo: abstract geometric, building/tower, door, gear, house, lock, rolling door, roof, shield, window. |
| `app/services/logo_service.py:73-114` | LLM chon mot category trong danh sach co dinh; fallback folder `logos/abstract_geometric/`. |
| `app/services/logo_generator.py:101-107` | API sinh anh co model `seedream-4-0-250828`, `size=2K`, `watermark=False`. |

## 7. Quynh MKT: cac lop KHONG tim thay trong source

Da quet `app/core`, `app/services`, `app/api` cua Conversation Service. Khong tim thay lop tuong duong Linh cho:

- Regex intent router affirmative/refusal/confusion/defensive/tam-su/technical inquiry.
- `ack_tokens` greeting nhu `tiếp`, `làm`, `đi`.
- Template deterministic rieng cho `không lừa đảo`.
- Reply pipeline xoa cau khen, chen ACK, chi giu cau hoi cuoi.
- Dictionary sua phien am STT/typed text nhu `ê cô pắc`, `âu sừn pắc`, `cốp men`.
- Mapping hard-code `Ecopark -> Văn Giang, Hưng Yên`, `Ocean Park -> Gia Lâm, Hà Nội`.
- State machine 17 slot, retry, rush mode, persona scoring turn `3/8/13`.

Dieu nay khong co nghia Quynh khong co rule. Quynh co rule nghiep vu trong prompt va co rule finalize/logo sau chat. Diem khac la rule cua Quynh it chen vao viec viet reply tung turn hon.

## 8. Doi chieu truc tiep cac case da test

| Case | Linh | Quynh |
|---|---|---|
| `có lừa đảo không em` | Regex `DEFENSIVE` -> legacy defensive handler -> co the thay reply bang template co dinh. | Khong tim thay regex/template code rieng. LLM main chat tu tra loi theo prompt + history. |
| `ok em`, `tiếp đi`, `làm đi` o greeting | `ack_tokens` va heuristic ngan trong `_conv_greeting.py`. | Khong tim thay greeting token parser tuong duong. |
| `alo alo` | Ping regex + reply fixed trong Linh greeting; reply pipeline cung classify `alo` la joking/testing. | Khong tim thay ping regex code rieng. |
| `đi chơi với anh đi rồi anh cho` | Flirt regex -> ACK fixed -> cau hoi fallback fixed. | Khong tim thay flirt branch code rieng. |
| `sinh pha`, `cốp men` | Dictionary typed/STT replace truoc LLM; typed brand co the hoi confirm theo dictionary. | Khong tim thay dictionary code. LLM phai tu hieu. |
| `ê cô pắc`, `âu sừn pắc` | Dictionary doi thanh Ecopark/Ocean Park; legacy con co mapping dia chi cu the. | Khong tim thay mapping code. Neu Quynh hieu duoc thi do nang luc LLM/prompt/context, khong phai dictionary tuong duong trong source. |
| `anh phân phối thi công` | Technical regex tung bat nham; Linh da them skip/data exception. | Khong co technical regex router tuong duong. |
| Ninh mem theo context | Prompt Linh co yeu cau, nhung pipeline co blacklist va drop sentence. | Prompt Quynh khuyen khich noi mem; reply duoc tra truc tiep hon. |

## 9. Phan loai: khoa nao nen giu, khoa nao can xem lai

### Nen giu lam guardrail

- Validation phone.
- Address chua ro thi hoi confirm, khong tu persist.
- Prompt injection guard.
- Personal abuse escalation co gioi han.
- Hallucination guard khong bia quy mo, uy tin, dia phuong.
- Brand unknown chi flag admin, khong reject dealer.
- Checklist field Linh lam bo nho nghiep vu.

### Nen xem lai vi lam Linh kem tu nhien hon Quynh

- Greeting `ack_tokens` va heuristic `word_count <= 1`.
- Regex intent rong chay truoc LLM, nhat la `DEFENSIVE`, `CONFUSION`, `TECHNICAL_INQUIRY`.
- Roi ve legacy handler cho defensive/confusion/refusal thay vi de mot LLM-first edge-case prompt nhin full history.
- Template fixed cho benefit, ping, flirt neu dung qua nhieu.
- Reply pipeline chen ACK generic va xoa cau khen theo blacklist phrase.
- Required-focus regex reject output LLM va thay bang fallback fixed.
- Dictionary typed text thay truc tiep moi message; voi brand/dia danh khong chac nen dung candidate + confirm thay vi auto-replace/persist.
- Legacy mapping dia chi cu the va loi khen Ecopark/Ocean Park.
- Persona scoring va bridge rotation neu tiep tuc tham gia vao flow moi.

## 10. Ket luan kien truc

Quynh khong phai "khong hard-code". Quynh hard-code checklist, phong cach, schema extract, finalize rule va logo routing. Tuy nhien, chat intake cua Quynh van la:

`full history -> mot LLM hoi thoai -> reply tu nhien -> LLM finalize/extract sau`

Linh hien tai la:

`correct dictionary -> regex guards/intents -> LLM-first hoac legacy branch -> checklist focus -> LLM reply -> regex reply repair/drop/prefix -> output`

Muon Linh giong Quynh hon thi khong nen xoa tat ca validation. Can giam nhung rule dang dong vai tro "bien kich hoi thoai", chi giu rule dong vai tro guardrail va checklist ngam.


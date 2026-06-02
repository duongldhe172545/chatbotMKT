# Linh MKT Quynh-Style Rebuild Plan

Ngay viet: 2026-06-01

Trang thai: **ke hoach moi, thay the huong planner-first trung gian**.

Muc tieu cua plan nay khac voi ban `_analysis/linh-mkt-implementation-plan.md` truoc do. Ban truoc van co xu huong boc planner quanh cau truc slot/state-machine cua Linh. Huong moi nay di theo dung y: **cau truc hoi thoai giong Quynh MKT, noi dung nghiep vu/cau hoi theo Linh MKT**.

Ket luan ngan:

> Linh khong nen tiep tuc la "slot machine co LLM phu tro". Linh can thanh "LLM conversation agent co schema/guard theo sau".

---

## 1. Dinh nghia dung muc tieu

### 1.1. Hoc Quynh o tang nao?

Quynh MKT tot hon Linh MKT o tang **kien truc hoi thoai**:

- LLM la nguoi noi chuyen chinh.
- LLM nhin lich su hoi thoai de quyet dinh nen noi gi tiep.
- Khong ep nguoi dung di tung slot may moc.
- Khong can hard-code qua nhieu case dia danh/cau tra loi ngan.
- Extract thong tin tu hoi thoai sau do, thay vi bat user phai tra loi dung slot hien tai.
- `should_finalize` cung dua tren lich su hoi thoai, khong chi dua vao state hien tai.

Quynh khong phai tot hon vi co gen anh. Gen anh la phan sau. Cai can hoc la **cach dat LLM vao ghe lai hoi thoai**.

### 1.2. Giu Linh o tang nao?

Linh van giu:

- Nhan vat: Em Linh MKT.
- Muc dich: tang bo thuong hieu so cho dealer trong Cong Dong Tho 4.0.
- Noi dung can hoi: ten chu, ten cua hang, dia chi/khu vuc, so Zalo/SDT, san pham, hang vat tu, mo hinh kinh doanh, nguon khach, phan khuc, phong cach thuong hieu, mau sac, slogan, dong y nhan bo brandkit.
- Tone Linh: le phep, gan gui, hoi co ly do, khong giong form hanh chinh.
- API, DB, admin, export md, voice, frontend neu khong can doi.

Khong giu:

- Slot-first la nao chinh.
- ACK generator roi append cau hoi template.
- Regex/case mapping la cach lam thong minh chinh.
- `current_slot` quyet dinh turn tiep theo.

---

## 2. Vi sao plan planner-first cu van chua du?

Plan cu co tien bo so voi legacy, nhung van sai huong neu muc tieu la giong Quynh:

```text
User message
  -> detect intent
  -> check planner eligible
  -> planner tra facts + assistant_reply
  -> merge profile
  -> fallback legacy cho nhieu case
```

Van de:

- Planner van bi xem nhu mot module nam trong khung ASKING cu.
- Eligibility/fallback khien nhieu turn tu nhien van quay ve legacy.
- `current_slot`, consent slot, address blacklist, regex guard van anh huong flow qua nhieu.
- Planner van bi yeu cau tra structured result nhu mot "state planner", chua thuc su la mot chatbot nhu Quynh.
- De sua cac case cu the, ta de bi keo vao hard-code: `Ecopark`, `Ocean Park`, `Gia Lam`, `o e`, `u e`, ...

Neu tiep tuc huong cu, Linh se tot hon mot it nhung van mang cam giac "form chat".

Huong moi:

```text
User message + full conversation history + Linh business brief + current profile
  -> LLM conversation brain viet reply chinh
  -> extractor doc hoi thoai de cap nhat profile
  -> coverage guard kiem tra con thieu gi
  -> confirmer doc history de quyet dinh co du/chot chua
```

Day moi gan voi Quynh.

---

## 3. Kien truc dich

### 3.1. Flow moi trong ASKING

```text
POST /api/chat
  -> load session/profile
  -> global guards co ban:
       timeout, prompt injection, abuse, voice fail, rate limit
  -> append dealer message vao history
  -> LLM fact extractor doc recent/full history
       cap nhat profile bang facts co evidence
  -> compute coverage tu profile
       required/optional con thieu, co the confirm chua
  -> LLM conversation brain doc:
       full recent history
       profile hien tai
       coverage/checklist ngam
       Linh persona + business script
       last user message
     va viet 1 assistant_reply tu nhien
  -> reply guards:
       cam scoring vocab, PII leak, hallucination adjectives, prompt injection echo
  -> append bot reply
  -> save session/profile
  -> return API response nhu cu
```

Diem cot loi: **assistant_reply khong den tu slot template nua**.

### 3.2. `current_slot` trong kien truc moi

`current_slot` khong bi xoa ngay vi admin/test/frontend co the dang dung. Nhung vai tro moi la:

- debug pointer;
- field focus gan nhat;
- thong tin phu cho analytics;
- fallback legacy neu can.

Nó **khong duoc lam dao dien hoi thoai**.

### 3.3. State machine trong kien truc moi

State machine khong con quyet dinh "hoi cau nao tiep".

Vai tro moi:

- xac dinh stage lon: `GREETING`, `ASKING`, `CONFIRMING`, `DONE`;
- chan confirm khi required fields chua du;
- mark done/timeout/escalation;
- guard loop/risk.

Trong ASKING, nguoi viet kich ban la LLM conversation brain.

---

## 4. Module moi can co

### 4.1. `app/core/llm_first_asking.py`

Day la engine ASKING moi, thay happy path cua `_conv_asking.py`.

Interface de xuat:

```python
def handle_asking_llm_first(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> str:
    ...
```

Trach nhiem:

- goi extractor de cap nhat profile;
- tinh coverage;
- goi conversation brain de viet reply;
- cap nhat `session.current_slot` chi nhu focus/debug;
- chuyen `CONFIRMING` neu conversation brain/coverage deu dong y;
- fallback neu LLM loi.

Khong lam:

- khong append slot template;
- khong goi ACK generator cho happy path;
- khong hard-code dia danh de quyet dinh reply.

### 4.2. `app/llm/linh_conversation_prompt.py`

Prompt chinh cua Linh, tuong duong vai tro prompt Quynh.

Noi dung prompt gom:

- Ban la Em Linh MKT.
- Muc tieu cua cuoc noi chuyen.
- Qua tang sau cuoc noi chuyen: logo, danh thiep, video gioi thieu.
- Cach noi: le phep, gan gui, hoi tung cau, co ly do truoc cau hoi nhay cam.
- Checklist nghiep vu Linh, nhung noi ro: checklist la **ngam**, khong doc nhu form.
- Doc lich su hoi thoai truoc khi hoi tiep.
- Neu dealer hoi nguoc "anh duoc gi", tra loi loi ich roi moi xin phep tiep tuc.
- Neu dealer tra loi nhieu thong tin mot luc, ghi nhan tat ca, khong hoi lai.
- Neu dealer sua thong tin, chap nhan va noi lai ngan gon.
- Neu dealer tra loi ngan nhu "ok", "uh", "ờ em", hieu theo cau hoi ngay truoc.
- Neu chua chac mot dia danh/ten rieng, hoi xac nhan tu nhien, khong crash.
- Hoi toi da 1 cau hoi chinh moi turn.
- Khi du thong tin, tom tat va hoi xac nhan.

Prompt nay **khong phai JSON-only prompt**. No sinh reply tu nhien.

### 4.3. `app/llm/intake_fact_extractor.py`

Extractor rieng, doc hoi thoai de cap nhat profile.

Gan voi Quynh: Quynh extract profile tu full conversation khi finalize. Linh can luu state moi turn, nen extractor chay moi turn hoac moi vai turn.

Interface:

```python
def extract_intake_facts(
    history_text: str,
    current_profile: DealerProfileRaw,
    client: LLMClient,
) -> IntakeFacts:
    ...
```

Output:

```python
class IntakeFact(BaseModel):
    field: str
    value: Any
    evidence: str
    confidence: Literal["low", "medium", "high"]
    is_correction: bool = False

class IntakeFacts(BaseModel):
    facts: list[IntakeFact]
    uncertainty_notes: list[str] = []
```

Nguyen tac:

- Fact phai co evidence trong user history.
- Khong extract field derived nhu `brand_name_short`, `slogan_options` trong buoc nay.
- Khong hard-code dia danh vao code. Neu user noi "âu sừn pắc" va LLM hieu la Ocean Park thi evidence ghi ro.
- Neu khong chac, de uncertainty hoac hoi lai, khong doan cung.

### 4.4. `app/core/intake_profile_merge.py`

Merge facts vao `DealerProfileRaw`.

Khac voi hard-code merge hien tai:

- validate field bang validator cu;
- scalar chi fill khi trong;
- correction chi overwrite khi confidence cao va co evidence;
- list merge unique;
- invalid fact bi bo qua, khong crash;
- return merge summary cho test/log.

Khong nen canonicalize dia danh bang bang mapping trong happy path moi. Neu muon derive tinh/huyen, dung extractor/LLM hoac parse phu, nhung khong duoc de no dieu khien hoi thoai.

### 4.5. `app/core/intake_coverage.py`

Thay `current_slot` bang coverage/checklist ngam.

Output:

```python
class IntakeCoverage(BaseModel):
    required_missing: list[str]
    useful_optional_missing: list[str]
    filled_fields: list[str]
    can_summarize: bool
    recommended_focus: str | None
    reason: str
```

Coverage la input cho LLM, khong phai script cung.

### 4.6. `app/llm/intake_finalize_judge.py`

Giong `should_finalize` cua Quynh.

Vai tro:

- doc history;
- doc last user message;
- doc profile/coverage;
- quyet dinh user da xac nhan tom tat/chot chua.

Output:

```json
{
  "should_finalize": true,
  "reason": "...",
  "missing_blockers": []
}
```

Khong dung rule "message == ok" mot cach don gian, vi "ok" co the chi la dong y tiep tuc.

---

## 5. Cau truc prompt Linh theo kieu Quynh

Prompt Linh nen la mot "business brief" dai, nhat quan, giong Quynh.

Khung prompt:

```text
Ban la Em Linh MKT...

MUC TIEU
Tro chuyen voi chu dai ly/cua hang trong nganh cua, nhom kinh, tu bep, VLXD...
Thu thap du thong tin de lam bo thuong hieu so mien phi...

PHONG CACH
- Xung em/anh...
- Le phep, am ap, noi nhu nguoi that...
- Khong doc checklist...
- Hoi toi da 1 cau hoi chinh...
- Luon noi ly do ngan gon truoc khi hoi thong tin nhay cam...

CHECKLIST NGAM
1. Ten anh + ten cua hang
2. Khu vuc/dia chi
3. SDT/Zalo de gui bo thuong hieu
4. San pham/dich vu chinh
5. Hang vat tu/thuong hieu hay dung
6. Mo hinh kinh doanh
7. Nguon khach/nhom khach
8. Phan khuc
9. Phong cach/mau sac/slogan neu co
10. Dong y nhan brandkit

LUAT HOI THOAI
- Neu user tra loi nhieu field, ghi nhan het.
- Neu user hoi "anh duoc gi", tra loi loi ich that ngan gon.
- Neu user noi khong biet, goi y 2-3 lua chon.
- Neu user sua thong tin, cap nhat va tiep tuc.
- Neu user tra loi ngan, hieu theo cau hoi ngay truoc.
- Neu du thong tin, tom tat va hoi xac nhan.

DU LIEU HIEN CO
{profile_summary}

CHECKLIST CON THIEU
{coverage_summary}

LICH SU GAN DAY
{history}

TIN NHAN MOI NHAT
{message}
```

LLM chi tra text reply, khong tra JSON trong prompt nay.

---

## 6. Runtime chi tiet

### 6.1. Khi user noi binh thuong

Vi du:

> Anh ten Hung, cua hang Solar Hung Phat o Gia Lam, chuyen Xingfa voi Austdoor.

Flow moi:

1. Extractor doc message/history, fill:
   - owner_name = Hung;
   - dealer_name = Solar Hung Phat;
   - address = Gia Lam;
   - main_product/category/supplier_brands neu co evidence.
2. Coverage thay con thieu SDT/Zalo va mo hinh/nguon khach.
3. Conversation brain reply:

```text
Da em ghi duoc anh Hung, cua hang Solar Hung Phat o khu vuc Gia Lam, dang manh ve Xingfa va Austdoor roi a. De lat nua em gui bo thuong hieu dung nguoi, anh cho em xin so Zalo hoac so dien thoai minh hay dung nha?
```

Khong hoi lai ten cua hang/dia chi/san pham.

### 6.2. Khi user hoi loi ich

User:

> anh duoc gi khi noi chuyen voi em nao

Conversation brain nen tra loi:

```text
Da anh se duoc em ho tro gom lai thong tin cua hang de lam bo thuong hieu rieng: logo, danh thiep va video gioi thieu. Phan nay giup cua hang minh nhin chuyen nghiep hon khi gui khach tren Zalo/Facebook. Neu anh thay on, em xin phep hoi nhanh vai thong tin de lam dung theo cua hang minh nha?
```

Khong can state-machine defensive template.

### 6.3. Khi user tra loi dia danh kho nghe

User:

> anh o au sun pac

Huong moi khong hard-code trong code. LLM co the:

- neu hieu: "Ocean Park, Gia Lam dung khong anh?"
- neu khong chac: "Y anh la khu Ocean Park hay mot dia diem khac a?"

User:

> o e

LLM doc history va hieu day la xac nhan cau ngay truoc.

Code khong can mapping `"o e" -> yes` cho happy path moi. Neu co guard phu thi chi de fallback, khong phai logic chinh.

---

## 7. Feature flag moi

De tranh pha app ngay, them mode:

```text
CONVERSATION_ENGINE=legacy
CONVERSATION_ENGINE=planner
CONVERSATION_ENGINE=llm_first
```

Y nghia:

- `legacy`: Linh cu.
- `planner`: ban trung gian da lam, co the giu tam de so sanh.
- `llm_first`: engine moi theo kieu Quynh.

Khi code thu, co the bat `.env` local:

```text
CONVERSATION_ENGINE=llm_first
```

`llm_first` moi la huong chinh. `planner` khong con la dich cuoi.

---

## 8. Nhung phan can bo khoi happy path moi

Trong `llm_first`, khong dung:

- `_conv_asking.handle_asking()` cho happy path;
- `state_machine.decide_action()` de quyet dinh cau hoi tiep theo;
- `gen_ack_safe()` cho reply chinh;
- `get_question()`/slot template de append cau hoi chinh;
- hard-code mapping dia danh nhu cach xu ly chinh;
- `is_planner_eligible` qua chat lam quay ve legacy lien tuc.

Van co the giu cac phan nay cho:

- fallback khi LLM loi;
- regression test;
- mode `legacy`;
- mot vai guard bao mat.

---

## 9. Phan nao can giu

Giu:

- `/api/chat` contract.
- `DealerProfileRaw`.
- `SessionState.history`.
- SQLite store.
- Admin queue.
- MD exporter.
- Voice input pipeline.
- Validators field.
- Reply guards.
- Confirmation/card/export sau khi profile du.

Ly do: nhung phan nay khong lam Linh kem thong minh. Van de nam o **bo nao hoi thoai ASKING**.

---

## 10. Ke hoach code theo phase

### Phase 1: Them engine llm_first, chua xoa legacy

Them file:

- `app/core/llm_first_asking.py`
- `app/llm/linh_conversation_prompt.py`
- `app/llm/intake_fact_extractor.py`
- `app/llm/intake_finalize_judge.py`
- `app/core/intake_coverage.py`
- `app/core/intake_profile_merge.py`

Sua:

- `app/config.py`: them mode `llm_first` vao comment/config.
- `app/core/conversation.py`: route ASKING theo `CONVERSATION_ENGINE`.
- `.env.example`: document `CONVERSATION_ENGINE=legacy|planner|llm_first`.

Khong sua:

- DB schema.
- API response.
- Frontend.
- API key.

### Phase 2: Viet prompt Linh full brief

Viet prompt hoi thoai dai, nhat quan, thay cho template slot.

Nguon noi dung:

- greeting/quyen loi hien tai cua Linh;
- checklist field trong `app/slots/definitions.py`;
- tone Linh trong static UI/current bot copy;
- cac yeu cau tu analysis: khong form, khong hoi lai, hoi co ly do.

### Phase 3: Extract profile tu hoi thoai

Extractor doc:

- recent user turns;
- profile hien tai;
- optionally full compact history.

Extractor tra structured facts. Merge dung validators.

Quan trong: extractor khong duoc viet reply.

### Phase 4: Conversation brain viet reply

Conversation brain nhan:

- profile da update sau extractor;
- coverage con thieu;
- lich su gan day;
- last user message;
- Linh prompt.

No tra reply text.

Neu reply rong/LLM loi, fallback:

```text
Da em dang bi loi ket noi mot chut, anh nhan lai giup em sau it phut nhe.
```

Khong fallback ve slot template neu muc tieu la test chat intelligence, vi fallback do lam cam giac cu quay lai.

### Phase 5: Finalize giong Quynh

Them `intake_finalize_judge`:

- chi finalize khi user da xac nhan sau ban tom tat;
- khong finalize chi vi user noi "ok" o dau flow;
- neu required con thieu thi khong finalize.

Khi du thong tin:

1. Conversation brain tom tat.
2. Hoi xac nhan.
3. User xac nhan.
4. `Stage.CONFIRMING` hoac export/brandkit step chay tiep.

### Phase 6: Transcript eval

Them folder:

- `tests/fixtures/transcripts/`
- hoac `_analysis/transcripts/`

Transcript bat buoc:

1. User hoi "anh duoc gi".
2. User noi nhieu field trong mot cau.
3. User noi dia danh kho nghe.
4. User tra loi ngan de xac nhan cau truoc.
5. User sua thong tin.
6. User khong biet hang vat tu.
7. User tu choi so dien thoai.
8. User noi ngoai luong nhung co du lieu trong cau.
9. User hoi "sao can so dien thoai".
10. User da du thong tin va xac nhan chot.

Eval khong nen check exact text. Check behavior:

- co hoi lai field da co khong;
- co ghi nhan nhieu field trong mot cau khong;
- co tiep noi ngu canh khong;
- co hoi toi da 1 cau chinh khong;
- co biet giai thich loi ich/ly do khong;
- co tranh hard-code template khong.

---

## 11. Test plan

### Unit tests

- `test_intake_coverage.py`
  - required missing/fill dung;
  - coverage khong ep slot script.

- `test_intake_profile_merge.py`
  - fill scalar;
  - correction overwrite co kiem soat;
  - list merge unique;
  - invalid phone bi bo qua;
  - khong hard-code canonical address trong merge.

- `test_intake_fact_extractor.py`
  - mocked LLM extract nhieu fields;
  - invalid JSON fallback;
  - low confidence skipped.

- `test_llm_first_asking.py`
  - reply den tu conversation brain, khong den tu template;
  - user multi-field khong bi hoi lai;
  - short confirmation dua tren history;
  - LLM fail co fallback gon.

- `test_conversation_engine_modes.py`
  - `legacy` giu cu;
  - `planner` van chay neu can so sanh;
  - `llm_first` bo qua `_conv_asking` happy path.

### Regression tests

Chay nhom hien co:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_extractors.py tests/unit/test_reply_pipeline.py tests/unit/test_conversation.py -q
```

Sau do chay full:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Neu legacy tests fail do behavior moi, tach test theo engine mode, khong ep `llm_first` match exact legacy.

---

## 12. Acceptance criteria

Ban code thu dau tien duoc coi la dung huong neu:

- `CONVERSATION_ENGINE=llm_first` chay duoc local.
- Trong ASKING happy path, `_conv_asking.handle_asking()` khong duoc goi.
- Bot tra loi bang prompt Linh full context, khong append slot template.
- User dua nhieu thong tin mot luc thi profile fill nhieu field va reply khong hoi lai.
- User hoi "anh duoc gi" thi bot giai thich loi ich va hoi xin phep tiep tuc.
- User tra loi ngan nhu "ok", "uh", "o e" duoc hieu theo cau truoc bang history, khong bang mapping case chinh.
- Dia danh kho nghe khong crash. Neu LLM khong chac, bot hoi xac nhan tu nhien.
- Khong them hard-code dia danh moi vao happy path.
- Required fields van duoc guard truoc confirm.
- API/frontend/DB khong doi.

---

## 13. Viec can rollback/bo sau khi chuyen huong

Cac thay doi tam thoi tu planner-first co the can bo hoac demote:

- hard-code canonical address trong `profile_merge.py`;
- mapping local address moi them trong `_conv_derive.py`;
- planner eligibility/fallback qua chat;
- prompt planner JSON-first neu no van lam bot giong form.

Khong can xoa ngay trong cung mot commit neu so rui ro, nhung `llm_first` khong duoc phu thuoc vao cac patch do.

---

## 14. Ket luan

Huong dung khong phai:

```text
Lam Linh cu thong minh hon bang cach them regex, mapping, fallback va slot patch.
```

Huong dung la:

```text
Dung cau truc hoi thoai cua Quynh:
  LLM noi chuyen chinh + full history + prompt nhat quan

Nhung dung noi dung cua Linh:
  brandkit, logo, danh thiep, video, checklist dealer cua Linh

Va giu ha tang cua Linh:
  API, DB, admin, voice, md export, validators, guards
```

Noi ngan gon: **thay nao ASKING bang Quynh-style LLM-first, giu than app cua Linh**.

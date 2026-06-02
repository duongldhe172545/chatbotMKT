# Linh MKT planner-first implementation plan

Ngày viết: 2026-06-01

> Ghi chú 2026-06-01: plan này là bản trung gian `planner-first`. Theo yêu cầu mới, hướng đích đã chuyển sang cấu trúc **Quỳnh-style LLM-first**: xem `_analysis/linh-mkt-quynh-style-rebuild-plan.md`. Không dùng file này làm kế hoạch code chính nữa nếu mục tiêu là bám kiến trúc Quỳnh.

Mục tiêu của lượt code thử là thay happy path hội thoại ASKING theo hướng planner-first, nhưng vẫn giữ rollback an toàn. Mặc định hệ thống chạy `CONVERSATION_ENGINE=legacy`, tức không đổi hành vi production nếu chưa bật flag.

## Phạm vi implement

- Thêm feature flag `CONVERSATION_ENGINE=legacy|planner_shadow|planner`.
- Thêm planner model, prompt, missing-field checklist và merge an toàn.
- Hook planner vào `Stage.ASKING` trong `app/core/conversation.py`.
- Giữ `_conv_asking.py` làm legacy fallback.
- Không đổi `/api/chat`, DB schema, frontend, `.env` thật hoặc API key.

## Luồng runtime

```text
Stage.ASKING
  legacy:
    handle_asking()

  planner_shadow:
    plan_intake_turn() trong try/log only
    handle_asking() trả reply thật

  planner:
    nếu turn eligible happy path:
      handle_asking_with_planner()
    nếu không:
      handle_asking()
```

Planner chỉ chạy trực tiếp khi intent layer 1 là `NORMAL` hoặc `AFFIRMATIVE`, không phải technical inquiry, không phải address blacklist, và không ở slot consent `4.0/4.1`. Các case defensive, tâm sự, refusal, confusion, consent vẫn đi legacy.

## Module thêm mới

- `app/models/planner.py`: `PlannedFact`, `PlannerResult`, `MissingFieldState`.
- `app/core/missing_fields.py`: tính required/optional missing từ profile hiện tại.
- `app/core/profile_merge.py`: validate và merge planner facts vào `DealerProfileRaw`.
- `app/llm/planner_prompt.py`: prompt + JSON schema cho planner.
- `app/core/intake_planner.py`: gọi LLM planner và xử lý turn planner.

## Test cần có

- `tests/unit/test_missing_fields.py`.
- `tests/unit/test_profile_merge.py`.
- `tests/unit/test_intake_planner.py`.
- `tests/unit/test_conversation_planner_engine.py`.

Regression bắt buộc:

- Legacy mode giữ behavior cũ.
- Shadow mode không đổi reply thật.
- Planner mode extract nhiều field trong một câu.
- Planner invalid/fail fallback legacy.
- Defensive/tâm sự/refusal/confusion/technical/slot `4.0` fallback legacy.

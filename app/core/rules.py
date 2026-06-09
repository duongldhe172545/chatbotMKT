"""Unified rules loader — load config/rules.yaml một lần, dùng toàn hệ thống.

Cung cấp:
- get_rules() → dict gốc từ YAML
- get_mission() → str
- get_persona() → dict
- get_data_principles() → list[str]
- get_tone(dealer_type) → str
- get_safety_rules() → list[str]
- build_rules_context_for_prompt() → str (dùng cho LLM prompt)
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
RULES_PATH = CONFIG_DIR / "rules.yaml"


@lru_cache(maxsize=1)
def get_rules() -> dict[str, Any]:
    """Load rules.yaml một lần (cached)."""
    if not RULES_PATH.exists():
        logger.error("rules.yaml not found at %s", RULES_PATH)
        return {}
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_mission() -> str:
    return get_rules().get("mission", "").strip()


def get_persona() -> dict[str, Any]:
    return get_rules().get("persona", {})


def get_data_principles() -> list[str]:
    dc = get_rules().get("data_collection", {})
    return dc.get("principles", [])


def get_slot_rules(slot_id: str) -> list[str]:
    """Lấy rules riêng cho 1 slot (nếu có)."""
    dc = get_rules().get("data_collection", {})
    for slot in dc.get("slots", []):
        if slot.get("id") == slot_id:
            return slot.get("rules", [])
    return []


def get_tone(dealer_type: str = "unknown") -> str:
    """Lấy tone instruction chuẩn của Em Linh MKT."""
    tone = get_rules().get("tone", {})
    return tone.get("general", "").strip()


def get_safety_rules() -> list[str]:
    return get_rules().get("safety", [])


def build_rules_context_for_prompt(
    *,
    dealer_type: str = "unknown",
    address_form: str = "anh",
) -> str:
    """Build a compact rules summary for injection into LLM prompts.

    Gộp mission + persona + data principles + tone + safety thành 1 string
    gọn gàng để inject vào system prompt.
    """
    persona = get_persona()
    principles = get_data_principles()
    tone_text = get_tone()
    safety = get_safety_rules()

    # Slot summary
    dc = get_rules().get("data_collection", {})
    slots = dc.get("slots", [])
    slot_lines = []
    for s in slots:
        kind = s.get("kind", "")
        label = s.get("label", "")
        fields = ", ".join(s.get("fields", []))
        rules = s.get("rules", [])
        line = f"  {s['id']} ({kind}): {label} → [{fields}]"
        if rules:
            for r in rules:
                line += f"\n    - {r}"
        slot_lines.append(line)

    return f"""NHIỆM VỤ:
{get_mission()}

NHÂN VẬT:
- Tên: {persona.get('name', 'Em Linh')}
- Vai trò: {persona.get('role', '')}
- Xưng: {persona.get('self_reference', 'em')}, gọi khách: {address_form}
- Nếu khách hỏi danh tính: {persona.get('identity_if_asked', '')}

NGUYÊN TẮC THU THẬP:
{chr(10).join('- ' + p for p in principles)}

17 SLOT (thu theo thứ tự):
{chr(10).join(slot_lines)}

GIỌNG ĐIỆU:
{tone_text}

AN TOÀN:
{chr(10).join('- ' + s for s in safety)}"""


def clear_cache() -> None:
    """Clear cache — dùng cho test."""
    get_rules.cache_clear()

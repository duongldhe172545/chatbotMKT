"""Guideline registry — load + query condition→action rules from YAML.

Parlant concept: Guidelines are "when X, do Y" rules that the agent
must follow. They are loaded from config/guidelines.yaml and matched
against the current conversation state each turn.

Each guideline has:
- id: unique identifier (e.g. "tone_busy_user")
- condition: when this guideline applies
- action: what the agent should do
- priority: higher = checked first (default 50)
- category: grouping for trace/debug
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class Guideline:
    """A single condition→action rule."""

    id: str
    condition: str
    action: str
    priority: int = 50
    category: str = "general"
    enabled: bool = True

    def matches_context(self, context: dict[str, Any]) -> bool:
        """Evaluate if this guideline's condition matches the current context.

        Phase 3 stub: uses simple keyword matching on condition string.
        Phase 4+ will use a proper expression evaluator.
        """
        if not self.enabled:
            return False

        cond = self.condition.lower()

        # Simple keyword-based condition matching
        if cond.startswith("when:"):
            cond = cond[5:].strip()

        # Check against context variables
        for key, value in context.items():
            if isinstance(value, str) and key.lower() in cond:
                if value.lower() in cond:
                    return True
            if isinstance(value, bool) and value and key.lower() in cond:
                return True
            if isinstance(value, list) and key.lower() in cond:
                for item in value:
                    if isinstance(item, str) and item.lower() in cond:
                        return True

        return False


class GuidelineRegistry:
    """Load and query guidelines from YAML config."""

    def __init__(self, config_path: Path | None = None):
        self._guidelines: dict[str, Guideline] = {}
        self._config_path = config_path or CONFIG_DIR / "guidelines.yaml"
        self._loaded = False

    def load(self) -> None:
        """Load guidelines from YAML file."""
        if not self._config_path.exists():
            logger.warning("Guidelines config not found: %s", self._config_path)
            self._loaded = True
            return

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        guidelines_list = raw.get("guidelines", [])
        for entry in guidelines_list:
            g = Guideline(
                id=entry["id"],
                condition=entry.get("condition", ""),
                action=entry.get("action", ""),
                priority=int(entry.get("priority", 50)),
                category=entry.get("category", "general"),
                enabled=entry.get("enabled", True),
            )
            self._guidelines[g.id] = g

        self._loaded = True
        logger.info("Loaded %d guidelines from %s", len(self._guidelines), self._config_path)

    def get(self, guideline_id: str) -> Guideline | None:
        self._ensure_loaded()
        return self._guidelines.get(guideline_id)

    def all(self) -> list[Guideline]:
        self._ensure_loaded()
        return sorted(self._guidelines.values(), key=lambda g: (-g.priority, g.id))

    def by_category(self, category: str) -> list[Guideline]:
        self._ensure_loaded()
        return [g for g in self.all() if g.category == category]

    def match(self, context: dict[str, Any]) -> list[Guideline]:
        """Return all guidelines whose condition matches the context.

        Sorted by priority (descending).
        """
        self._ensure_loaded()
        matched = [g for g in self.all() if g.matches_context(context)]
        return sorted(matched, key=lambda g: -g.priority)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

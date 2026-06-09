"""Canned responses — pre-built replies for common situations.

Parlant concept: Some situations have deterministic, pre-built replies
that don't need LLM generation. The canned response system checks
if the current objective/observations match a template and returns
it directly (bypassing the agent).

When no canned response matches, the agent generates a reply.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class CannedResponse:
    """A pre-built response template."""

    id: str
    trigger_objective: str  # e.g. "collect_required_field"
    trigger_field: str | None = None  # e.g. "phone_or_zalo"
    trigger_intent: str | None = None  # e.g. "defensive"
    trigger_flag: str | None = None  # e.g. "phone_invalid_after_retry"
    template: str = ""
    address_form_placeholder: str = "{af}"
    priority: int = 50


class CannedResponseRegistry:
    """Load and match canned responses from YAML config."""

    def __init__(self, config_path: Path | None = None):
        self._responses: list[CannedResponse] = []
        self._config_path = config_path or CONFIG_DIR / "canned_responses.yaml"
        self._loaded = False

    def load(self) -> None:
        """Load canned responses from YAML."""
        if not self._config_path.exists():
            logger.warning("Canned responses config not found: %s", self._config_path)
            self._loaded = True
            return

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        for entry in raw.get("canned_responses", []):
            self._responses.append(
                CannedResponse(
                    id=entry["id"],
                    trigger_objective=entry.get("trigger_objective", ""),
                    trigger_field=entry.get("trigger_field"),
                    trigger_intent=entry.get("trigger_intent"),
                    trigger_flag=entry.get("trigger_flag"),
                    template=entry.get("template", ""),
                    priority=int(entry.get("priority", 50)),
                )
            )

        self._loaded = True
        logger.info("Loaded %d canned responses", len(self._responses))

    def match(
        self,
        *,
        objective_type: str,
        target_field: str | None = None,
        intent: str | None = None,
        target_flag: str | None = None,
    ) -> CannedResponse | None:
        """Find the best matching canned response.

        Returns None if no match (agent should generate reply).
        """
        self._ensure_loaded()

        candidates = []
        for resp in self._responses:
            if resp.trigger_objective != objective_type:
                continue
            if resp.trigger_field and resp.trigger_field != target_field:
                continue
            if resp.trigger_intent and resp.trigger_intent != intent:
                continue
            if resp.trigger_flag and resp.trigger_flag != target_flag:
                continue
            candidates.append(resp)

        if not candidates:
            return None

        # Return highest priority match
        return max(candidates, key=lambda r: r.priority)

    def render(self, response: CannedResponse, address_form: str = "anh") -> str:
        """Render a canned response template with address form substitution."""
        text = response.template.replace("{af}", address_form)
        return text.replace("{Af}", address_form.capitalize())

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

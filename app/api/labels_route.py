"""Endpoint trả label cho frontend — single source of truth."""
from __future__ import annotations

from fastapi import APIRouter

from app.labels import all_labels

router = APIRouter(prefix="/api", tags=["labels"])


@router.get("/labels")
def get_labels() -> dict:
    return all_labels()

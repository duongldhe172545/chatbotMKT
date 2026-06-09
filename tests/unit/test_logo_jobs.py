from __future__ import annotations

import json
import time

from app.core import logo_jobs
from app.core.logo_generator import LogoVariant
from app.models.schema import DealerProfileRaw


def test_logo_job_is_idempotent_and_reads_cached_variants(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_generate(session_id, profile, progress_callback=None):
        calls.append(session_id)
        variants = []
        for index in range(1, 4):
            if progress_callback:
                progress_callback(index)
            variants.append(
                LogoVariant(
                    id=f"{session_id}-{index}",
                    name=f"Mẫu {index}",
                    style="test",
                    url=f"/logos/{index}.svg",
                    download_url=f"/logos/{index}.svg",
                )
            )
        return variants

    monkeypatch.setattr(logo_jobs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(logo_jobs, "generate_logo_variants", fake_generate)
    profile = DealerProfileRaw(dealer_name="Dương An", brandkit_consent="yes")

    logo_jobs.start_logo_job("session-logo-job", profile)
    for _ in range(100):
        status = logo_jobs.get_logo_job("session-logo-job")
        if status["status"] == "completed":
            break
        time.sleep(0.01)

    assert status["status"] == "completed"
    assert status["progress"] == 3
    assert status["total"] == 3
    assert len(logo_jobs.get_logo_variants("session-logo-job")) == 3

    logo_jobs.start_logo_job("session-logo-job", profile)
    assert calls == ["session-logo-job"]


def test_logo_job_keeps_existing_five_variant_manifest_readable(monkeypatch, tmp_path):
    monkeypatch.setattr(logo_jobs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    session_id = "legacy-five-logo-job"
    folder = tmp_path / session_id
    folder.mkdir(parents=True)
    variants = [
        LogoVariant(
            id=f"{session_id}-{index}",
            name=f"Mẫu {index}",
            style="legacy",
            url=f"/logos/{index}.svg",
            download_url=f"/logos/{index}.svg",
        ).model_dump()
        for index in range(1, 6)
    ]
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "progress": 5,
                "total": 5,
                "error": None,
                "logo_variants": variants,
            }
        ),
        encoding="utf-8",
    )

    status = logo_jobs.get_logo_job(session_id)

    assert status["total"] == 5
    assert status["progress"] == 5
    assert len(logo_jobs.get_logo_variants(session_id)) == 5

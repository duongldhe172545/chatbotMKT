from __future__ import annotations

from app.core.logo_generator import generate_logo_variants
from app.models.schema import DealerProfileRaw


def test_generate_five_distinct_svg_logo_variants(tmp_path):
    profile = DealerProfileRaw(
        dealer_name="Xưởng Nhôm Dương An",
        main_product="nhôm Xingfa",
        brandkit_consent="yes",
        color_accent="xanh dương",
        logo_initials="XDA",
        slogan_preference="Vững nhôm, bền nhà",
        logo_style="tối giản hiện đại",
    )

    variants = generate_logo_variants(
        "session-logo-test",
        profile,
        output_root=tmp_path,
        url_prefix="/test-logos",
    )

    assert len(variants) == 5
    assert len({variant.url for variant in variants}) == 5
    files = sorted((tmp_path / "session-logo-test").glob("*.svg"))
    assert len(files) == 5
    assert "XDA" in files[0].read_text(encoding="utf-8")
    assert "Vững nhôm, bền nhà" in files[0].read_text(encoding="utf-8")


def test_generate_logo_variants_requires_consent(tmp_path):
    assert generate_logo_variants(
        "no-consent",
        DealerProfileRaw(dealer_name="Test", brandkit_consent="no"),
        output_root=tmp_path,
    ) == []

"""Test sanity check 5-point. Refer F2A.7."""
from __future__ import annotations

from app.core.sanity import check_sanity
from app.core.session import create_session
from app.models.enums import Flag
from app.models.schema import DealerProfileRaw


# ============================================================
# Check 1 — 6 REQUIRED fields
# ============================================================


class TestRequiredFields:
    def test_all_required_filled_passes(self):
        s = create_session()
        p = _full_profile()
        ok, failed = check_sanity(s, p)
        assert ok is True, f"Failed: {failed}"
        assert failed == []

    def test_missing_required_without_flag_fails(self):
        """Thiếu REQUIRED không có flag required_missing → FAIL."""
        s = create_session()
        p = _full_profile()
        p.owner_name = None  # missing
        ok, failed = check_sanity(s, p)
        assert ok is False
        assert any("Check 1" in f for f in failed)

    def test_missing_required_with_flag_passes(self):
        """Thiếu REQUIRED + có flag required_missing → PASS (admin sẽ review)."""
        s = create_session()
        s.flags.append(Flag.REQUIRED_MISSING)
        p = _full_profile()
        p.owner_name = None
        ok, _ = check_sanity(s, p)
        # Pass dù thiếu owner_name vì có flag
        assert ok is True


# ============================================================
# Check 2 — Phone format
# ============================================================


class TestPhoneFormat:
    def test_valid_phone_passes(self):
        s = create_session()
        p = _full_profile()
        p.phone_or_zalo = "0912345678"
        ok, _ = check_sanity(s, p)
        assert ok is True

    def test_invalid_phone_fails(self):
        s = create_session()
        p = _full_profile()
        p.phone_or_zalo = "abc"
        ok, failed = check_sanity(s, p)
        assert ok is False
        assert any("Check 2" in f for f in failed)

    def test_null_phone_passes(self):
        """Phone null OK (chỉ check format khi có data)."""
        s = create_session()
        s.flags.append(Flag.REQUIRED_MISSING)  # bypass check 1
        p = _full_profile()
        p.phone_or_zalo = None
        ok, failed = check_sanity(s, p)
        # Check 2 (phone format) PASS — chỉ check khi non-null
        assert not any("Check 2" in f for f in failed)


# ============================================================
# Check 3 — Address blacklist
# ============================================================


class TestAddressCheck:
    def test_normal_address_passes(self):
        s = create_session()
        p = _full_profile()
        p.address = "123 Lê Lợi Q.1 TP.HCM"
        ok, _ = check_sanity(s, p)
        assert ok is True

    def test_blacklist_address_fails(self):
        s = create_session()
        p = _full_profile()
        p.address = "Gần Lăng Bác Hà Nội"
        ok, failed = check_sanity(s, p)
        assert ok is False
        assert any("Check 3" in f for f in failed)


# ============================================================
# Check 4 — brandkit_consent
# ============================================================


class TestConsentCheck:
    def test_yes_passes(self):
        s = create_session()
        p = _full_profile()
        p.brandkit_consent = "yes"
        ok, _ = check_sanity(s, p)
        assert ok is True

    def test_no_passes(self):
        s = create_session()
        p = _full_profile()
        p.brandkit_consent = "no"
        ok, _ = check_sanity(s, p)
        assert ok is True

    def test_null_without_flag_fails(self):
        s = create_session()
        p = _full_profile()
        p.brandkit_consent = None
        ok, failed = check_sanity(s, p)
        # Check 4 fail vì consent null + không có flag
        assert any("Check 4" in f for f in failed)

    def test_null_with_consent_unclear_flag_passes(self):
        s = create_session()
        s.flags.append(Flag.CONSENT_UNCLEAR)
        # Cũng cần required_missing để bypass check 1 cho brandkit_consent
        s.flags.append(Flag.REQUIRED_MISSING)
        p = _full_profile()
        p.brandkit_consent = None
        ok, failed = check_sanity(s, p)
        # Check 4 PASS với consent_unclear flag
        assert not any("Check 4" in f for f in failed)


# ============================================================
# Check 5 — No Scope 4 leak
# ============================================================


class TestScope4Leak:
    def test_clean_profile_passes(self):
        """Profile từ Pydantic schema KHÔNG có Scope 4 field → PASS."""
        s = create_session()
        p = _full_profile()
        ok, failed = check_sanity(s, p)
        # Check 5 PASS (schema strict)
        assert not any("Check 5" in f for f in failed)


# ============================================================
# Helper
# ============================================================


def _full_profile() -> DealerProfileRaw:
    """Profile có đủ 6 REQUIRED slot → passes Check 1.

    6 REQUIRED slot:
    - 1.1: owner_name + dealer_name
    - 1.2: address
    - 1.3: phone_or_zalo
    - 2.1: main_product
    - 2.2: business_model_signal
    - 4.0: brandkit_consent
    """
    return DealerProfileRaw(
        owner_name="Tùng",
        dealer_name="Nhôm Kính Thanh Tùng",
        address="123 Lê Lợi Q.1 TP.HCM",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm kính",
        business_model_signal="phân phối",
        brandkit_consent="yes",
    )

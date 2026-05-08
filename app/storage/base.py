"""Storage adapter interface — sau swap sang M365 / Power Automate / Graph API."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schema import DealerProfileRaw, Session


class StorageAdapter(ABC):
    @abstractmethod
    def save_session(self, session: Session) -> None:
        """Lưu/cập nhật session — tương đương 02_INTAKE_LOG."""
        ...

    @abstractmethod
    def load_session(self, session_id: str) -> Session | None:
        ...

    @abstractmethod
    def save_profile_raw(self, session_id: str, profile: DealerProfileRaw) -> None:
        """Lưu profile đã CONFIRMED — tương đương 01_DEALER_PROFILE_RAW.

        Lưu ý: bản này vẫn ở trạng thái review_status='RAW',
        cần human review trước khi tạo Dealer_ID chính thức (mục 12, mục 26).
        """
        ...

    @abstractmethod
    def list_profiles(self) -> list[dict]:
        """Liệt kê tất cả profile đã CONFIRMED, mới nhất trước."""
        ...

    @abstractmethod
    def list_sessions(self, limit: int = 50) -> list[dict]:
        """Liệt kê session gần nhất (kể cả chưa hoàn thành)."""
        ...

    def find_profile_by_phone(self, phone: str) -> DealerProfileRaw | None:
        """Tìm profile CONFIRMED có cùng phone_or_zalo. Default: None.

        Subclass có thể override để hỗ trợ cross-session memory.
        """
        return None

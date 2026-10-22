import requests

from .config import Settings
from .documents import DmsDocument, DownloadedFile

SUCCESS_CODE = "00"


class DmsError(RuntimeError):
    pass


class DmsClient:
    """Klien API DMS-Cardsys v2 (search & download)."""

    def __init__(self, base_url: str, timeout_seconds: float, session: requests.Session | None = None):
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls, settings: Settings) -> "DmsClient":
        return cls(settings.dms_base_url, settings.dms_timeout_seconds)

    def is_reachable(self, timeout_seconds: float) -> bool:
        """DMS tidak punya endpoint health; respons HTTP apa pun berarti host bisa dijangkau."""
        try:
            self._session.get(f"{self._base_url}/api/v2/search", timeout=timeout_seconds)
        except requests.RequestException:
            return False
        return True

    def search_by_ticket(self, ticket_id: str) -> list[DmsDocument]:
        response = self._session.post(
            f"{self._base_url}/api/v2/search",
            json={"metadata": {"NomorDokumen": ticket_id}, "mode": "any"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()

        if body.get("code") != SUCCESS_CODE:
            raise DmsError(f"Search tiket {ticket_id} gagal: {body.get('code')} {body.get('message')}")

        return [_to_document(ticket_id, item) for item in body.get("data", {}).get("documents", [])]

    def download(self, node_id: str) -> DownloadedFile:
        response = self._session.get(
            f"{self._base_url}/api/v2/download",
            params={"id": node_id},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return DownloadedFile(
            content=response.content,
            content_type=response.headers.get("content-type", "").split(";")[0].strip(),
        )


def _to_document(ticket_id: str, item: dict) -> DmsDocument:
    return DmsDocument(
        ticket_id=ticket_id,
        node_id=item["nodeId"],
        filename=item.get("metadata", {}).get("filename", ""),
        created_at=item.get("createDate", ""),
    )

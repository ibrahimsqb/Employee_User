"""Lightweight client for the external face recognition API.

This module keeps outbound HTTP details in one place so we can
reuse across onboarding (enrollment) and attendance (identification).
"""
import logging
from typing import Iterable, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = getattr(settings, "FACE_API_BASE_URL", "http://13.50.238.213:8000").rstrip("/")
CONNECT_TIMEOUT = float(getattr(settings, "FACE_API_CONNECT_TIMEOUT", 5))
READ_TIMEOUT = float(getattr(settings, "FACE_API_READ_TIMEOUT", 60))
ENABLED = bool(getattr(settings, "FACE_API_ENABLED", True))


class FaceAPIError(Exception):
    """Raised when the face API returns an error or cannot be reached."""


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _post(path: str, *, data=None, files=None) -> dict:
    url = f"{BASE_URL}{path}"
    if not ENABLED:
        raise FaceAPIError("Face API is disabled by settings")
    try:
        response = _session().post(url, data=data, files=files, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    except requests.RequestException as exc:  # pragma: no cover - network
        logger.exception("Face API request failed: %s", exc)
        raise FaceAPIError(f"Could not reach face API: {exc}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise FaceAPIError(f"{path} returned {response.status_code}: {detail}")

    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def add_person(person_name: str, images: Iterable) -> dict:
    """Enroll a person with one or more face images.

    ``images`` can be any iterable of Django ``UploadedFile`` instances.
    """
    files_payload = []
    for image in images:
        if hasattr(image, "seek"):
            image.seek(0)
        files_payload.append(
            (
                "files",
                (getattr(image, "name", "face.jpg"), getattr(image, "file", image), getattr(image, "content_type", "image/jpeg")),
            )
        )

    if not files_payload:
        raise FaceAPIError("No face images provided for enrollment")

    return _post("/add_person", data={"person_name": person_name}, files=files_payload)


def rebuild_db() -> dict:
    return _post("/rebuild_db")


def migrate() -> dict:
    return _post("/migrate")


def identify(image_bytes: bytes) -> dict:
    file_tuple = ("capture.jpg", image_bytes, "image/jpeg")
    return _post("/identify", files={"file": file_tuple})


def extract_match_name(payload: dict) -> Optional[str]:
    """Return the best guess of the matched person name from API payload."""
    if not isinstance(payload, dict):
        return None

    for key in ("person_name", "person", "name", "label"):
        value = payload.get(key)
        if value:
            return str(value)

    # Some APIs return a list under "matches" or similar
    matches = payload.get("matches") or payload.get("results")
    if isinstance(matches, list) and matches:
        first = matches[0]
        if isinstance(first, dict):
            for key in ("person_name", "person", "name", "label"):
                value = first.get(key)
                if value:
                    return str(value)
        elif isinstance(first, str):
            return first

    return None

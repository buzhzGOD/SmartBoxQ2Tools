from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any


class DataError(ValueError):
    pass


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DataError(f"Невозможно прочитать {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise DataError(f"Некорректный JSON в {path}: {error}") from error
    if not isinstance(value, dict):
        raise DataError(f"{path} должен содержать JSON-объект")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def device_key(serial: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{serial}\0{fingerprint}".encode("utf-8")).hexdigest()[:16]


def verification_token(serial: str, profile_hash: str, count: int) -> str:
    value = f"{serial}\0{profile_hash}\0{count}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:12].upper()

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import Any


SECRET_NAME = re.compile(r"(?:api[_-]?key|access[_-]?token|secret|password|credential)", re.IGNORECASE)


class SecretRedactor:
    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(sorted({value for value in secrets if len(value) >= 6}, key=len, reverse=True))

    @property
    def secrets(self) -> tuple[str, ...]:
        return self._secrets

    def redact_text(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        return value

    def redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {str(key): self.redact(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(self.redact(item) for item in value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if is_dataclass(value):
            return {field.name: self.redact(getattr(value, field.name)) for field in fields(value)}
        if hasattr(value, "model_dump"):
            return self.redact(value.model_dump(mode="json"))
        return value

    def contains_secret(self, value: str) -> bool:
        return any(secret in value for secret in self._secrets)


def discover_secrets(config: Any | None = None, environ: Mapping[str, str] | None = None) -> list[str]:
    env = environ if environ is not None else os.environ
    discovered = {value for key, value in env.items() if SECRET_NAME.search(key) and len(value) >= 6}
    if config is None:
        return sorted(discovered)

    for provider in getattr(config, "providers", []):
        try:
            discovered.add(provider.resolve_api_key())
        except Exception:
            pass
    voice = getattr(config, "voice", None)
    for profile in getattr(voice, "profiles", []) if voice else []:
        for method_name in ("resolve_api_key", "resolve_app_id", "resolve_secret_key"):
            try:
                discovered.add(getattr(profile, method_name)())
            except Exception:
                pass
    return sorted(value for value in discovered if value and len(value) >= 6)

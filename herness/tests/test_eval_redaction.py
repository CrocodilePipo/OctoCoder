from __future__ import annotations

from octocoder.evals.redaction import SecretRedactor, discover_secrets


def test_recursive_secret_redaction() -> None:
    secret = "super-secret-token"
    redactor = SecretRedactor([secret, "tiny"])
    value = {"event": [f"Authorization: Bearer {secret}", {"token": secret}]}
    redacted = redactor.redact(value)
    assert secret not in str(redacted)
    assert str(redacted).count("[REDACTED]") == 2
    assert redactor.secrets == (secret,)


def test_secret_discovery_uses_credential_named_environment() -> None:
    secrets = discover_secrets(environ={"MODEL_API_KEY": "model-secret", "PATH": "ignored-value"})
    assert secrets == ["model-secret"]

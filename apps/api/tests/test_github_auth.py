"""Tests for GitHub App authentication, JWT signing, and key resolution."""


import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.exceptions import GitHubAuthError
from app.github.auth import (
    GitHubAppAuth,
    assert_ready_for_github_operations,
    find_repo_root,
    is_valid_rsa_pem_key,
    resolve_private_key_path,
    validate_github_app_settings,
)


@pytest.fixture
def test_rsa_key_pair():
    """Generate ephemeral 2048-bit RSA key pair for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def test_jwt_iss_claim_is_string_for_numeric_app_ids(test_rsa_key_pair):
    """PyJWT and RFC 7519 require 'iss' claim to always be string, even with numeric app IDs."""
    private_pem, public_pem = test_rsa_key_pair

    # Test both numeric string and integer app_id
    for test_id in ["987654", 987654]:
        auth = GitHubAppAuth(app_id=test_id, private_key=private_pem)
        token = auth.generate_app_jwt()

        assert isinstance(token, str)
        decoded = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        assert decoded["iss"] == "987654"
        assert isinstance(decoded["iss"], str)
        assert "exp" in decoded
        assert "iat" in decoded
        # Expiry constraint: exactly 10 minutes (600s) from iat
        assert decoded["exp"] - decoded["iat"] == 600


def test_jwt_generation_with_local_pem_file():
    """Verify JWT generation using the repository's local PEM file without logging contents."""
    repo_root = find_repo_root()
    pem_path = repo_root / "codeguard-ai-123.2026-10-03.private-key.pem"

    if not pem_path.is_file():
        pytest.skip("Local PEM file not found in repository root")

    auth = GitHubAppAuth(app_id="123456", private_key_path=str(pem_path))
    token = auth.generate_app_jwt()

    assert isinstance(token, str)
    assert len(token) > 100
    # Header check
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"


def test_private_key_path_resolution(tmp_path):
    """Test resolution of relative and absolute key paths."""
    key_file = tmp_path / "custom-key.pem"
    key_file.write_text("dummy-content", encoding="utf-8")

    # Absolute path
    resolved = resolve_private_key_path(str(key_file))
    assert resolved == key_file.resolve()

    # Non-existent path returns None
    missing = resolve_private_key_path("does-not-exist-key-12345.pem")
    assert missing is None


def test_missing_private_key_path_raises_safe_error():
    """Configuring a non-existent GITHUB_PRIVATE_KEY_PATH must raise clear, safe error."""
    with pytest.raises(GitHubAuthError) as exc_info:
        GitHubAppAuth(app_id="123456", private_key_path="non_existent_key_file.pem")

    assert "does not exist or cannot be resolved" in str(exc_info.value)
    assert "non_existent_key_file.pem" in str(exc_info.value)


def test_invalid_rsa_private_key_raises_safe_error(tmp_path):
    """Configuring a file that is not a valid RSA key must raise clear, safe error."""
    invalid_file = tmp_path / "not-a-key.pem"
    invalid_file.write_text("-----BEGIN FOO-----\nnot an RSA key\n-----END FOO-----", encoding="utf-8")

    with pytest.raises(GitHubAuthError) as exc_info:
        GitHubAppAuth(app_id="123456", private_key_path=str(invalid_file))

    assert "is not a valid PEM RSA private key" in str(exc_info.value)


def test_invalid_inline_private_key_raises_safe_error():
    """Configuring an invalid inline GITHUB_PRIVATE_KEY must raise safe error."""
    with pytest.raises(GitHubAuthError) as exc_info:
        GitHubAppAuth(app_id="123456", private_key="not-a-valid-pem-key")

    assert "is not a valid PEM RSA private key" in str(exc_info.value)


def test_placeholder_app_id_rejected_when_signing(test_rsa_key_pair):
    """'dev-app-id' must be rejected when attempting to sign a real JWT."""
    private_pem, _ = test_rsa_key_pair

    auth = GitHubAppAuth(app_id="dev-app-id", private_key=private_pem)
    with pytest.raises(GitHubAuthError) as exc_info:
        auth.generate_app_jwt()

    assert "GITHUB_APP_ID cannot be 'dev-app-id'" in str(exc_info.value)


def test_non_numeric_app_id_rejected_when_signing(test_rsa_key_pair):
    """Non-numeric app ID string must be rejected when signing."""
    private_pem, _ = test_rsa_key_pair

    auth = GitHubAppAuth(app_id="invalid-alpha-id", private_key=private_pem)
    with pytest.raises(GitHubAuthError) as exc_info:
        auth.generate_app_jwt()

    assert "Invalid GITHUB_APP_ID format" in str(exc_info.value)


def test_is_valid_rsa_pem_key_helper(test_rsa_key_pair):
    """Validate RSA key detector helper."""
    private_pem, _ = test_rsa_key_pair
    assert is_valid_rsa_pem_key(private_pem) is True
    assert is_valid_rsa_pem_key("invalid-pem") is False
    assert is_valid_rsa_pem_key("") is False


def test_validate_github_app_settings_reporting():
    """validate_github_app_settings reports statuses without exposing secret values."""
    statuses = validate_github_app_settings(installation_id=12345)

    assert "GITHUB_APP_ID" in statuses
    assert "GITHUB_APP_SLUG" in statuses
    assert "GITHUB_PRIVATE_KEY" in statuses
    assert "GITHUB_WEBHOOK_SECRET" in statuses
    assert "target_installation_id" in statuses

    # All values must be safe status strings
    valid_statuses = {"CONFIGURED", "MISSING", "PLACEHOLDER", "INVALID"}
    for k, v in statuses.items():
        assert v in valid_statuses, f"Setting {k} has unexpected status: {v}"


def test_assert_ready_for_github_operations_blocks_on_placeholders(monkeypatch):
    """assert_ready_for_github_operations raises GitHubAuthError if placeholders exist."""
    monkeypatch.setattr("app.core.config.settings.GITHUB_APP_ID", "dev-app-id")
    with pytest.raises(GitHubAuthError) as exc_info:
        assert_ready_for_github_operations()

    assert "GitHub App settings are not ready" in str(exc_info.value)
    assert "GITHUB_APP_ID: PLACEHOLDER" in str(exc_info.value)

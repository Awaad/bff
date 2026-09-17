from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bff_control.infrastructure.auth.workos as workos_module
import jwt
import pytest
from bff_control.core.settings import AuthenticationSettings
from bff_control.domains.authentication.contracts import AccessTokenVerificationError
from bff_control.infrastructure.auth.workos import WorkOSAccessTokenVerifier
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

KID = "test-key"
ISSUER = "https://example.authkit.app"
CLIENT_ID = "client_test"


class StaticSigningKeyClient:
    def __init__(self, key: PyJWK) -> None:
        self._key = key
        self.requested_kids: list[str] = []

    def get_signing_key(self, kid: str) -> PyJWK:
        self.requested_kids.append(kid)
        return self._key


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def signing_key(private_key: rsa.RSAPrivateKey) -> PyJWK:
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    return PyJWK.from_dict(jwk)


def _settings(**overrides: object) -> AuthenticationSettings:
    values: dict[str, object] = {
        "issuer": ISSUER,
        "client_id": CLIENT_ID,
        "jwks_url": "https://example.authkit.app/oauth2/jwks",
        "jwt_leeway_seconds": 0,
    }
    values.update(overrides)
    return AuthenticationSettings.model_validate(values)


def _payload(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    values: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "user_test",
        "sid": "session_test",
        "jti": "token_test",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "client_id": CLIENT_ID,
    }
    values.update(overrides)
    return values


def _encode(
    private_key: rsa.RSAPrivateKey,
    payload: dict[str, Any],
    *,
    algorithm: str = "RS256",
    headers: dict[str, str] | None = None,
) -> str:
    token_headers = {"kid": KID}
    if headers is not None:
        token_headers.update(headers)
    return jwt.encode(payload, private_key, algorithm=algorithm, headers=token_headers)


def test_jwks_client_configures_bounded_cache_and_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePyJWKClient:
        def __init__(self, uri: str, **kwargs: object) -> None:
            captured["uri"] = uri
            captured.update(kwargs)

    monkeypatch.setattr(workos_module, "PyJWKClient", FakePyJWKClient)

    client = workos_module.build_workos_jwks_client(_settings())

    assert isinstance(client, FakePyJWKClient)
    assert captured == {
        "uri": "https://example.authkit.app/oauth2/jwks",
        "cache_keys": False,
        "cache_jwk_set": True,
        "lifespan": 300.0,
        "timeout": 5.0,
        "cooldown_duration": 30.0,
    }


@pytest.mark.asyncio
async def test_valid_workos_token_returns_provider_neutral_claims(
    private_key: rsa.RSAPrivateKey,
    signing_key: PyJWK,
) -> None:
    client = StaticSigningKeyClient(signing_key)
    verifier = WorkOSAccessTokenVerifier(_settings(), signing_keys=client)
    token = _encode(private_key, _payload())

    claims = await verifier.verify(token)

    assert claims.issuer == ISSUER
    assert claims.subject == "user_test"
    assert claims.provider_session_id == "session_test"
    assert claims.token_id == "token_test"
    assert claims.expires_at > claims.issued_at
    assert client.requested_kids == [KID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "https://wrong.example"),
        ("client_id", "wrong_client"),
        ("sub", ""),
        ("sid", ""),
        ("jti", ""),
    ],
)
async def test_invalid_identity_claims_are_rejected(
    private_key: rsa.RSAPrivateKey,
    signing_key: PyJWK,
    claim: str,
    value: str,
) -> None:
    verifier = WorkOSAccessTokenVerifier(
        _settings(),
        signing_keys=StaticSigningKeyClient(signing_key),
    )
    token = _encode(private_key, _payload(**{claim: value}))

    with pytest.raises(AccessTokenVerificationError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_expired_token_is_rejected(
    private_key: rsa.RSAPrivateKey,
    signing_key: PyJWK,
) -> None:
    now = datetime.now(tz=UTC)
    token = _encode(
        private_key,
        _payload(
            iat=int((now - timedelta(minutes=2)).timestamp()),
            exp=int((now - timedelta(minutes=1)).timestamp()),
        ),
    )
    verifier = WorkOSAccessTokenVerifier(
        _settings(),
        signing_keys=StaticSigningKeyClient(signing_key),
    )

    with pytest.raises(AccessTokenVerificationError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_unsupported_algorithm_is_rejected_before_key_lookup(
    signing_key: PyJWK,
) -> None:
    client = StaticSigningKeyClient(signing_key)
    verifier = WorkOSAccessTokenVerifier(_settings(), signing_keys=client)
    token = jwt.encode(
        _payload(),
        "not-used-by-verifier-but-long-enough-for-hs256",
        algorithm="HS256",
        headers={"kid": KID},
    )

    with pytest.raises(AccessTokenVerificationError):
        await verifier.verify(token)

    assert client.requested_kids == []


@pytest.mark.asyncio
async def test_missing_kid_is_rejected_before_key_lookup(
    private_key: rsa.RSAPrivateKey,
    signing_key: PyJWK,
) -> None:
    client = StaticSigningKeyClient(signing_key)
    verifier = WorkOSAccessTokenVerifier(_settings(), signing_keys=client)
    token = jwt.encode(_payload(), private_key, algorithm="RS256")

    with pytest.raises(AccessTokenVerificationError):
        await verifier.verify(token)

    assert client.requested_kids == []


@pytest.mark.asyncio
async def test_non_integer_timestamp_is_rejected(
    private_key: rsa.RSAPrivateKey,
    signing_key: PyJWK,
) -> None:
    verifier = WorkOSAccessTokenVerifier(
        _settings(),
        signing_keys=StaticSigningKeyClient(signing_key),
    )
    token = _encode(private_key, _payload(exp="9999999999"))

    with pytest.raises(AccessTokenVerificationError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_local_token_size_limit_fails_before_jwks_lookup(
    signing_key: PyJWK,
) -> None:
    client = StaticSigningKeyClient(signing_key)
    verifier = WorkOSAccessTokenVerifier(
        _settings(max_bearer_token_length=32),
        signing_keys=client,
    )

    with pytest.raises(AccessTokenVerificationError):
        await verifier.verify("x" * 33)

    assert client.requested_kids == []

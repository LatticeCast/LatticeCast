import base64
import hashlib

from router.api.sso import _hash, _pkce_challenge, _redirect_with_code, _valid_redirect_uri


def test_pkce_s256_matches_rfc7636_example():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert _pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_secrets_are_hashed_before_storage():
    secret = "sso-secret"
    assert _hash(secret) == hashlib.sha256(secret.encode()).hexdigest()
    assert _hash(secret) != secret


def test_redirect_preserves_existing_query_and_never_preserves_fragment():
    uri = "https://consumer.example/auth/lattice-cast/callback?return_to=%2Fhome#ignored"
    assert _redirect_with_code(uri, "one-time-code", "opaque-state") == (
        "https://consumer.example/auth/lattice-cast/callback?return_to=%2Fhome"
        "&code=one-time-code&state=opaque-state"
    )


def test_client_redirect_uri_requires_an_absolute_fragment_free_uri():
    assert _valid_redirect_uri("https://consumer.example/auth/lattice-cast/callback")
    assert not _valid_redirect_uri("/sso/callback")
    assert not _valid_redirect_uri("tappi://auth/callback")
    assert not _valid_redirect_uri("https://consumer.example/auth/lattice-cast/callback#code")

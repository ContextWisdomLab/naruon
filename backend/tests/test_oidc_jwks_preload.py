from unittest.mock import MagicMock

from api import auth as auth_module


def test_preload_oidc_jwks_clears_cache_without_client(monkeypatch):
    monkeypatch.setattr(auth_module, "jwks_client", None)
    monkeypatch.setattr(auth_module, "_cached_oidc_signing_keys", ("previous_key",))

    auth_module.preload_oidc_jwks()

    assert auth_module._cached_oidc_signing_keys == ()


def test_preload_oidc_jwks_refreshes_and_caches_keys(monkeypatch):
    jwk_set = MagicMock()
    jwk_set.keys = ["key1", "key2"]
    client = MagicMock()
    client.get_jwk_set.return_value = jwk_set
    monkeypatch.setattr(auth_module, "jwks_client", client)
    monkeypatch.setattr(auth_module, "_cached_oidc_signing_keys", ("previous_key",))

    auth_module.preload_oidc_jwks()

    client.get_jwk_set.assert_called_once_with(refresh=True)
    assert auth_module._cached_oidc_signing_keys == ("key1", "key2")


def test_preload_oidc_jwks_clears_cache_when_refresh_fails(monkeypatch):
    client = MagicMock()
    client.get_jwk_set.side_effect = Exception("Test Exception")
    monkeypatch.setattr(auth_module, "jwks_client", client)
    monkeypatch.setattr(auth_module, "_cached_oidc_signing_keys", ("previous_key",))

    auth_module.preload_oidc_jwks()

    client.get_jwk_set.assert_called_once_with(refresh=True)
    assert auth_module._cached_oidc_signing_keys == ()

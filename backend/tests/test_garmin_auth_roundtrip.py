"""
Tests pour garmin_auth.py — Tache 3.6.2
Test serialisation/deserialisation token Garth roundtrip.
Verifie que le cycle complet fonctionne : dumps() → encrypt → decrypt → loads().
"""
import pytest
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet
from fastapi import HTTPException


# Generer une cle Fernet valide pour les tests
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()

# Token Garth simule (ce que client.dumps() retourne)
FAKE_GARTH_TOKEN = '{"oauth1": {"token": "abc123"}, "oauth2": {"access_token": "xyz789", "expires_at": 9999999999}}'


@pytest.fixture(autouse=True)
def _patch_settings():
    """Patche get_settings pour fournir une ENCRYPTION_KEY valide."""
    mock_settings = MagicMock()
    mock_settings.ENCRYPTION_KEY = TEST_ENCRYPTION_KEY
    with patch("app.auth.garmin_auth.get_settings", return_value=mock_settings):
        # Re-importer pour que GarminAuthManager utilise la cle mockee
        import importlib
        import app.auth.garmin_auth as mod
        importlib.reload(mod)
        yield mod


def _get_manager(mod):
    """Retourne l'instance GarminAuthManager du module reloade."""
    return mod.garmin_auth


# ============================================================
# Test roundtrip encrypt → decrypt
# ============================================================


class TestEncryptDecryptRoundtrip:
    """Verifie que encrypt_token puis decrypt_token redonne le token original."""

    def test_roundtrip_simple_string(self, _patch_settings):
        mgr = _get_manager(_patch_settings)
        original = "hello-garth-token"
        encrypted = mgr.encrypt_token(original)
        assert encrypted != original
        decrypted = mgr.decrypt_token(encrypted)
        assert decrypted == original

    def test_roundtrip_json_token(self, _patch_settings):
        mgr = _get_manager(_patch_settings)
        encrypted = mgr.encrypt_token(FAKE_GARTH_TOKEN)
        decrypted = mgr.decrypt_token(encrypted)
        assert decrypted == FAKE_GARTH_TOKEN

    def test_roundtrip_unicode(self, _patch_settings):
        mgr = _get_manager(_patch_settings)
        original = '{"display_name": "André Béréa"}'
        encrypted = mgr.encrypt_token(original)
        decrypted = mgr.decrypt_token(encrypted)
        assert decrypted == original

    def test_encrypted_is_different_each_time(self, _patch_settings):
        """Fernet utilise un IV aleatoire, donc 2 chiffrements du meme token different."""
        mgr = _get_manager(_patch_settings)
        enc1 = mgr.encrypt_token(FAKE_GARTH_TOKEN)
        enc2 = mgr.encrypt_token(FAKE_GARTH_TOKEN)
        assert enc1 != enc2
        # Mais les deux se dechiffrent au meme resultat
        assert mgr.decrypt_token(enc1) == mgr.decrypt_token(enc2) == FAKE_GARTH_TOKEN


# ============================================================
# Test roundtrip complet : login → dumps → encrypt → decrypt → loads
# ============================================================


class TestFullGarthRoundtrip:
    """Simule le cycle complet avec mock garth.Client."""

    def test_login_then_get_client(self, _patch_settings):
        """login() → token chiffre → get_client() reconstruit le client."""
        mod = _patch_settings
        mgr = _get_manager(mod)

        mock_client_instance = MagicMock()
        mock_client_instance.dumps.return_value = FAKE_GARTH_TOKEN
        mock_client_instance.login.return_value = None

        with patch.object(mod.garth, "Client", return_value=mock_client_instance):
            encrypted_token = mgr.login("user@test.com", "password123")

        assert encrypted_token is not None
        assert isinstance(encrypted_token, str)
        assert encrypted_token != FAKE_GARTH_TOKEN

        # Maintenant reconstruire le client
        mock_restored_client = MagicMock()
        with patch.object(mod.garth, "Client", return_value=mock_restored_client):
            client = mgr.get_client(encrypted_token)

        # Verifie que loads() a ete appele avec le token original
        mock_restored_client.loads.assert_called_once_with(FAKE_GARTH_TOKEN)
        assert client is mock_restored_client

    def test_dumps_value_preserved_through_encryption(self, _patch_settings):
        """Le token retourne par dumps() doit etre identique apres decrypt."""
        mod = _patch_settings
        mgr = _get_manager(mod)

        mock_client = MagicMock()
        mock_client.dumps.return_value = FAKE_GARTH_TOKEN

        with patch.object(mod.garth, "Client", return_value=mock_client):
            encrypted = mgr.login("a@b.com", "pass")

        decrypted = mgr.decrypt_token(encrypted)
        assert decrypted == FAKE_GARTH_TOKEN


# ============================================================
# Test erreurs
# ============================================================


class TestRoundtripErrors:
    """Verifie le comportement en cas d'erreurs dans le roundtrip."""

    def test_decrypt_with_wrong_key_fails(self, _patch_settings):
        """Un token chiffre avec une cle ne peut pas etre dechiffre avec une autre."""
        mgr = _get_manager(_patch_settings)
        encrypted = mgr.encrypt_token(FAKE_GARTH_TOKEN)

        # Creer un manager avec une cle differente
        other_key = Fernet.generate_key().decode()
        other_cipher = Fernet(other_key.encode())
        mgr_copy = _get_manager(_patch_settings)
        mgr_copy.cipher = other_cipher

        with pytest.raises(HTTPException) as exc_info:
            mgr_copy.decrypt_token(encrypted)
        assert exc_info.value.status_code == 400

    def test_encrypt_empty_token_raises(self, _patch_settings):
        mgr = _get_manager(_patch_settings)
        with pytest.raises(HTTPException) as exc_info:
            mgr.encrypt_token("")
        assert exc_info.value.status_code == 400

    def test_decrypt_empty_token_raises(self, _patch_settings):
        mgr = _get_manager(_patch_settings)
        with pytest.raises(HTTPException) as exc_info:
            mgr.decrypt_token("")
        assert exc_info.value.status_code == 400

    def test_decrypt_garbage_raises(self, _patch_settings):
        mgr = _get_manager(_patch_settings)
        with pytest.raises(HTTPException) as exc_info:
            mgr.decrypt_token("not-a-valid-fernet-token")
        assert exc_info.value.status_code == 400

    def test_no_encryption_key_raises(self, _patch_settings):
        """Si ENCRYPTION_KEY est absente, encrypt/decrypt doivent lever 500."""
        mgr = _get_manager(_patch_settings)
        mgr.cipher = None

        with pytest.raises(HTTPException) as exc_info:
            mgr.encrypt_token(FAKE_GARTH_TOKEN)
        assert exc_info.value.status_code == 500

        with pytest.raises(HTTPException) as exc_info:
            mgr.decrypt_token("some-token")
        assert exc_info.value.status_code == 500

    def test_get_client_loads_failure_raises_401(self, _patch_settings):
        """Si loads() echoue (token corrompu/expire), get_client leve 401."""
        mod = _patch_settings
        mgr = _get_manager(mod)
        encrypted = mgr.encrypt_token(FAKE_GARTH_TOKEN)

        mock_client = MagicMock()
        mock_client.loads.side_effect = Exception("Token expire")

        with patch.object(mod.garth, "Client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                mgr.get_client(encrypted)
            assert exc_info.value.status_code == 401

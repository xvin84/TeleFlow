"""
Unit tests for teleflow.utils.crypto

Tests Fernet encryption, salt generation, and session re-encryption
without any Qt or Telegram dependencies.
"""
import pytest
from teleflow.utils.crypto import (
    generate_salt,
    salt_to_hex,
    salt_from_hex,
    SessionManager,
    make_session_manager,
)


class TestSalt:
    def test_generate_salt_length(self) -> None:
        assert len(generate_salt()) == 32

    def test_generate_salt_unique(self) -> None:
        assert generate_salt() != generate_salt()

    def test_salt_roundtrip(self) -> None:
        salt = generate_salt()
        assert salt_from_hex(salt_to_hex(salt)) == salt

    def test_salt_hex_is_string(self) -> None:
        assert isinstance(salt_to_hex(generate_salt()), str)


class TestSessionManager:
    def _mgr(self, password: str = "testpass") -> SessionManager:
        return SessionManager(password=password, salt=generate_salt())

    def test_roundtrip(self) -> None:
        mgr = self._mgr()
        assert mgr.decrypt(mgr.encrypt("session_abc123")) == "session_abc123"

    def test_encrypted_differs_from_plaintext(self) -> None:
        mgr = self._mgr()
        assert mgr.encrypt("hello") != "hello"

    def test_wrong_key_raises(self) -> None:
        salt = generate_salt()
        m1 = SessionManager("pass1", salt)
        m2 = SessionManager("pass2", salt)
        enc = m1.encrypt("secret")
        with pytest.raises(Exception):
            m2.decrypt(enc)

    def test_empty_string_roundtrip(self) -> None:
        mgr = self._mgr()
        assert mgr.decrypt(mgr.encrypt("")) == ""

    def test_unicode_roundtrip(self) -> None:
        mgr = self._mgr()
        data = "сессия_тест_🔑"
        assert mgr.decrypt(mgr.encrypt(data)) == data

    def test_same_password_salt_deterministic_key(self) -> None:
        salt = generate_salt()
        m1 = SessionManager("pw", salt)
        m2 = SessionManager("pw", salt)
        enc = m1.encrypt("data")
        assert m2.decrypt(enc) == "data"


class TestReencrypt:
    def test_reencrypt_preserves_plaintext(self) -> None:
        salt = generate_salt()
        m_old = SessionManager("old_pass", salt)
        original = "my_telegram_session"
        enc_new = m_old.reencrypt(m_old.encrypt(original), "new_pass")
        m_new = SessionManager("new_pass", salt)
        assert m_new.decrypt(enc_new) == original

    def test_reencrypt_old_key_cant_read_new(self) -> None:
        salt = generate_salt()
        m_old = SessionManager("old", salt)
        enc_new = m_old.reencrypt(m_old.encrypt("data"), "new")
        with pytest.raises(Exception):
            m_old.decrypt(enc_new)

    def test_reencrypt_same_password_roundtrip(self) -> None:
        salt = generate_salt()
        mgr = SessionManager("same", salt)
        data = "unchanged"
        enc = mgr.encrypt(data)
        re_enc = mgr.reencrypt(enc, "same")
        assert mgr.decrypt(re_enc) == data


class TestMakeSessionManager:
    def test_none_password_uses_sentinel(self) -> None:
        salt = generate_salt()
        m1 = make_session_manager(None, salt)
        m2 = make_session_manager(None, salt)
        enc = m1.encrypt("data")
        assert m2.decrypt(enc) == "data"

    def test_empty_string_uses_sentinel(self) -> None:
        salt = generate_salt()
        m1 = make_session_manager("", salt)
        m2 = make_session_manager(None, salt)
        enc = m1.encrypt("data")
        assert m2.decrypt(enc) == "data"

    def test_real_password_differs_from_sentinel(self) -> None:
        salt = generate_salt()
        m_sentinel = make_session_manager(None, salt)
        m_real = make_session_manager("mypassword", salt)
        enc = m_sentinel.encrypt("data")
        with pytest.raises(Exception):
            m_real.decrypt(enc)

import os
from smtplib import (SMTP, SMTP_SSL, SMTPAuthenticationError,
                     SMTPResponseException)
from unittest import mock

import pytest

from smtpdfix.handlers import _base64_encode as encode


def test_init(smtpd):
    host = os.getenv("SMTPD_HOST", "127.0.0.1")
    port = int(os.getenv("SMTPD_PORT", "8025"))
    assert smtpd.hostname == host
    assert smtpd.port == port
    assert len(smtpd.messages) == 0


def test_init_ssl(mock_smtpd_use_ssl, smtpd, msg):
    with SMTP_SSL(smtpd.hostname, smtpd.port) as client:
        client.send_message(msg)

    assert len(smtpd.messages) == 1


def test_AUTH_unknown_mechanism(monkeypatch, smtpd):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.ehlo()
        code, response = client.docmd("AUTH", args="FAKEMECH")
        assert code == 504


def test_AUTH_LOGIN_abort(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.ehlo()
        code, resp = client.docmd("AUTH", f"LOGIN {encode(user.username)}")
        assert code == 334
        code, resp = client.docmd("*")
        assert code == 501


def test_AUTH_LOGIN_success(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.ehlo()
        code, resp = client.docmd("AUTH", f"LOGIN {encode(user.username)}")
        assert code == 334
        assert resp == bytes(encode("Password"), "ascii")
        code, resp = client.docmd(f"{encode(user.password)}")
        assert code == 235


def test_AUTH_PLAIN(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    enc = encode(f"{user.username} {user.password}")
    cmd_text = f"PLAIN {enc}"
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.ehlo()
        (code, resp) = client.docmd("AUTH", args=cmd_text)
        assert code == 235


def test_AUTH_PLAIN_no_encryption(smtpd, user):
    enc = encode(f"{user.username} {user.password}")
    cmd_text = f"PLAIN {enc}"
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.ehlo()
        (code, resp) = client.docmd("AUTH", args=cmd_text)
        assert code == 538


def test_AUTH_PLAIN_two_parts(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.ehlo()
        code, resp = client.docmd("AUTH", "PLAIN")
        assert (code, resp) == (334, b"")
        enc = encode(f"{user.username} {user.password}")
        code, resp = client.docmd(enc)
        assert code == 235


def test_AUTH_PLAIN_failure(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.ehlo()
        enc = encode(f"{user.username} {user.password[:0:-1]}")
        code, resp = client.docmd("AUTH", f"PLAIN {enc}")
        assert code == 535
        assert resp == b"5.7.8 Authentication credentials invalid"


def test_VRFY(smtpd, user):
    with SMTP(smtpd.hostname, smtpd.port) as client:
        code, resp = client.verify(user.username)
        assert code == 252


def test_VRFY_failure(smtpd):
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.help()
        code, resp = client.verify("failure@example.org")
        assert code == 502


def test_alt_port(mock_smtpd_port, smtpd):
    assert smtpd.port == 5025


def test_login(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        assert client.login(user.username, user.password)


def test_login_fail(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with pytest.raises(SMTPAuthenticationError) as ex:
        with SMTP(smtpd.hostname, smtpd.port) as client:
            client.starttls()
            assert client.login(user.username, user.password[:0:-1])

    assert ex.type is SMTPAuthenticationError


def test_login_no_tls(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_AUTH_REQUIRE_TLS", "False")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        assert client.login(user.username, user.password)


def test_login_already_done(monkeypatch, smtpd, user):
    monkeypatch.setenv("SMTPD_ENFORCE_AUTH", "True")
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.login(user.username, user.password)
        # we need to explicitly get the response from the the second AUTH
        # command because smtplib doesn't treat it as an error.
        code, resp = client.docmd("AUTH", "LOGIN")
        assert code == 503
        assert resp == b"Already authenticated"


def test_no_messages(smtpd):
    assert len(smtpd.messages) == 0


def test_send_message(smtpd, msg):
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.send_message(msg)

    assert len(smtpd.messages) == 1


def test_send_message_logged_in(monkeypatch, smtpd, user, msg):
    monkeypatch.setenv("SMTPD_USE_STARTTLS", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.starttls()
        client.login(user.username, user.password)
        client.send_message(msg)

    assert len(smtpd.messages) == 1


def test_send_messaged_auth_not_complete(monkeypatch, smtpd, msg):
    monkeypatch.setenv("SMTPD_ENFORCE_AUTH", "True")
    with pytest.raises(SMTPResponseException) as er:
        with SMTP(smtpd.hostname, smtpd.port) as client:
            client.send_message(msg)
    assert er.match(r"^\(530")


def test_sendmail(smtpd):
    from_addr = "from.addr@example.org"
    to_addr = "to.addr@example.org"
    msg = (f"From: {from_addr}\r\n"
           f"To: {to_addr}\r\n"
           f"Subject: Foo\r\n\r\n"
           f"Foo bar")

    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.sendmail(from_addr, to_addr, msg)

    assert len(smtpd.messages) == 1


@mock.patch.dict(os.environ, {"SMTPD_ENFORCE_AUTH": "True"})
def test_mock_patch(smtpd):
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.helo()
        code, repl = client.docmd("DATA", "")
        assert code == 530
        assert repl.startswith(b"5.7.0 Authentication required")


def test_monkeypatch(monkeypatch, smtpd):
    monkeypatch.setenv("SMTPD_ENFORCE_AUTH", "True")
    with SMTP(smtpd.hostname, smtpd.port) as client:
        client.helo()
        code, repl = client.docmd("DATA", "")
        assert code == 530
        assert repl.startswith(b"5.7.0 Authentication required")

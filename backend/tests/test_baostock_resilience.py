import socket

from baostock.common import context as bs_context

from backend.app.sources.baostock_source import BaostockSource


def test_baostock_session_applies_and_restores_socket_timeout(monkeypatch):
    observed = {}

    class SessionSocket:
        def settimeout(self, value):
            observed["session_timeout"] = value

    class LoginResult:
        error_code = "0"
        error_msg = "success"

    class FakeBaostock:
        def login(self):
            observed["login_timeout"] = socket.getdefaulttimeout()
            return LoginResult()

        def logout(self):
            observed["logout"] = True

    previous = socket.getdefaulttimeout()
    monkeypatch.setattr(bs_context, "default_socket", SessionSocket(), raising=False)
    source = BaostockSource(socket_timeout_seconds=7)
    source._bs = FakeBaostock()

    with source.session() as client:
        assert client is source._bs
        assert socket.getdefaulttimeout() == previous

    assert observed == {"login_timeout": 7.0, "session_timeout": 7.0, "logout": True}
    assert socket.getdefaulttimeout() == previous

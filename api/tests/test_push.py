import pytest
from pywebpush import WebPushException

from app.alerts import push
from app.config import Settings

SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "p", "auth": "a"}}
PAYLOAD = {"title": "Retraso", "body": "AVE 03304 lleva 12 min"}


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def settings(tmp_path, key="clave-privada"):
    return Settings(data_dir=tmp_path, vapid_private_key=key, vapid_subject="mailto:test@example.com")


def raising(exc):
    def fake_webpush(**kwargs):
        raise exc
    return fake_webpush


def test_ok(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(push, "webpush", lambda **kwargs: calls.append(kwargs))
    assert push.send_push(settings(tmp_path), SUB, PAYLOAD) == "ok"
    assert len(calls) == 1 and calls[0]["subscription_info"] == SUB


@pytest.mark.parametrize("status, expected", [(410, "gone"), (404, "gone"), (500, "error")])
def test_webpush_exception(tmp_path, monkeypatch, status, expected):
    exc = WebPushException("fallo", response=FakeResponse(status))
    monkeypatch.setattr(push, "webpush", raising(exc))
    assert push.send_push(settings(tmp_path), SUB, PAYLOAD) == expected


def test_network_failure_is_error(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "webpush", raising(ConnectionError("sin red")))
    assert push.send_push(settings(tmp_path), SUB, PAYLOAD) == "error"


def test_unconfigured_does_not_send(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "webpush", raising(AssertionError("no debe llamarse")))
    assert push.send_push(settings(tmp_path, key=""), SUB, PAYLOAD) == "error"

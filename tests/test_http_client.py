"""
Tests for the dual-transport HTTP client and per-domain throttle.

Run: pytest tests/test_http_client.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.searchers.http_client import (
    BLOCK_STATUSES,
    THROTTLE_PENALTY_STATUSES,
    DomainThrottle,
    DualTransportSession,
)


# --- throttle ---------------------------------------------------------

def test_throttle_spaces_same_host():
    t = DomainThrottle(base_delay=0.3)
    start = time.monotonic()
    for _ in range(3):
        t.wait("https://pub.example/a")
    assert time.monotonic() - start >= 0.6


def test_throttle_does_not_block_different_hosts():
    t = DomainThrottle(base_delay=0.5)
    start = time.monotonic()
    t.wait("https://a.example/x")
    t.wait("https://b.example/x")
    assert time.monotonic() - start < 0.2


def test_throttle_exempts_infrastructure_hosts():
    t = DomainThrottle(base_delay=0.5)
    start = time.monotonic()
    for _ in range(5):
        t.wait("https://doi.org/10.1/x")
    assert time.monotonic() - start < 0.2


def test_backoff_grows_and_decays():
    t = DomainThrottle(base_delay=0.01)
    url = "https://slow.example/x"
    host = "slow.example"

    t.penalise(url)
    first = t._backoff[host]
    t.penalise(url)
    second = t._backoff[host]
    assert second > first, "backoff should grow on repeated blocks"

    t.reward(url)
    assert t._backoff[host] == pytest.approx(second / 2), "success should halve backoff"


def test_backoff_clears_after_enough_success():
    t = DomainThrottle(base_delay=0.01)
    url = "https://slow.example/x"
    t.penalise(url)
    for _ in range(10):
        t.reward(url)
    assert "slow.example" not in t._backoff


def test_backoff_is_capped():
    t = DomainThrottle(base_delay=0.01)
    url = "https://slow.example/x"
    for _ in range(20):
        t.penalise(url)
    from src.searchers.http_client import MAX_DOMAIN_BACKOFF
    assert t._backoff["slow.example"] <= MAX_DOMAIN_BACKOFF


def test_403_is_not_a_throttle_penalty():
    """A Cloudflare bot-block is permanent - backing off just stalls the run."""
    assert 403 in BLOCK_STATUSES          # worth retrying on the other transport
    assert 403 not in THROTTLE_PENALTY_STATUSES  # but NOT worth waiting on
    assert 429 in THROTTLE_PENALTY_STATUSES


# --- dual transport ---------------------------------------------------

class FakeResp:
    def __init__(self, status, url="https://x.example/"):
        self.status_code = status
        self.url = url
        self.headers = {"content-type": "text/html"}

    def close(self):
        pass


@pytest.fixture
def session():
    s = DualTransportSession("UA/1.0", pool_size=2)
    s.throttle = DomainThrottle(base_delay=0.0)
    return s


def test_falls_back_to_requests_on_block(session, monkeypatch):
    calls = []

    class Curl:
        def get(self, url, **kw):
            calls.append("curl")
            return FakeResp(403)

    class Req:
        def get(self, url, **kw):
            calls.append("requests")
            return FakeResp(200)

    monkeypatch.setattr(type(session), "_curl_session", property(lambda self: Curl()))
    monkeypatch.setattr(type(session), "_requests_session", property(lambda self: Req()))

    r = session.get("https://blocked.example/paper")
    assert r.status_code == 200
    assert calls == ["curl", "requests"]


def test_no_fallback_when_primary_succeeds(session, monkeypatch):
    calls = []

    class Curl:
        def get(self, url, **kw):
            calls.append("curl")
            return FakeResp(200)

    class Req:
        def get(self, url, **kw):
            calls.append("requests")
            return FakeResp(200)

    monkeypatch.setattr(type(session), "_curl_session", property(lambda self: Curl()))
    monkeypatch.setattr(type(session), "_requests_session", property(lambda self: Req()))

    assert session.get("https://ok.example/p").status_code == 200
    assert calls == ["curl"]


def test_falls_back_on_transport_exception(session, monkeypatch):
    class Curl:
        def get(self, url, **kw):
            raise RuntimeError("TLS blew up")

    class Req:
        def get(self, url, **kw):
            return FakeResp(200)

    monkeypatch.setattr(type(session), "_curl_session", property(lambda self: Curl()))
    monkeypatch.setattr(type(session), "_requests_session", property(lambda self: Req()))

    assert session.get("https://flaky.example/p").status_code == 200


def test_works_without_curl_cffi(session, monkeypatch):
    class Req:
        def get(self, url, **kw):
            return FakeResp(200)

    monkeypatch.setattr(type(session), "_curl_session", property(lambda self: None))
    monkeypatch.setattr(type(session), "_requests_session", property(lambda self: Req()))

    assert session.get("https://x.example/p").status_code == 200

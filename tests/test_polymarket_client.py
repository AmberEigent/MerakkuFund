"""Tests for the official-SDK order book path and its REST fallback."""
from __future__ import annotations

from polyagents.dataflows.polymarket_client import PolymarketDataClient

BASES = ("https://gamma", "https://clob", "https://data")


# --- SDK doubles (py-clob-client OrderBookSummary / OrderSummary shape) ------

class _Level:
    def __init__(self, price, size):
        self.price = str(price)   # SDK returns strings
        self.size = str(size)


class _Summary:
    def __init__(self, bids, asks):
        self.bids = bids
        self.asks = asks


class FakeClob:
    def __init__(self, summary=None, raises=False):
        self._summary = summary
        self._raises = raises

    def get_order_book(self, token_id):
        if self._raises:
            raise RuntimeError("sdk boom")
        return self._summary


# --- REST double -------------------------------------------------------------

class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class FakeHttp:
    def __init__(self, payload):
        self._p = payload
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        return _Resp(self._p)

    def close(self):
        pass


def test_order_book_from_official_sdk():
    summary = _Summary(
        bids=[_Level(0.44, 200), _Level(0.43, 100)],
        asks=[_Level(0.46, 80)],
    )
    client = PolymarketDataClient(*BASES, clob=FakeClob(summary=summary))
    book = client.fetch_order_book("tok")
    assert book is not None
    assert book.best_bid == 0.44   # sorted best-first, parsed from strings
    assert book.best_ask == 0.46
    assert book.bids[0].size == 200.0


def test_rest_fallback_when_sdk_disabled():
    http = FakeHttp({"bids": [{"price": "0.40", "size": "10"}],
                     "asks": [{"price": "0.50", "size": "5"}]})
    client = PolymarketDataClient(*BASES, http=http, use_clob_sdk=False)
    book = client.fetch_order_book("tok")
    assert http.calls == 1          # went over REST
    assert book.best_bid == 0.40
    assert book.best_ask == 0.50


def test_rest_fallback_when_sdk_raises():
    http = FakeHttp({"bids": [{"price": "0.30", "size": "7"}], "asks": []})
    client = PolymarketDataClient(*BASES, http=http, clob=FakeClob(raises=True))
    book = client.fetch_order_book("tok")
    assert http.calls == 1          # SDK failed -> REST
    assert book.best_bid == 0.30

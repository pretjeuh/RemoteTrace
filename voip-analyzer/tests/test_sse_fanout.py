"""Tests for the live dashboard's SSE fan-out.

Regression guard: the endpoint once used a single shared queue, so one client
consuming an event (queue.get removes it) starved every other client. Each
client must now get its own copy of every event, and a client connecting
mid-capture must be seeded with the latest snapshot.
"""

from voip_analyzer.web import app


def _drain(q):
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def test_every_subscriber_receives_every_event():
    """Concurrent clients each receive all broadcast events, none stolen."""
    a, b, c = app._subscribe(), app._subscribe(), app._subscribe()
    try:
        app._broadcast({"stats": {"total_packets": 1}})
        app._broadcast({"stats": {"total_packets": 2}})

        for q in (a, b, c):
            totals = [e["stats"]["total_packets"] for e in _drain(q)]
            assert totals == [1, 2]
    finally:
        for q in (a, b, c):
            app._unsubscribe(q)


def test_late_subscriber_gets_latest_snapshot():
    """A client connecting mid-capture is seeded with the most recent event."""
    app._broadcast({"stats": {"total_packets": 99}})

    late = app._subscribe()
    try:
        snapshot = late.get_nowait()
        assert snapshot["stats"]["total_packets"] == 99
    finally:
        app._unsubscribe(late)


def test_unsubscribe_stops_delivery():
    """After a client disconnects, broadcasts no longer target its queue."""
    q = app._subscribe()
    app._unsubscribe(q)
    _drain(q)  # clear any seed

    app._broadcast({"stats": {"total_packets": 5}})

    assert q.empty()

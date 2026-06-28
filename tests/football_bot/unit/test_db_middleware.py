import pytest

from football_bot.middlewares.db_middleware import DBSessionMiddleware


class FakeSessionManager:
    def __init__(self, session):
        self.session = session
        self.entered = False
        self.exited = False
        self.exit_exc_type = None

    async def __aenter__(self):
        self.entered = True
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        self.exit_exc_type = exc_type


class FakeSessionPool:
    def __init__(self, manager):
        self.manager = manager
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.manager


def test_db_session_middleware_injects_session(run_async):
    session = object()
    manager = FakeSessionManager(session)
    pool = FakeSessionPool(manager)
    middleware = DBSessionMiddleware(pool)
    observed = {}

    async def handler(event, data):
        observed["event"] = event
        observed["session"] = data["session"]
        return "ok"

    result = run_async(middleware(handler, event="evt", data={}))

    assert result == "ok"
    assert pool.calls == 1
    assert manager.entered is True
    assert manager.exited is True
    assert observed == {"event": "evt", "session": session}


def test_db_session_middleware_closes_session_on_handler_error(run_async):
    session = object()
    manager = FakeSessionManager(session)
    pool = FakeSessionPool(manager)
    middleware = DBSessionMiddleware(pool)

    async def handler(_event, _data):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_async(middleware(handler, event="evt", data={}))

    assert pool.calls == 1
    assert manager.entered is True
    assert manager.exited is True
    assert manager.exit_exc_type is RuntimeError

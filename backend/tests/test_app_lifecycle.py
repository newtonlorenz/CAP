from app.main import app


def test_app_uses_lifespan_not_on_event_handlers():
    assert app.router.on_startup == []
    assert app.router.on_shutdown == []
    assert app.router.lifespan_context is not None

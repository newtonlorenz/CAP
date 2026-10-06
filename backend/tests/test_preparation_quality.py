from types import SimpleNamespace

from app.schemas.preparation_quality import ImportEnhancementRequest
from app.services.preparation_quality import enhance_import


def request():
    return ImportEnhancementRequest(
        headers=["Question", "Instructions"],
        rows=[
            {"row_index": 1, "question": "Is the company registered?", "explicit_type": True},
            {"row_index": 2, "question": "Provide the date (optional)"},
        ],
        mapping={"question": 0, "help": 1},
        header_row=0,
        external_processing_confirmed=True,
        settings_revision=1,
    )


async def test_preview_unavailable_preserves_baseline():
    result = await enhance_import(
        request(), SimpleNamespace(jev_enabled=False, typesafe_api_key="")
    )
    assert result.status == "skipped"
    assert not result.field_suggestions
    assert not result.suggested_mapping


async def test_preview_only_infers_missing_metadata_and_bounds_provider_state(monkeypatch):
    class Client:
        def __init__(self, config):
            pass

        async def evaluate(self, state, questions):
            assert all(key in ("headers", "rows") for key in state)
            assert "type_1" not in questions
            answers = {}
            for key, question in questions.items():
                value = {
                    "type_2": "date",
                    "required_1": "uncertain",
                    "required_2": "no",
                    "duplicate_2": "none",
                }.get(key, "none")
                answers[key] = {
                    "choice": value,
                    "probabilities": {
                        option: float(option == value) for option in question["criteria"]
                    },
                    "confidence": 1,
                }
            return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 10}}

    monkeypatch.setattr("app.services.preparation_quality.JevClient", Client)
    settings = SimpleNamespace(
        jev_enabled=True, typesafe_api_key="secret", jev_settings_revision=1, jev_model="jev-1.13.0"
    )
    result = await enhance_import(request(), settings)
    assert result.status == "completed"
    assert len(result.field_suggestions) == 1
    assert result.field_suggestions[0].row_index == 2
    assert result.field_suggestions[0].type == "date"
    assert result.field_suggestions[0].required is False


async def test_preview_endpoint_requires_manager_and_consent_and_never_saves(client, db_session):
    from app.models import User
    from app.services.auth import create_access_token

    url = "/api/v1/preparation/templates/import-enhancements"
    users = {}
    for role in ("manager", "contributor"):
        user = User(
            email=f"quality-{role}@example.com",
            password_hash="unused",
            full_name=role,
            role=role,
            active=True,
        )
        db_session.add(user)
        await db_session.flush()
        users[role] = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    await db_session.commit()
    body = request().model_dump()
    assert (await client.post(url, json=body, headers=users["contributor"])).status_code == 403
    body["external_processing_confirmed"] = False
    response = await client.post(url, json=body, headers=users["manager"])
    assert response.status_code == 422
    assert "Confirm external" in response.text
    body["external_processing_confirmed"] = True
    response = await client.post(url, json=body, headers=users["manager"])
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    assert (await client.get("/api/v1/preparation/templates", headers=users["manager"])).json()[
        "total"
    ] == 0


async def test_provider_failure_keeps_manual_import_available(monkeypatch):
    from app.services.jev_provider import JevError

    class Unavailable:
        def __init__(self, config):
            pass

        async def evaluate(self, state, questions):
            raise JevError("Service unavailable")

    monkeypatch.setattr("app.services.preparation_quality.JevClient", Unavailable)
    settings = SimpleNamespace(
        jev_enabled=True, typesafe_api_key="secret", jev_settings_revision=1, jev_model="jev-1.13.0"
    )
    result = await enhance_import(request(), settings)
    assert result.status == "skipped"
    assert result.warnings
    assert not result.field_suggestions
    assert not result.suggested_mapping


async def test_settings_disable_stops_queued_preview_requests_and_discards_suggestions(
    client, db_session, setup_database, monkeypatch
):
    import httpx
    from sqlalchemy import update

    from app.models import User
    from app.models.installation_settings import InstallationSettings
    from app.services.auth import create_access_token
    from app.services.installation_settings import _encrypt
    from app.services.jev_provider import JevClient

    db_session.add(
        InstallationSettings(
            section="jev",
            configuration={"enabled": True, "model": "jev-1.13.0"},
            secret_encrypted=_encrypt("disposable-key"),
            revision=1,
        )
    )
    user = User(
        email="race-manager@example.com",
        password_hash="unused",
        full_name="Manager",
        role="manager",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    source_calls = []

    async def handler(provider_request):
        import json

        payload = json.loads(provider_request.content)
        if "rows" in payload["state"]:
            source_calls.append(payload["state"])
            if len(source_calls) == 1:
                async with setup_database() as fresh_db:
                    await fresh_db.execute(
                        update(InstallationSettings)
                        .where(InstallationSettings.section == "jev")
                        .values(configuration={"enabled": False, "model": "jev-1.13.0"}, revision=2)
                    )
                    await fresh_db.commit()
        answers = {}
        for key, question in payload["questions"].items():
            selected = (
                "0"
                if key == "question"
                else (
                    "text"
                    if key.startswith("type_")
                    else "yes" if key.startswith("required_") else "none"
                )
            )
            answers[key] = {
                "type": "choice",
                "choice": selected,
                "confidence": 1,
                "probabilities": {
                    option: float(option == selected) for option in question["criteria"]
                },
            }
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": answers,
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.preparation_quality.JevClient",
        lambda config, **kwargs: JevClient(config, transport=transport, **kwargs),
    )
    body = request().model_dump()
    body["rows"] = [
        {"row_index": index, "question": f"Blank source question {index}"} for index in range(1, 36)
    ]
    response = await client.post(
        "/api/v1/preparation/templates/import-enhancements", json=body, headers=headers
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "partial"
    assert 1 <= len(source_calls) <= 2
    assert result["field_suggestions"] == []
    assert result["suggested_mapping"] == {}
    assert any("settings changed" in warning.lower() for warning in result["warnings"])

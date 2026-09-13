from types import SimpleNamespace

from api.tenant_config import TenantConfigResponse, _tenant_config_response


def test_noema_orchestrator_token_is_presence_only_in_tenant_config_response():
    fields = TenantConfigResponse.model_fields
    assert "noema_orchestrator_token" not in fields
    assert "has_noema_orchestrator_token" in fields

    response = _tenant_config_response(
        SimpleNamespace(
            user_id="user-1",
            noema_orchestrator_base_url="https://orchestrator.internal/v1",
            noema_orchestrator_token="orch-secret",
        )
    ).model_dump()

    assert response["noema_orchestrator_base_url"] == "https://orchestrator.internal/v1"
    assert response["has_noema_orchestrator_token"] is True
    assert "noema_orchestrator_token" not in response
    assert "orch-secret" not in repr(response)


def test_noema_orchestrator_token_presence_is_false_when_unset():
    response = _tenant_config_response(
        SimpleNamespace(
            user_id="user-1",
            noema_orchestrator_base_url=None,
            noema_orchestrator_token=None,
        )
    ).model_dump()

    assert response["noema_orchestrator_base_url"] is None
    assert response["has_noema_orchestrator_token"] is False
    assert "noema_orchestrator_token" not in response

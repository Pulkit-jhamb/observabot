import pytest

from observabot.tools import TOOL_SCHEMAS, dispatch, to_text

from .test_agent import FakeObs


def test_every_schema_has_a_handler_name():
    names = {tool["name"] for tool in TOOL_SCHEMAS}
    assert names == {"list_services", "service_health", "get_firing_alerts", "query_prometheus", "lookup_runbook"}


def test_dispatch_rejects_unknown_tool():
    with pytest.raises(KeyError):
        dispatch(FakeObs(), "delete_everything", {})


def test_dispatch_rejects_missing_argument():
    with pytest.raises(KeyError):
        dispatch(FakeObs(), "service_health", {})


def test_dispatch_routes_to_service_health():
    result = dispatch(FakeObs(), "service_health", {"service": "payments"})
    assert result["service"] == "payments"


def test_to_text_is_json():
    assert to_text({"a": 1}) == '{\n  "a": 1\n}'

import asyncio

from observabot.mcp_server import build_server
from observabot.slack_app import clean_question

from .test_agent import FakeObs


def test_clean_question_strips_mentions():
    assert clean_question("<@U0123ABC> how is checkout doing?") == "how is checkout doing?"


def test_clean_question_handles_empty_text():
    assert clean_question(None) == ""


def test_mcp_server_registers_the_read_only_tools():
    server = build_server(FakeObs())
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {"list_services", "service_health", "get_firing_alerts", "query_prometheus", "lookup_runbook"}

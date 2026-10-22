from types import SimpleNamespace

from observabot.agent import MAX_STEPS, HealthAgent
from observabot.config import Settings
from observabot.tools import Observability


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class ScriptedMessages:
    """Replays scripted responses and records every request the agent sends."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        return self.scripted.pop(0)


class FakeClient:
    def __init__(self, scripted):
        self.messages = ScriptedMessages(scripted)


class FakeObs(Observability):
    def __init__(self):
        self.settings = Settings.from_env()
        self.runbooks = []
        self.service_calls = []

    def service_health(self, service):
        self.service_calls.append(service)
        return {"service": service, "request_rate": 12.0, "error_ratio": 0.01, "p95_latency_s": 0.2, "up": 1.0}


def test_runs_tool_then_returns_final_text():
    client = FakeClient(
        [
            response([tool_block("t1", "service_health", {"service": "checkout"})], "tool_use"),
            response([text_block("*checkout* is healthy: 1% errors, p95 200ms.")], "end_turn"),
        ]
    )
    obs = FakeObs()
    agent = HealthAgent(client, "claude-test", obs)

    answer = agent.answer("how is checkout?")

    assert answer == "*checkout* is healthy: 1% errors, p95 200ms."
    assert obs.service_calls == ["checkout"]
    second_request = client.messages.calls[1]["messages"]
    tool_result = second_request[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "t1"
    assert '"error_ratio": 0.01' in tool_result["content"]


def test_passes_tools_model_and_system_prompt():
    client = FakeClient([response([text_block("hi")], "end_turn")])
    HealthAgent(client, "claude-test", FakeObs()).answer("hello")

    call = client.messages.calls[0]
    assert call["model"] == "claude-test"
    assert {t["name"] for t in call["tools"]} >= {"service_health", "get_firing_alerts", "lookup_runbook"}
    assert "ObservaBot" in call["system"]


def test_tool_error_is_reported_back_to_claude():
    client = FakeClient(
        [
            response([tool_block("t1", "no_such_tool", {})], "tool_use"),
            response([text_block("Sorry, that tool failed.")], "end_turn"),
        ]
    )
    answer = HealthAgent(client, "claude-test", FakeObs()).answer("?")

    assert answer == "Sorry, that tool failed."
    result = client.messages.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True


def test_step_limit_stops_a_runaway_loop():
    looping = [
        response([tool_block(f"t{i}", "service_health", {"service": "x"})], "tool_use")
        for i in range(MAX_STEPS)
    ]
    answer = HealthAgent(FakeClient(looping), "claude-test", FakeObs()).answer("loop")
    assert "step limit" in answer

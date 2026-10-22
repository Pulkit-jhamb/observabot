"""Claude tool-calling loop that answers service-health questions in plain English."""

import json
import logging

from .tools import TOOL_SCHEMAS, Observability, dispatch, to_text

log = logging.getLogger(__name__)

MAX_STEPS = 8
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are ObservaBot, an on-call assistant for a platform team.
Answer questions about service health, latency, errors and firing alerts using the tools provided.

Rules:
- Always call a tool to get current numbers. Never guess metrics.
- Prefer service_health and get_firing_alerts over raw PromQL.
- When a question is about an alert or a symptom, call lookup_runbook and summarise the relevant steps.
- Express error ratios as percentages and latency in milliseconds.
- Be brief: lead with the answer, then the supporting numbers. Use Slack-friendly markdown (*bold*, bullets).
- If a tool fails, say so plainly instead of inventing data."""


class HealthAgent:
    def __init__(self, client, model: str, observability: Observability):
        self.client = client
        self.model = model
        self.obs = observability

    def answer(self, question: str) -> str:
        messages = [{"role": "user", "content": question}]

        for _ in range(MAX_STEPS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return _text_of(response.content) or "I didn't get an answer back. Please try again."

            messages.append({"role": "user", "content": self._run_tools(response.content)})

        log.warning("Agent hit the %d-step limit for question: %s", MAX_STEPS, question)
        return "I couldn't finish answering within the step limit. Try a narrower question."

    def _run_tools(self, content) -> list[dict]:
        results = []
        for block in content:
            if block.type != "tool_use":
                continue
            try:
                output = to_text(dispatch(self.obs, block.name, block.input))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
            except Exception as exc:  # report the failure to Claude so it can explain it
                log.exception("Tool %s failed", block.name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": str(exc)}),
                        "is_error": True,
                    }
                )
        return results


def _text_of(content) -> str:
    return "\n".join(block.text for block in content if block.type == "text").strip()

"""Slack bot entry point (Slack Bolt, Socket Mode).

Mention the bot in a channel (`@ObservaBot how is checkout doing?`) or message it directly.
"""

import logging
import re

import anthropic
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .agent import HealthAgent
from .config import Settings
from .tools import Observability

log = logging.getLogger("observabot.slack")

MENTION = re.compile(r"<@[A-Z0-9]+>")
WORKING = ":hourglass_flowing_sand: Checking..."


def clean_question(text: str) -> str:
    return MENTION.sub("", text or "").strip()


def build_app(settings: Settings, agent: HealthAgent) -> App:
    app = App(token=settings.slack_bot_token)

    def respond(event, say, client):
        question = clean_question(event.get("text", ""))
        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]

        if not question:
            say(text="Ask me about a service, e.g. `how is checkout doing?`", thread_ts=thread_ts)
            return

        placeholder = client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=WORKING)
        try:
            answer = agent.answer(question)
        except anthropic.APIError:
            log.exception("Claude API call failed")
            answer = ":warning: I couldn't reach the language model. Try again shortly."
        except Exception:
            log.exception("Unexpected error answering question")
            answer = ":warning: Something went wrong while checking. The error has been logged."

        client.chat_update(channel=channel, ts=placeholder["ts"], text=answer)

    @app.event("app_mention")
    def handle_mention(event, say, client):
        respond(event, say, client)

    @app.event("message")
    def handle_direct_message(event, say, client):
        # Only direct messages; ignore channel chatter and anything from bots (including ourselves).
        if event.get("channel_type") != "im" or event.get("bot_id") or event.get("subtype"):
            return
        respond(event, say, client)

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    for name, value in {
        "SLACK_BOT_TOKEN": settings.slack_bot_token,
        "SLACK_APP_TOKEN": settings.slack_app_token,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    }.items():
        if not value:
            raise SystemExit(f"{name} is not set. See .env.example.")

    obs = Observability(settings)
    agent = HealthAgent(anthropic.Anthropic(api_key=settings.anthropic_api_key), settings.claude_model, obs)
    app = build_app(settings, agent)

    log.info("ObservaBot starting (model=%s, prometheus=%s)", settings.claude_model, settings.prometheus_url)
    SocketModeHandler(app, settings.slack_app_token).start()


if __name__ == "__main__":
    main()

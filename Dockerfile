FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY observabot ./observabot
COPY runbooks ./runbooks

# The bot and MCP server share this image; docker-compose picks the command.
CMD ["python", "-m", "observabot.slack_app"]

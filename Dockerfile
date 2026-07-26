# Container image for the NC-Document-Controller hosted agent.
#
# Serves the orchestrator (with its two in-process sub-agents) over the Foundry
# Responses protocol on port 8088, which is the contract expected by
# `az cognitiveservices agent create --protocol responses`.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
# The Agent Framework hosted-agent packages are in preview, so allow
# pre-release versions during resolution.
RUN pip install --pre -r requirements.txt

# Application code. The agents read their instructions from agents/*.md, so the
# whole package (including the markdown files) is copied in.
COPY config.py main.py ./
COPY agents ./agents

# The Foundry Responses protocol contract requires listening on port 8088.
EXPOSE 8088

CMD ["python", "main.py"]

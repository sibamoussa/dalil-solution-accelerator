FROM python:3.13-slim

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG ACCELERATOR_CONFIG=accelerator.json

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

COPY webapp/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY webapp/main.py ./
COPY webapp/retrieval_fusion.py ./
COPY webapp/foundry_retrieval.py ./
COPY webapp/agent_runtime.py webapp/grounded_workflow.py ./
COPY webapp/demo_limits.py ./
COPY webapp/accelerator_config.py webapp/source_manifest.py webapp/conversation_history.py ./
COPY ${ACCELERATOR_CONFIG} ./accelerator.json
COPY sources ./sources
COPY webapp/assets ./assets

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

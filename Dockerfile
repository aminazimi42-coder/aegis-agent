FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

COPY pyproject.toml ./
COPY README.md ./
COPY LICENSE ./
COPY app ./app
COPY agents ./agents
COPY core ./core
COPY docs ./docs
COPY tests ./tests

RUN pip install --upgrade pip && pip install .

EXPOSE 10000

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "10000"]

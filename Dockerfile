FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN useradd -M app

COPY pyproject.toml ./
COPY bot ./bot
RUN pip install .

USER app

CMD ["python", "-m", "bot.main"]

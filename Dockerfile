FROM python:3.12 AS build

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app/

RUN pip install poetry

COPY pyvatti/poetry.lock pyvatti/pyproject.toml ./

RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR

FROM python:3.12-slim-bullseye

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=build ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY pyvatti /app/pyvatti

ADD helmvatti /opt/

WORKDIR /app/

CMD ["uvicorn", "pyvatti.src.pyvatti.main:app", "--host", "0.0.0.0", "--port", "80"]

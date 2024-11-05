
FROM python:3.12-slim-bullseye

ARG TARGETARCH

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app/

RUN pip install poetry

COPY pyvatti/ /app/pyvatti

WORKDIR /app/pyvatti/

RUN poetry install && rm -rf $POETRY_CACHE_DIR

ADD pyvatti/helmvatti /opt/helmvatti

ENV HELM_CHART_PATH=/opt/helmvatti

WORKDIR /tmp

RUN apt-get update \
 && apt-get install -y curl \
 && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" \
 && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
 && curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash \
 && rm /tmp/* \
 && apt-get -y clean

WORKDIR /app/pyvatti

CMD ["poetry", "run", "pyvatti"]

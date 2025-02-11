FROM python:3.12-slim-bullseye as build

ARG TARGETARCH

RUN pip install nox uv 

COPY pyvatti/ /app/pyvatti

WORKDIR /app/pyvatti 

RUN nox -s build

FROM python:3.12-slim-bullseye

COPY --from=build /app/pyvatti/dist/hattivatti-2.1.0-py3-none-any.whl /tmp/

RUN pip install /tmp/hattivatti-2.1.0-py3-none-any.whl

ADD pyvatti/helmvatti /opt/helmvatti

ENV HELM_CHART_PATH=/opt/helmvatti

RUN apt-get update \
 && apt-get install -y curl \
 && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" \
 && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
 && curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash \
 && rm /tmp/* \
 && apt-get -y clean

CMD ["pyvatti"]

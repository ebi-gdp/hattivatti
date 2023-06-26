FROM --platform=linux/amd64 rust:bookworm AS build

WORKDIR /opt/build

COPY . ./

RUN cargo build --target x86_64-unknown-linux-gnu

FROM --platform=linux/amd64 debian:stable-slim

COPY --from=build /opt/build/target/x86_64-unknown-linux-gnu/debug/hattivatti /opt/

RUN apt-get update && apt-get install -y openssl-dev

CMD ["/opt/hattivatti"]
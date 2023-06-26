FROM --platform=linux/amd64 rust:bookworm AS build

WORKDIR /opt/build

COPY . ./

RUN cargo build --target x86_64-unknown-linux-gnu

FROM --platform=linux/amd64 debian:stable-slim

COPY --from=build /opt/build/target/x86_64-unknown-linux-gnu/debug/hattivatti /opt/

CMD ["/opt/hattivatti"]
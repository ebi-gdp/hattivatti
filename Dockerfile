FROM --platform=linux/amd64 rust:buster AS build

WORKDIR /opt/build

COPY . ./

RUN cargo build --target x86_64-unknown-linux-gnu

FROM --platform=linux/amd64 debian:buster-slim

RUN apt-get update && apt-get install -y ca-certificates

COPY --from=build /opt/build/target/x86_64-unknown-linux-gnu/debug/hattivatti /opt/

CMD ["/opt/hattivatti"]
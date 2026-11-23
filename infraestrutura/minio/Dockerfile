FROM golang:1.24.8-bookworm@sha256:4ed690d6649d63c312b99a6120025ec79ce3b542968a37da53d6236c7c61a848 AS construcao
ENV CGO_ENABLED=0 GOAMD64=v1 GOTOOLCHAIN=local
RUN go install -trimpath github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
RUN go install -trimpath github.com/minio/mc@RELEASE.2025-08-13T08-35-41Z
RUN go version -m /go/bin/minio > /go/minio-compilacao.txt && go version -m /go/bin/mc > /go/mc-compilacao.txt

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
RUN useradd --uid 10001 --create-home aplicativo && mkdir /dados && chown aplicativo /dados
COPY --from=construcao /go/bin/minio /usr/local/bin/minio
COPY --from=construcao /go/bin/mc /usr/local/bin/mc
COPY --from=construcao /go/minio-compilacao.txt /go/mc-compilacao.txt /usr/local/share/
USER aplicativo
WORKDIR /home/aplicativo
CMD ["minio", "server", "/dados", "--console-address", ":9001"]

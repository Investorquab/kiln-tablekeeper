# Tablekeeper Stage 1

## Build

    docker build -t tablekeeper-stage1 ./stage-1

## Run

    docker run --rm -p 8080:8080 tablekeeper-stage1

The service listens on 0.0.0.0:${PORT} and defaults to port 8080.

## Health check

    curl http://127.0.0.1:8080/health

Expected:

    {"status":"ok"}

The service is self-contained in the image and requires no outbound network access at runtime.

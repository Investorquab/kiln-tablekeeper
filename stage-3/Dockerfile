FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Debian's tzdata package supplies the full IANA database without runtime network access.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY main.py /app/main.py
EXPOSE 8080
CMD ["python", "/app/main.py"]

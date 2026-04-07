FROM python:3.11-slim as builder

RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/lib -r requirements.txt

FROM gcr.io/distroless/python3-debian12:nonroot-amd64

WORKDIR /app

COPY --from=builder /app/lib /app/lib

COPY bot.py .

ENV PYTHONPATH=/app/lib
ENV PYTHONUNBUFFERED=1

USER 65532

ENTRYPOINT ["/usr/bin/python3", "bot.py"]

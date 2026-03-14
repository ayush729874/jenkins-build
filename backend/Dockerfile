FROM python:3.10-alpine AS builder
WORKDIR /app
RUN apk add --no-cache \
    gcc musl-dev libffi-dev
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --prefix=/install -r requirements.txt

FROM python:3.10-alpine AS runtime
WORKDIR /app
RUN addgroup -S appgroup \
    && adduser -S -G appgroup appuser
COPY --from=builder /install /usr/local
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
HEALTHCHECK --interval=30s --timeout=10s \
    --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; ..."
EXPOSE 8000
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8000"]

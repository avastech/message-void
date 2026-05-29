FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY message_void ./message_void

ENV PYTHONUNBUFFERED=1 \
    MESSAGE_VOID_HOST=0.0.0.0 \
    MESSAGE_VOID_PORT=5000 \
    MESSAGE_VOID_SMTP_HOST=0.0.0.0 \
    MESSAGE_VOID_SMTP_PORT=1025

EXPOSE 5000 1025

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2); sys.exit(0)" || exit 1

CMD ["python", "-m", "message_void"]

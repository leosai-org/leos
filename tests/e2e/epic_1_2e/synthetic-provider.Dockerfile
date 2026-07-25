FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY synthetic_provider.py /app/synthetic_provider.py

USER 65532:65532
EXPOSE 8000
CMD ["python", "/app/synthetic_provider.py"]


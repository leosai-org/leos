FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /test
COPY test_execution_spine_e2e.py /test/test_execution_spine_e2e.py

USER 65532:65532
CMD ["python", "-m", "unittest", "-v", "test_execution_spine_e2e"]


FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

WORKDIR /app
COPY constraints/v2-runtime.txt /opt/leos/constraints/v2-runtime.txt
COPY services/work-coordination-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY contracts /contracts
COPY packages/leos-contracts/src/leos_contracts ./leos_contracts
COPY services/work-coordination-service/app ./app

ENV PYTHONPATH=/app
ENV LEOS_CONTRACT_ROOT=/contracts
ENV LEOS_WORK_COORDINATION_DATA_DIR=/data/work-coordination

EXPOSE 8118
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8118"]

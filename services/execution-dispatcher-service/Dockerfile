FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de
WORKDIR /app
COPY packages/leos-contracts /opt/leos/packages/leos-contracts
COPY contracts /opt/leos/contracts
COPY constraints/v2-runtime.txt /opt/leos/constraints/v2-runtime.txt
COPY services/execution-dispatcher-service/requirements.txt .
ENV PIP_CONSTRAINT=/opt/leos/constraints/v2-runtime.txt
RUN pip install --no-cache-dir /opt/leos/packages/leos-contracts \
    && pip install --no-cache-dir -r requirements.txt
COPY services/execution-dispatcher-service/app ./app
ENV LEOS_CONTRACT_ROOT=/opt/leos/contracts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

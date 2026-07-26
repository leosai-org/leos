FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de
WORKDIR /app
COPY constraints/v2-runtime.txt /opt/leos/constraints/v2-runtime.txt
COPY services/organization-domain-service/requirements.txt .
ENV PIP_CONSTRAINT=/opt/leos/constraints/v2-runtime.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY contracts /contracts
COPY packages/leos-contracts/src/leos_contracts ./leos_contracts
COPY services/organization-domain-service/app ./app
ENV LEOS_CONTRACT_ROOT=/contracts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

WORKDIR /app

COPY packages/leos-contracts /opt/leos/packages/leos-contracts
COPY contracts /opt/leos/contracts
COPY constraints/v2-runtime.txt /opt/leos/constraints/v2-runtime.txt
COPY services/employee-cognitive-service/requirements.txt .
RUN pip install --no-cache-dir \
        -c /opt/leos/constraints/v2-runtime.txt \
        /opt/leos/packages/leos-contracts \
    && pip install --no-cache-dir \
        -c /opt/leos/constraints/v2-runtime.txt \
        -r requirements.txt

COPY services/employee-cognitive-service/app ./app
ENV LEOS_CONTRACT_ROOT=/opt/leos/contracts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

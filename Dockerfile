FROM python:3.11-slim

# Install Clingo
RUN apt-get update && apt-get install -y --no-install-recommends \
    clingo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY reasoner/ ./reasoner/
COPY shared/ ./shared/

RUN mkdir -p /app/reasoner/data

EXPOSE 8000

CMD ["uvicorn", "reasoner.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

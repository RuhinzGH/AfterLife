FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY afterlife/ afterlife/
COPY api/ api/
COPY app_data/ app_data/
COPY models/ models/

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]

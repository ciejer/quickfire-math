FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DB_PATH=/data/quickfiremath.sqlite \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080
# Create a volume mount point. Use /data for persistence.
RUN mkdir -p /data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
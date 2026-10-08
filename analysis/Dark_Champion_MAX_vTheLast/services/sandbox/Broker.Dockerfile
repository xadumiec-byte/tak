FROM library/python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
WORKDIR /app
COPY services/sandbox/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/sandbox/broker.py .
CMD ["uvicorn","broker:app","--host","0.0.0.0","--port","8091"]

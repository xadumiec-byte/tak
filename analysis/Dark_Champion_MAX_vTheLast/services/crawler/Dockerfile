FROM library/python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
WORKDIR /app
RUN pip install --no-cache-dir crawl4ai==0.9.2 fastapi==0.115.6 uvicorn==0.34.0
COPY services/crawler/app.py .
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","11235"]

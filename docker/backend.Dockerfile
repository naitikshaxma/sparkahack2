# Backend Dockerfile for Voice OS Bhaarat
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    tesseract-ocr \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actual application files
COPY backend /app/backend

# Set the Python path to correctly resolve imports
ENV PYTHONPATH=/app

# Expose the API port
EXPOSE 8000

# Start the uvicorn server via app_factory or main
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

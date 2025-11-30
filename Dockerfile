# syntax = docker/dockerfile:1
FROM python:3.11-slim

# Work directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Default command: run the relay
CMD ["python", "relay.py"]
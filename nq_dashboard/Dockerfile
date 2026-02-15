FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy nq_scalper (indicator engine dependency)
COPY ../nq_scalper /app/nq_scalper

# Build frontend
COPY frontend/package.json frontend/
RUN cd frontend && npm install

COPY frontend/ frontend/
RUN cd frontend && npm run build

# Copy backend
COPY backend/ backend/

# Create data directory
RUN mkdir -p backend/data

# Serve frontend static files via FastAPI
ENV PORT=8000

# Start
CMD cd backend && python -m uvicorn app:app --host 0.0.0.0 --port ${PORT}

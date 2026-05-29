# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr (critical for Docker logs)
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies (no cache to keep image small)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Health check — verify the API server is responsive
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')" || exit 1

# Run the API Gateway for 24x7 Hugging Face Deployment
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "7860"]

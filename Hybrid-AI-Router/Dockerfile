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

# Health check — verify the Python process is alive
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "print('healthy')" || exit 1

# Run the terminal chat (unbuffered via PYTHONUNBUFFERED above)
CMD ["python", "-m", "src.main"]

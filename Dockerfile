# =========================================================================
# RIGID SINGLE-STAGE DOCKERFILE
# This version prioritizes a successful build over minimal image size.
# =========================================================================

# Start from the same base image
FROM python:3.12-slim

# Set environment variables for a clean and efficient build/runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UVICORN_WORKERS=1

# Install ALL system dependencies in a single layer.
# 'libgdal-dev' is the development package, which automatically pulls in the
# correct runtime libraries (like libgdal33) as dependencies.
# This avoids any issues with guessing the right runtime package name.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the application's working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-input -r requirements.txt

# Create a non-root user for security
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Copy the rest of the application code
COPY . .

# Change ownership of the entire app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# # Health check to ensure the application is responsive
# HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
#   CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5).raise_for_status()"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
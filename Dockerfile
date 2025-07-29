# =========================================================================
# BUILDER STAGE: To install dependencies
# =========================================================================
# Using a specific version is better for reproducibility. 3.12-slim is based on Debian Bookworm.
FROM python:3.12-slim as builder

# Set environment variables for a clean and efficient build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for building python packages, especially GeoPandas
# libgdal-dev is the development package needed for the build process.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy only the requirements file to leverage Docker layer caching
COPY requirements.txt ./

# Install project dependencies using pip
RUN pip install --no-input -r requirements.txt

# Copy the rest of the application code
COPY . .


# =========================================================================
# PRODUCTION STAGE: The final, lean image
# =========================================================================
FROM python:3.12-slim as production

# Set environment variables for runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Default number of workers, can be overridden at runtime
    UVICORN_WORKERS=1

# Install only runtime system dependencies
# libgdal34 is the runtime library for GDAL on Debian Bookworm (used in python:3.12-slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal34 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy installed packages and application code from the builder stage
# Set ownership to the non-root user at the same time
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder --chown=appuser:appuser /app /app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Health check to ensure the application is responsive.
# This requires 'requests' in requirements.txt.
# HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
#   CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5).raise_for_status()"

# Run the application with graceful shutdown using Uvicorn's worker management.
# The number of workers can be overridden by setting the UVICORN_WORKERS env var.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
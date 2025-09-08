# =========================================================================
# STAGE 1: The "Builder" Stage
# This stage installs all build tools, compiles dependencies, and prepares
# the application. It will be discarded at the end.
# =========================================================================
FROM python:3.12-slim AS builder

# Set environment variables for the build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build-time system dependencies needed to compile Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies. This layer is cached as long as
# requirements.txt doesn't change.
COPY requirements.txt ./
RUN pip install --no-input -r requirements.txt

# Copy the application code into the builder stage
COPY . .

# =========================================================================
# STAGE 2: The "Final" Production Stage
# This stage starts from a clean base and copies ONLY the necessary
# artifacts from the "builder" stage, resulting in a tiny final image.
# =========================================================================
FROM python:3.12-slim

# Set environment variables for runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UVICORN_WORKERS=1

# Install ONLY the required runtime system dependencies.
# 'libgdal33' is the shared library file needed by the Python packages to run.
# It's much smaller than the '-dev' package.
# NOTE: The package name might change (libgdal36) in future Debian versions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal36 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

WORKDIR /app

# Copy the installed Python packages from the builder stage
# This copies the entire 'site-packages' directory where pip installed everything.
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy the application code from the builder stage
COPY --from=builder /app /app

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
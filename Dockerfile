# Stage 1: Builder
FROM python:3.10 as builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install pip-tools to compile dependency lock file
RUN pip install --upgrade pip uv pip-tools

COPY requirements.in .
RUN pip-compile requirements.in -o requirements.txt


# Stage 2: Final image
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for building some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Copy the compiled requirements from builder stage
COPY --from=builder /app/requirements.txt .

# Install Python dependencies and verify installation by listing installed packages
RUN pip install --no-cache-dir -r requirements.txt && pip list

# Copy application source code after installing dependencies to leverage Docker layer caching
COPY . .

# Change ownership and switch to the non-root user
RUN chown -R appuser:appuser /home/appuser/app
USER appuser

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

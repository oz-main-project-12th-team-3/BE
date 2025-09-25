# Stage 1: Builder
FROM python:3.10 as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install build tools globally in the builder
RUN pip install uv pip-tools

# Compile requirements to a lock file 체크 필요
WORKDIR /app
COPY requirements.in .
RUN pip-compile requirements.in -o requirements.txt




# Stage 2: Final image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


# Create a non-root user
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Copy the virtual environment from the builder stage


# Copy dependency list and install dependencies
COPY --from=builder /app/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Change ownership of the app directory and switch to the non-root user
RUN chown -R appuser:appuser /home/appuser/app
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Default command
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

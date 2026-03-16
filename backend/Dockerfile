# Use a minimal Python 3.12 image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for PyMuPDF, Pillow, etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    libfreetype6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (astral)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into the system python using uv
RUN uv pip install --system -r pyproject.toml

# Copy the rest of the application code
COPY . .

# Set a default port fallback, but allow Cloud Run to override it
ENV PORT=8000
EXPOSE $PORT

# Command to run the application using the dynamic port
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
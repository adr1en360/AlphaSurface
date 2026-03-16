FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Copy only the files needed for dependency resolution first
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself yet)
RUN uv sync --frozen --no-install-project

# Copy the rest of the application code
COPY . .

# Install the project and its dependencies again to make sure everything is installed
RUN uv sync --frozen

# Expose the port that the application listens on.
EXPOSE 8000

# Set the command to run the application using `uv run`.
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

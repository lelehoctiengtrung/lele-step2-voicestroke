FROM python:3.12-slim

# Install system dependencies, git, and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install google-colab-cli and other dependencies
RUN pip install --no-cache-dir \
    google-colab-cli \
    requests

# Set working directory matching Docker mounts
WORKDIR /app

# Copy files
COPY . /app

# Run the Colab runner script
CMD ["python3", "VPS_Steps/run_step2_colab.py"]

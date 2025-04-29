# syntax=docker/dockerfile:1

# Build stage
FROM python:3.12.5-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    cmake \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Download NLTK data
RUN python -m nltk.downloader -d /usr/local/share/nltk_data punkt averaged_perceptron_tagger

# Production stage
FROM python:3.12.5-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libmagic1 \
    tesseract-ocr \
    postgresql-client \
    poppler-utils \
    gcc \
    g++ \
    cmake \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /root/.local/bin /usr/local/bin
# Copy NLTK data from builder
COPY --from=builder /usr/local/share/nltk_data /usr/local/share/nltk_data

# Create necessary directories
RUN mkdir -p storage logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PATH="/usr/local/bin:$PATH"

# Create default configuration
RUN echo '[api]\n\
host = "0.0.0.0"\n\
port = 8000\n\
reload = false\n\
\n\
[auth]\n\
jwt_algorithm = "HS256"\n\
dev_mode = true\n\
dev_entity_id = "dev_user"\n\
dev_entity_type = "developer"\n\
dev_permissions = ["read", "write", "admin"]\n\
\n\
[completion]\n\
provider = "ollama"\n\
model_name = "llama2"\n\
base_url = "http://localhost:11434"\n\
\n\
[database]\n\
provider = "postgres"\n\
\n\
[embedding]\n\
provider = "ollama"\n\
model_name = "nomic-embed-text"\n\
dimensions = 768\n\
similarity_metric = "cosine"\n\
base_url = "http://localhost:11434"\n\
\n\
[parser]\n\
chunk_size = 1000\n\
chunk_overlap = 200\n\
use_unstructured_api = false\n\
\n\
[reranker]\n\
use_reranker = false\n\
\n\
[redis]\n\
host = "redis"\n\
port = 6379\n\
\n\
[storage]\n\
provider = "local"\n\
storage_path = "/app/storage"\n\
\n\
[vector_store]\n\
provider = "pgvector"\n\
' > /app/morphik.toml.default

# Create startup script
RUN <<'EOF' cat > /app/docker-entrypoint.sh
#!/bin/bash
set -e

# Copy default config if none exists
if [ ! -f /app/morphik.toml ]; then
    cp /app/morphik.toml.default /app/morphik.toml
fi

# Function to check PostgreSQL
check_postgres() {
    if [ -n "$POSTGRES_URI" ]; then
        echo "Waiting for PostgreSQL..."
        max_retries=30
        retries=0
        # Extract database credentials from POSTGRES_URI
        DB_USER=$(echo $POSTGRES_URI | sed -n "s/.*:\/\/\([^:]*\):.*/\1/p")
        DB_NAME=$(echo $POSTGRES_URI | sed -n "s/.*@[^\/]*\/\([^?]*\).*/\1/p")
        until PGPASSWORD=$PGPASSWORD pg_isready -h postgres -U $DB_USER -d $DB_NAME; do
            retries=$((retries + 1))
            if [ $retries -eq $max_retries ]; then
                echo "Error: PostgreSQL did not become ready in time"
                exit 1
            fi
            echo "Waiting for PostgreSQL... (Attempt $retries/$max_retries)"
            sleep 2
        done
        echo "PostgreSQL is ready!"
        
        # Verify database connection
        if ! PGPASSWORD=$PGPASSWORD psql -h postgres -U $DB_USER -d $DB_NAME -c "SELECT 1" > /dev/null 2>&1; then
            echo "Error: Could not connect to PostgreSQL database"
            exit 1
        fi
        echo "PostgreSQL connection verified!"
    fi
}

# Check PostgreSQL
check_postgres

# Check if command arguments were passed ($# is the number of arguments)
if [ $# -gt 0 ]; then
    # If arguments exist, execute them (e.g., execute "arq core.workers...")
    exec "$@"
else
    # Otherwise, execute the default command (Uvicorn for the API)
    exec uvicorn core.api:app --host $HOST --port $PORT --loop asyncio --http auto --ws auto --lifespan auto
fi
EOF

RUN chmod +x /app/docker-entrypoint.sh

# Copy application code
COPY core ./core
COPY README.md LICENSE ./

# Labels for the image
LABEL org.opencontainers.image.title="Morphik Core"
LABEL org.opencontainers.image.description="Morphik Core - A powerful document processing and retrieval system"
LABEL org.opencontainers.image.source="https://github.com/yourusername/morphik"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.licenses="MIT"

# Expose port
EXPOSE 8000

# Set the entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

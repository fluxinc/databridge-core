FROM postgres:17.4-alpine

# Install build dependencies
RUN apk add --no-cache \
    git \
    build-base \
    clang \
    llvm \
    postgresql17-dev

# Clone and build pgvector
RUN git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make OPTFLAGS="" \
    && make install

# Cleanup
RUN apk del git build-base clang llvm postgresql17-dev \
    && rm -rf /pgvector 

# Accept build argument for dump file
ARG DUMP_FILE

# Create initialization script that will restore the dump if DUMP_FILE is provided
RUN if [ -n "$DUMP_FILE" ]; then \
    echo '#!/bin/bash' > /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'set -e' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '# Wait for PostgreSQL to start' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'until pg_isready -U $POSTGRES_USER; do' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  echo "Waiting for PostgreSQL to start..."' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  sleep 1' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'done' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'echo "Restoring database from dump..."' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo "pg_restore -U \$POSTGRES_USER -d \$POSTGRES_DB --clean --if-exists --no-owner /$DUMP_FILE" >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'echo "Database restore completed."' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    chmod +x /docker-entrypoint-initdb.d/10-restore-dump.sh; \
    fi

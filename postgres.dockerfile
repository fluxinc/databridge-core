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
    echo 'if [ -f "/$DUMP_FILE" ]; then' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  echo "Restoring database from dump..."' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo "  pg_restore -U \$POSTGRES_USER -d \$POSTGRES_DB --clean --if-exists --no-owner /$DUMP_FILE" >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  echo "Database restore completed."' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  touch /tmp/restore_completed' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  echo "Restore completed signal file created."' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'else' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo '  echo "Dump file /$DUMP_FILE not found, skipping restore"' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    echo 'fi' >> /docker-entrypoint-initdb.d/10-restore-dump.sh && \
    chmod +x /docker-entrypoint-initdb.d/10-restore-dump.sh; \
    fi

RUN echo 'touch /var/run/restore_completed' >> /docker-entrypoint-initdb.d/11-mark-restore-completed.sh && \
    echo 'echo "Restore completed signal file created."' >> /docker-entrypoint-initdb.d/11-mark-restore-completed.sh && \
    chmod +x /docker-entrypoint-initdb.d/11-mark-restore-completed.sh;

# Create simple database check script
RUN echo '#!/bin/bash' > /usr/local/bin/check-db.sh && \
    echo 'until pg_isready -U "${POSTGRES_USER:-postgres}" > /dev/null 2>&1; do sleep 1; done' >> /usr/local/bin/check-db.sh && \
    echo 'DB_EXISTS=$(psql -U "${POSTGRES_USER:-postgres}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='\''${POSTGRES_DB:-postgres}'\''" 2>/dev/null || echo "")' >> /usr/local/bin/check-db.sh && \
    echo 'if [ "$DB_EXISTS" = "1" ]; then touch /var/run/restore_completed; echo "Database exists - marker created"; fi' >> /usr/local/bin/check-db.sh && \
    chmod +x /usr/local/bin/check-db.sh

CMD ["sh", "-c", "/usr/local/bin/check-db.sh & exec docker-entrypoint.sh postgres"]

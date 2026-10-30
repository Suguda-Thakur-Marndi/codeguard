# Hardened, isolated Execution Sandbox for CodeGuard
FROM python:3.11-slim

# Security: run as non-root user
RUN groupadd -g 1000 sandboxuser && \
    useradd -u 1000 -g sandboxuser -m -s /bin/bash sandboxuser

# Install minimal testing dependencies only
RUN pip install --no-cache-dir pytest pytest-asyncio

WORKDIR /workspace
RUN chown -R sandboxuser:sandboxuser /workspace

USER sandboxuser

# Default entrypoint
CMD ["pytest"]

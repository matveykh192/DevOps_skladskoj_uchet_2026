# Reproducible build: pinned base image (rule: forbid latest tag)
FROM python:3.11.9-slim

# Prevent python from writing bytecode and enable unbuffered logging for container output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Non-root user: create dedicated group and user (rule: forbid root execution)
RUN groupadd -r -g 10001 appuser && \
    useradd -r -u 10001 -g appuser -d /code -s /sbin/nologin appuser

# Dependencies layer (cached if requirements don't change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source code
COPY app ./app
COPY frontend ./frontend
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Ensure proper non-root permissions
RUN chown -R appuser:appuser /code

# Switch to non-privileged user
USER appuser

# Document exposed internal port
EXPOSE 8000

# Graceful termination signal handling
STOPSIGNAL SIGTERM

# Healthcheck to verify application and database readiness
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Exec form ensures uvicorn receives SIGTERM directly for graceful shutdown
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

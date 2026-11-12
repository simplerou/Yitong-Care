FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY validation_service ./validation_service
COPY scripts ./scripts
COPY evaluations ./evaluations
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir .
EXPOSE 8000 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

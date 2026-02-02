FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker.justfile /app/justfile


RUN chown -R appuser:appuser /app

USER appuser

CMD ["just", "run-server"]
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

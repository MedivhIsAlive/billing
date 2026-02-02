default:
    @just --justfile /app/app.justfile --list

run-server:
    python manage.py runserver 0.0.0.0:8000

migrate:
    python manage.py migrate

test:
    python manage.py test

# Wait for DB (useful for entrypoints)
wait-for-db:
    while ! nc -z db 5432; do sleep 1; done;

worker-start:
    celery -A billing worker --loglevel=info

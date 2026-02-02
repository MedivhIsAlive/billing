default:
    @just --list

compose-up:
    docker compose up -d

compose-up-build:
    docker compose up -d --build

compose-down:
    docker compose down

migrate:
    docker compose exec web python manage.py migrate

test:
    docker compose exec web python manage.py test

prune-docker:
    docker system prune -f

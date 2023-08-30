git submodule update --init --recursive
COMPOSE_PROFILES=backend DOCKER_BUILDKIT=1 docker-compose -f docker-compose.dev.yaml up --build
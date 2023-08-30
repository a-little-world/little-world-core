git submodule update --init --recursive
COMPOSE_PROFILES=all DOCKER_BUILDKIT=1 docker-compose -f docker-compose.dev.yaml build
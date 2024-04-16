git submodule update --init --recursive
for frontend in main_frontend admin_panel_frontend cookie_banner_frontend; do touch ./front/$frontend.webpack-stats.json ; done
COMPOSE_PROFILES=all DOCKER_BUILDKIT=1 docker-compose -f docker-compose.dev.yaml build
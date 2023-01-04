# This is the general entry point for server startup ( dev )
# TODO: in the future these procesees should be deomonized or handled by supervisord
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"
celery -A back worker --loglevel=info &
single-beat celery -A back beat --loglevel=info &
uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
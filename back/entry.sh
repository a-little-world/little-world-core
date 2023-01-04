# This is the general entry point for server startup ( dev )
# TODO: in the future these procesees should be deomonized or handled by supervisord
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"
celery -A back worker --loglevel=info &
if [ "$BUILD_TYPE" = "deployment" ]; then
    SINGLE_BEAT_REDIS_SERVER="rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:$DJ_REDIS_PORT" single-beat celery -A back beat --loglevel=info &
else
    #SINGLE_BEAT_REDIS_SERVER='redis://host.docker.internal:6379' single-beat celery -A back beat --loglevel=info &
    celery -A back beat --loglevel=info &
fi
uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
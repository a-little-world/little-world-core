# This is the general entry point for server startup ( dev )
# TODO: in the future these procesees should be deomonized or handled by supervisord
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"
celery -A back worker --loglevel=info &
if [ "$BUILD_TYPE" = "deployment" ]; then
    SINGLE_BEAT_REDIS_SERVER="rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:$DJ_REDIS_PORT" single-beat celery -A back beat --loglevel=info &
elif [ "$BUILD_TYPE" = "staging" ]; then
    SINGLE_BEAT_REDIS_SERVER="rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:$DJ_REDIS_PORT" single-beat celery -A back beat --loglevel=info &
else
    celery -A back beat --loglevel=info &
fi

if [ "$BUILD_TYPE" = "deployment" ]; then
    python3 manage.py migrate --noinput
fi

uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
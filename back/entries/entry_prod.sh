# This is the general entry point for server startup ( dev )
# TODO: in the future these procesees should be deomonized or handled by supervisord
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"

if [ "$USE_LECACY_CONFIG" = "false" ]; then
if [ "$START_UVICORN" = "true" ]; then
    AMNT_WORKERS=${UVICORN_WORKERS:-1}
    python3 manage.py shell --command 'from management.controller import create_base_admin_and_add_standart_db_values; create_base_admin_and_add_standart_db_values()'
    uvicorn back.asgi:application --port 8000 --host 0.0.0.0 --workers $AMNT_WORKERS
fi

if [ "$START_CELERY_WORKER" = "true" ]; then
    celery -A back worker --loglevel=info
fi

if [ "$START_CELERY_BEAT" = "true" ]; then
    celery -A back beat --loglevel=info
fi

if [ "$START_CELERY_SINGLE_BEAT" = "true" ]; then
    SINGLE_BEAT_REDIS_SERVER="$FULL_ACCESS_REDIS_URL" single-beat celery -A back beat --loglevel=info
fi
else
# The legacy way to configure the helm chart ================
if [ "$SAFEMODE" = "true" ]; then
uvicorn back.asgi:application --port 8000 --host 0.0.0.0
else

celery -A back worker --loglevel=info &

if [ "$BUILD_TYPE" = "deployment" ]; then
    SINGLE_BEAT_REDIS_SERVER="$FULL_ACCESS_REDIS_URL" single-beat celery -A back beat --loglevel=info &
else
    celery -A back beat --loglevel=info &
fi

python3 manage.py shell --command 'from management.controller import create_base_admin_and_add_standart_db_values; create_base_admin_and_add_standart_db_values()'

uvicorn back.asgi:application --port 8000 --host 0.0.0.0
fi # End of legacy way to configure the helm chart ================
fi

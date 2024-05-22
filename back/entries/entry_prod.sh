# This is the general entry point for server startup ( dev )
# TODO: in the future these procesees should be deomonized or handled by supervisord
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"

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
fi
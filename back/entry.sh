# This is the general entry point for server startup ( dev )
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"

celery -A back worker --loglevel=info &
if [ "$BUILD_TYPE" = "deployment" ]; then
    SINGLE_BEAT_REDIS_SERVER="$FULL_ACCESS_REDIS_URL" single-beat celery -A back beat --loglevel=info &
elif [ "$BUILD_TYPE" = "staging" ]; then
    SINGLE_BEAT_REDIS_SERVER="$FULL_ACCESS_REDIS_URL" single-beat celery -A back beat --loglevel=info &
else
    celery -A back beat --loglevel=info &
fi

if [ "$BUILD_TYPE" = "deployment" ]; then
    python3 manage.py migrate --noinput
fi

if [ "$DJ_USE_AUTO_RELOAD" = "1" ]; then
    python3 /back/tbs_django_auto_reload/update_watcher.py &
fi

if [ "$EMPHIRIAL" = "1" ]; then
    python3 manage.py migrate --noinput
    python3 manage.py collectstatic --noinput
    python3 manage.py add_questions
    python3 manage.py shell --command 'from management.controller import create_base_admin_and_add_standart_db_values; create_base_admin_and_add_standart_db_values()'
    python3 manage.py shell --command 'from management.random_test_users import create_abunch_of_users; create_abunch_of_users()'
fi

uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
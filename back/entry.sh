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

if [ "$EMPHIRIAL" = "1" ]; then
    python3 manage.py migrate --noinput
    python3 manage.py collectstatic --noinput
    # python3 manage.py makemessages -a Only if new translations where added
    # python3 manage.py makemessages -a --ignore "emails/*" <-- ignore emails, we don't jet offerr translations for them
    python3 manage.py add_tag_translations
    python3 manage.py add_questions
    python3 manage.py compilemessages --use-fuzzy
    python3 manage.py shell --command 'from management.controller import create_base_admin_and_add_standart_db_values; create_base_admin_and_add_standart_db_values()'
    python3 manage.py shell --command 'from management.random_test_users import create_abunch_of_users; create_abunch_of_users()'
fi

uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
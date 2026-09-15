# This is the general entry point for server startup ( dev )
# "rediss://:$DJ_REDIS_PASSWORD@$DJ_REDIS_HOST:DJ_REDIS_PORT"

if [ "$BUILD_TYPE" = "production" ]; then
    START_CELERY_WORKER="${START_CELERY_WORKER:-true}"
    START_CELERY_BEAT="${START_CELERY_BEAT:-false}"
    START_CELERY_SINGLE_BEAT="${START_CELERY_SINGLE_BEAT:-true}"
    RUN_MIGRATIONS_ON_CONTAINER_START="${RUN_MIGRATIONS_ON_CONTAINER_START:-true}"
else
    START_CELERY_WORKER="${START_CELERY_WORKER:-true}"
    START_CELERY_BEAT="${START_CELERY_BEAT:-true}"
    START_CELERY_SINGLE_BEAT="${START_CELERY_SINGLE_BEAT:-false}"
    RUN_MIGRATIONS_ON_CONTAINER_START="${RUN_MIGRATIONS_ON_CONTAINER_START:-false}"
fi

if [ "$START_CELERY_WORKER" = "true" ]; then
    if [ "$BUILD_TYPE" = "development" ] && [ "$DJ_USE_AUTO_RELOAD" = "1" ]; then
        # Owns the Celery worker and restarts it when /back/**/*.py changes.
        python3 /back/entries/celery_worker_reloader.py &
    else
        celery -A back worker --loglevel=info &
    fi
fi

if [ "$START_CELERY_SINGLE_BEAT" = "true" ]; then
    SINGLE_BEAT_REDIS_SERVER="$FULL_ACCESS_REDIS_URL" single-beat celery -A back beat --loglevel=info &
elif [ "$START_CELERY_BEAT" = "true" ]; then
    celery -A back beat --loglevel=info &
fi

if [ "$RUN_MIGRATIONS_ON_CONTAINER_START" = "true" ]; then
    python3 manage.py migrate --noinput || exit $?
fi

if [ "$DJ_USE_AUTO_RELOAD" = "1" ]; then
    python3 /usr/local/lib/python3.13/site-packages/django_simple_reload/update_watcher.py &
fi

if [ "$EMPHIRIAL" = "1" ]; then
    python3 manage.py migrate --noinput || exit $?
    python3 manage.py collectstatic --noinput
    python3 manage.py add_questions
    python3 manage.py shell --command 'from management.controller import create_base_admin_and_add_standart_db_values; create_base_admin_and_add_standart_db_values()'
    python3 manage.py shell --command 'from management.self_onboarding_seed import create_self_onboarding_course; create_self_onboarding_course()'
    python3 manage.py shell --command 'from management.random_test_users import create_abunch_of_users; create_abunch_of_users()'
fi

# Ensure management permissions and base support account permissions at startup.
python3 manage.py shell --command 'from django.apps import apps; from django.contrib.auth.management import create_permissions; app_config = apps.get_app_config("management"); create_permissions(app_config, verbosity=0); from management.controller import get_base_management_user; get_base_management_user()'


if [ "$BUILD_TYPE" = "development" ]; then
    if [ "$DJ_DEBUG" = "1" ]; then
        python3 -Xfrozen_modules=off -m debugpy --listen 0.0.0.0:5678 -m uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
    else
        uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0
    fi
else
    uvicorn back.asgi:application --port 8000 --host 0.0.0.0
fi

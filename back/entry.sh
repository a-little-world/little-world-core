# This is the general entry point for server startup ( dev )
# TODO: in the future these procesees should be deomonized or handled by supervisord
celery -A back worker --loglevel=info &
celery -A back beat --loglevel=info &
uvicorn back.asgi:application --port 8000 --host 0.0.0.0
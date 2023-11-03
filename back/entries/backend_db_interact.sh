# This entry script is meant for connecting to the live backend from a local deployment
# Therefore this should never run any migrations! Or collect statics etc...

uvicorn back.asgi:application --reload --port 8000 --host 0.0.0.0

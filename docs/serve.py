"""
Supersimple flask whitenoise setup to server html docs
"""
from flask import Flask
from whitenoise import WhiteNoise
from gevent.pywsgi import WSGIServer

app = Flask(__name__)
app.wsgi_app = WhiteNoise(
    app.wsgi_app,
    index_file=True,
)
my_static_folders = (
    "docs/",
)
for static in my_static_folders:
    app.wsgi_app.add_files(static)


http_server = WSGIServer(('', 8000), app)
http_server.serve_forever()

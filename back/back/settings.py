import os

# This can be used to exclude apps or middleware
BUILD_TYPE = os.environ["BUILD_TYPE"]
assert BUILD_TYPE in ['deployment', 'staging', 'development']

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = os.environ['DJ_SECRET_KEY']
DEBUG = os.environ["DJ_DEBUG"].lower() in ('true', '1', 't')
ALLOWED_HOSTS = os.environ.get("DJ_ALLOWED_HOSTS", "").split(",")
FRONTENDS = os.environ["FR_FRONTENDS"].split(",")

"""
Own applications:
management: for user management and general api usage
"""

INSTALLED_APPS = [
    'management',
    'corsheaders',
    'rest_framework',
    *([  # API docs not required in deployment
        'drf_spectacular',  # for api shema generation
        'drf_spectacular_sidecar'  # statics for redoc and swagger
    ] if BUILD_TYPE in ['staging', 'development'] else []),
    'webpack_loader',  # Load bundled webpack files, check `./run.py front`
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]
print(f'Installed apps:\n' + '\n- '.join(INSTALLED_APPS))

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    *([  # Whitenoise to server static only needed in staging or development
        'whitenoise.middleware.WhiteNoiseMiddleware',
    ] if BUILD_TYPE in ['staging', 'development'] else []),
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'back.urls'

CORS_ALLOWED_ORIGINS = []
if BUILD_TYPE == 'staging':
    CORS_ALLOWED_ORIGINS = [
        'https://django-clean-slate-staging.herokuapp.com',  # For staging heroku page
    ]

if BUILD_TYPE == 'staging':
    CSRF_TRUSTED_ORIGINS = [
        'https://django-clean-slate-staging.herokuapp.com',  # For staging heroku page
    ]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, "template/")
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

STATIC_URL = 'static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'static/')

STATICFILES_DIRS = [
    # TODO: add static filed from other apps?
]


WSGI_APPLICATION = "back.wsgi.application"
ASGI_APPLICATION = "back.asgi.application"

CELERY_TIMEZONE = os.environ['DJ_CELERY_TIMEZONE']
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60


if BUILD_TYPE in ['staging', 'development']:
    # autmaticly renders index.html when entering an absolute static path
    WHITENOISE_INDEX_FILE = True

if BUILD_TYPE in ['staging', 'development']:

    REST_FRAMEWORK = {
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    }

    SPECTACULAR_SETTINGS = {
        'TITLE': 'API DOC django clean clate',
        'DESCRIPTION': 'Django Clean Slate by tbscode',
        'VERSION': '1.0.0',
        'SERVE_INCLUDE_SCHEMA': False,
        # The following are for using
        'SWAGGER_UI_DIST': 'SIDECAR',
        'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
        'REDOC_DIST': 'SIDECAR',
        "SWAGGER_UI_SETTINGS": {
            "deepLinking": True,
            "persistAuthorization": True,
            "displayOperationId": True,
        },
    }

"""
Development database is simply sq-lite, 
it is not recommendet to store this database, rather you should load a fixture
via:
`./run.py dump` uses `manage.py dumpdata`
"""
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
} if BUILD_TYPE in ['staging', 'development'] else {
    # TODO: production DB setup
}

AUTH_PASSWORD_VALIDATORS = [{'NAME': val} for val in [
    'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    'django.contrib.auth.password_validation.MinimumLengthValidator',
    'django.contrib.auth.password_validation.CommonPasswordValidator',
    'django.contrib.auth.password_validation.NumericPasswordValidator',
]]

"""
For loading webpack static files
- in development this assumes the frontend folder is mounted at `/front` (inside the container)
- in production we instead copy the `./front` files to `/front`
"""
WEBPACK_LOADER = {app: {  # Configure seperate loaders for every app!
    'CACHE': not DEBUG,
    'STATS_FILE': f"/front/{app}.webpack-stats.json",
    'BUNDLE_DIR_NAME': f"/front/dist/{app}",  # TODO: is this required?
    'POLL_INTERVAL': 0.1,
    'IGNORE': [r'.+\.hot-update.js', r'.+\.map'],
} for app in FRONTENDS}

LANGUAGE_CODE = os.environ.get('DJ_LANGUAGE_CODE', 'en-us')
TIME_ZONE = os.environ.get('DJ_TIME_ZONE', 'UTC')
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'

if DEBUG:
    info = '\n '.join([f'{n}: {globals()[n]}' for n in [
        'BASE_DIR', 'SECRET_KEY', 'ALLOWED_HOSTS', 'CELERY_TIMEZONE', 'FRONTENDS']])
    print(f"configured django settings:\n {info}")

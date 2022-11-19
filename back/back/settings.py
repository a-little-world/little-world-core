from django.utils.translation import gettext as _
import os

# This can be used to exclude apps or middleware
BUILD_TYPE = os.environ["BUILD_TYPE"]
assert BUILD_TYPE in ['deployment', 'staging', 'development']

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = os.environ['DJ_SECRET_KEY']
DEBUG = os.environ["DJ_DEBUG"].lower() in ('true', '1', 't')
BASE_URL = os.environ.get("DJ_BASE_URL", "http://localhost:8000")
ALLOWED_HOSTS = os.environ.get("DJ_ALLOWED_HOSTS", "").split(",")
FRONTENDS = os.environ["FR_FRONTENDS"].split(",")
MANAGEMENT_USER_MAIL = os.environ["DJ_MANAGEMENT_USER_MAIL"]
ADMIN_OPEN_KEYPHRASE = os.environ["DJ_ADMIN_OPEN_KEYPHRASE"]

"""
Own applications:
management: for user management and general api usage
"""

INSTALLED_APPS = [
    'tracking',  # Our user / action / event tracking
    'emails',  # Manageing logging and sending emails
    'cookie_consent',  # Our cookie consent management system

    'management',  # Main backend application

    # TODO: inclusing here can be cleaned up:
    'chat.django_private_chat2.apps.DjangoPrivateChat2Config',  # Our chat

    'corsheaders',
    'rest_framework',
    # A convenient multiselect field for db objects ( used e.g.: in profile.interests )
    'multiselectfield',
    'phonenumber_field',  # Conevnient handler for phone numbers with admin prefix
    'django_rest_passwordreset',  # TODO: could also be used for MFA via email

    'jazzmin',  # The waaaaaay nicer admin interface

    # API docs not required in deployment, so we disable to routes
    # Though we keep the backages so we don't have to split the code
    'drf_spectacular',  # for api shema generation
    'drf_spectacular_sidecar',  # statics for redoc and swagger

    *(['django_spaghetti'] if BUILD_TYPE in ['staging', 'development'] else []),

    'webpack_loader',  # Load bundled webpack files, check `./run.py front`
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]
print(f'Installed apps:\n' + '\n- '.join(INSTALLED_APPS))

if BUILD_TYPE in ['staging', 'development']:
    SPAGHETTI_SAUCE = {
        'apps': ['auth', 'management', 'tracking', 'emails'],
        'show_fields': False,
        'exclude': {'auth': ['user']},
    }


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    *([  # Whitenoise to server static only needed in staging or development
        'whitenoise.middleware.WhiteNoiseMiddleware',
    ] if BUILD_TYPE in ['staging', 'development'] else []),
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'management.middleware.AdminPathBlockingMiddleware',
    'tracking.middleware.TrackRequestsMiddleware',
]

MIDDLEWARE_CLASSES = [
    'corsheaders.middleware.CorsMiddleware',
    "cookie_consent.middleware.CleanCookiesMiddleware",
]

COOKIE_CONSENT_ENABLED = True

ROOT_URLCONF = 'back.urls'
"""
We overwirte the default user model, and add an 'hash' parmameter
"""
AUTH_USER_MODEL = 'management.User'

CORS_ALLOWED_ORIGINS = []
if BUILD_TYPE == 'staging':
    CORS_ALLOWED_ORIGINS = [
        # TODO: setup
    ]

if BUILD_TYPE == 'staging':
    CSRF_TRUSTED_ORIGINS = [
        # TODO: setup
    ]


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, "template/"),
            os.path.join(BASE_DIR, "management/template/"),
            os.path.join(BASE_DIR, "emails/template/")
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

# TODO: following adjust for production
STATIC_URL = 'static/'
MEDIA_URL = '/media/'

STATIC_ROOT = os.path.join(BASE_DIR, 'static/')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'emails/static/')
]

USE_I18N = True
def ugettext(s): return s


LANGUAGES = [
    ('en', ugettext('English')),
    ('de', ugettext('German'))
]
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'management/locale/')
]

WSGI_APPLICATION = "back.wsgi.application"
ASGI_APPLICATION = "back.asgi.application"

CELERY_TIMEZONE = os.environ['DJ_CELERY_TIMEZONE']
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# django-rest-password reset config:
# Password reset tokens are only valid for 1h!
DJANGO_REST_MULTITOKENAUTH_RESET_TOKEN_EXPIRY_TIME = 1
DJANGO_REST_PASSWORDRESET_NO_INFORMATION_LEAKAGE = True
DJANGO_REST_MULTITOKENAUTH_REQUIRE_USABLE_PASSWORD = False


if BUILD_TYPE in ['staging', 'development']:
    # autmaticly renders index.html when entering an absolute static path
    WHITENOISE_INDEX_FILE = True


# We enforce these authentication classes
# By that we force a crsf token to be present on **every** POST request
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ]
}

if BUILD_TYPE in ['staging', 'development']:

    # pylint doesn't like it not sure why
    REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS'] = 'drf_spectacular.openapi.AutoSchema'

    SPECTACULAR_SETTINGS = {
        'TITLE': 'Little Worlds Api Documentation',
        'DESCRIPTION': 'by tbscode',
        'VERSION': '1.0.0',
        'SERVE_INCLUDE_SCHEMA': False,
        # The following are for using sidecar
        'SWAGGER_UI_DIST': 'SIDECAR',
        'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
        'REDOC_DIST': 'SIDECAR',
        "SWAGGER_UI_SETTINGS": {
            "deepLinking": True,
            "persistAuthorization": True,
            "displayOperationId": True,
        },
    }

if BUILD_TYPE in ['staging', 'development']:
    # TODO: actually for staging we should use in Memory channel layer or install redis in the container
    host_ip_from_inside_container = "host.docker.internal"
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [(host_ip_from_inside_container, 6379)],
            },
        }
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

JAZZMIN_SETTINGS = {
    "site_title": "Little World Admin",
    "site_header": "Admin Little World",
    "site_brand": "LW",
    "site_logo": "img/email/footer_logo_w_text.png",
    "login_logo": None,
    "login_logo_dark": None,
    "site_logo_classes": "img-circle",
    "site_icon": None,
    "welcome_sign": "Waddup greetings fellow admin :)",
    "copyright": "Tim Schupp, A Little World gUG",
    "search_model": ["auth.User", "auth.Group"],
    # Field name on user model that contains avatar ImageField/URLField/Charfield or a callable that receives the user
    "user_avatar": None,
    "topmenu_links": [
        {"name": "Home",  "url": "/app",
            "permissions": ["auth.view_user"]},

        {"name": "Repo", "url": "https://github.com/a-little-world/little-world-backend",
            "new_window": True},

        {"name": "Docs", "url": "/static/docs",
            "new_window": True},

        {"name": "API", "url": "/api/schema/swagger-ui/",
            "new_window": True},

        {"name": "Emails", "url": "/emails/welcome",
            "new_window": True},

        {"event": "tracking"},
    ],
    "usermenu_links": [
        {"name": "AdminChat", "url": "https://github.com/farridav/django-jazzmin/issues",
            "new_window": True},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "custom_links": {
        # "books": [{ # This will come in handy TODO
        #    "name": "Make Messages",
        #    "url": "make_messages",
        #    "icon": "fas fa-comments",
        #    "permissions": ["books.view_book"]
        # }]
    },

    # Custom icons for side menu apps/models See https://fontawesome.com/icons?d=gallery&m=free&v=5.0.0,5.0.1,5.0.10,5.0.11,5.0.12,5.0.13,5.0.2,5.0.3,5.0.4,5.0.5,5.0.6,5.0.7,5.0.8,5.0.9,5.1.0,5.1.1,5.2.0,5.3.0,5.3.1,5.4.0,5.4.1,5.4.2,5.13.0,5.12.0,5.11.2,5.11.1,5.10.0,5.9.0,5.8.2,5.8.1,5.7.2,5.7.1,5.7.0,5.6.3,5.5.0,5.4.2
    # for the full list of 5.13.0 free icon classes
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
    },
    # Icons that are used when one is not manually specified
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": False,
    "custom_css": None,
    # I'm pretty sure we can just load react avatar js here and render profile images / avatars
    "custom_js": None,
    # Whether to link font from fonts.googleapis.com (use custom_css to supply font otherwise)
    "use_google_fonts_cdn": True,  # TODO: we don't want his
    "show_ui_builder": False,
}

from channels_redis.core import RedisChannelLayer
from django.utils.translation import gettext_lazy as _
import os

# This can be used to exclude apps or middleware
BUILD_TYPE = os.environ["BUILD_TYPE"]
assert BUILD_TYPE in ['deployment', 'staging', 'development']

IS_DEV = BUILD_TYPE == 'development'
IS_STAGE = BUILD_TYPE == 'staging'
IS_PROD = BUILD_TYPE == 'deployment'

DOCS_BUILD = os.environ.get(
    "DJ_DOCS_BUILD", "false").lower() in ('true', '1', 't')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = os.environ['DJ_SECRET_KEY']
DEBUG = os.environ["DJ_DEBUG"].lower() in ('true', '1', 't')
BASE_URL = os.environ.get("DJ_BASE_URL", "http://localhost:8000")
ALLOWED_HOSTS = os.environ.get("DJ_ALLOWED_HOSTS", "").split(",")
FRONTENDS = os.environ["FR_FRONTENDS"].split(",")
MANAGEMENT_USER_MAIL = os.environ["DJ_MANAGEMENT_USER_MAIL"]
ADMIN_OPEN_KEYPHRASE = os.environ["DJ_ADMIN_OPEN_KEYPHRASE"]
DEFAULT_FROM_EMAIL = os.environ["DJ_SG_DEFAULT_FROM_EMAIL"]

TWILIO_ACCOUNT_SID = os.environ["DJ_TWILIO_ACCOUNT_SID"]
TWILIO_API_KEY_SID = os.environ["DJ_TWILIO_API_KEY_SID"]
TWILIO_API_SECRET = os.environ["DJ_TWILIO_API_SECRET"]

if IS_PROD and 'K8_POD_IP' in os.environ:
    # So that we can further restrict access to the depoloyment kubernetes node
    ALLOWED_HOSTS.append(os.environ['K8_POD_IP'])

"""
Own applications:
management: for user management and general api usage
"""

INSTALLED_APPS = [
    'tracking',  # Our user / action / event tracking
    'emails',  # Manageing logging and sending emails
    'cookie_consent',  # Our cookie consent management system

    'management',  # Main backend application

    'chat.django_private_chat2.apps.DjangoPrivateChat2Config',  # Our chat

    'corsheaders',
    'rest_framework',
    # A convenient multiselect field for db objects ( used e.g.: in profile.interests )
    'multiselectfield',
    'phonenumber_field',  # Conevnient handler for phone numbers with admin prefix
    'django_rest_passwordreset',  # TODO: could also be used for MFA via email

    'jazzmin',  # The waaaaaay nicer admin interface

    'hijack',  # For admins to login as other users, for remote administration and support
    'hijack.contrib.admin',  # Hijack button on user list in admin interface

    'django_celery_beat',
    'django_celery_results',

    'martor',
    'collectfast',

    # API docs not required in deployment, so we disable to routes
    # Though we keep the backages so we don't have to split the code
    'drf_spectacular',  # for api shema generation
    'drf_spectacular_sidecar',  # statics for redoc and swagger

    *(['django_spaghetti'] if BUILD_TYPE in ['staging', 'development'] else []),

    'webpack_loader',  # Load bundled webpack files, check `./run.py front`
    'storages',  # django storages managing s3 bucket files!
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'revproxy'
    #*(['django.contrib.sessions'] if IS_PROD or IS_STAGE else []),
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
    *([  # Whitenoise to server static only needed in development
        'whitenoise.middleware.WhiteNoiseMiddleware',
    ] if IS_DEV or DOCS_BUILD else []),
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'management.middleware.OverwriteSessionLangIfAcceptLangHeaderSet',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'management.middleware.AdminPathBlockingMiddleware',
    'hijack.middleware.HijackUserMiddleware',
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
if IS_STAGE or IS_PROD:
    # TODO: figure out which of these actually is the correct one!
    CORS_ALLOWED_ORIGINS = [
        BASE_URL
    ]

    CORS_ORIGIN_WHITELIST = [
        BASE_URL
    ]

    CSRF_TRUSTED_ORIGINS = [
        BASE_URL
    ]
elif DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
    CSRF_TRUSTED_ORIGINS = ["https://*.github.dev"]
    CSRF_ORIGIN_ALLOW_ALL = True


if not DEBUG:
    SESSION_COOKIE_SECURE = True

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


if not DOCS_BUILD and (IS_PROD or IS_STAGE):
    print("TRYING to push statics to bucket")
    # In production & staging we use S3 as file storage!
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    COLLECTFAST_STRATEGY = "collectfast.strategies.boto3.Boto3Strategy"
    #COLLECTFAST_ENABLED = False

    AWS_ACCESS_KEY_ID = os.environ['DJ_AWS_STATIC_ACCESS_KEY_ID']
    AWS_SECRET_ACCESS_KEY = os.environ['DJ_AWS_STATIC_SECRET_KEY']
    AWS_STORAGE_BUCKET_NAME = os.environ['DJ_AWS_STATIC_BUCKET_NAME']
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_S3_REGION_NAME = os.environ['DJ_AWS_REGION_NAME']
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'
    # https: // litttle-world-staging-bucket.s3.eu-central-1.amazonaws.com/
    # AWS_S3_ENDPOINT_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}'
    # {AWS_STORAGE_BUCKET_NAME}
    AWS_LOCATION = f'static'
    AWS_DEFAULT_ACL = 'public-read'

    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'static/')
    ]

    AWS_STATIC_ROOT = f'static'
    STATIC_URL = '{}/{}/'.format(AWS_S3_CUSTOM_DOMAIN, AWS_STATIC_ROOT)
    print("AWS URL", STATIC_URL)

    #STATIC_ROOT = os.path.join(BASE_DIR, 'static')
    #STATIC_ROOT = '{}/static/'.format(AWS_STORAGE_BUCKET_NAME)

    # dynamic user uploaded content like the profile image
    # .format(AWS_STORAGE_BUCKET_NAME)
    #jAWS_LOCATION_MEDIA = f'{AWS_STORAGE_BUCKET_NAME}/media'
    #MEDIA_URL = '{}/{}/'.format(AWS_S3_ENDPOINT_URL, AWS_LOCATION_MEDIA)
    #MEDIA_ROOT = 'media/'
    #jprint("TBS:", MEDIA_URL)
    CACHES = {  # This is so wee can use multithreaded statics uploads!
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        },
        'collectfast': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': 'redis://host.docker.internal:6379',
        }
    }
    COLLECTFAST_CACHE = "collectfast"
    COLLECTFAST_THREADS = 20
else:
    """
    In development all staticfiles will be hosted here
    In production we host them in an S3 bucket so we don't need to serve them our selves!
    """
    COLLECTFAST_ENABLED = False
    print("USING LOCAL STATIC SETUP")
    STATIC_URL = '/static/'
    STATIC_URL = 'static/'
    MEDIA_URL = '/media/'

    STATIC_ROOT = os.path.join(BASE_DIR, 'static/')
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'emails/static/')
    ]


USE_I18N = True
def ugettext(s): return s


"""
We want BigAutoField per default just in case
this will use 'BigAutoField' as default id for db models
"""
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# All languages frontends can be in:
# They will pre passed as tag -> lang references!
FRONTEND_LANGS = ['en', 'de']

LANGUAGES = [
    # v-- first one cause this is the lang we write our translation tags in
    # _TB cause this is Tim Benjamins English ;)
    # v- Tim using jamaican english, cause he cant be botherered to recompile translation everythime
    ('en', ugettext('English')),
    ('de', ugettext('German')),
    ('tag', ugettext('Tag')),
    # v-- these are custom tags to be overwritten from frontend!
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'management/locale/'),
    os.path.join(BASE_DIR, 'management/')
]

LOGIN_URL = "/login"

"""
uvicorn can handle both WSGI & ASGI
ASGI is veryimportant for chat websockets 
and e.g.: incomming call popups
"""
WSGI_APPLICATION = "back.wsgi.application"
ASGI_APPLICATION = "back.asgi.application"

"""
Some settings for celery
CELERY_RESULT_EXTENDED is imporant for celery results to correctly display in db admin panel
"""
CELERY_TIMEZONE = os.environ['DJ_CELERY_TIMEZONE']
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_RESULT_EXTENDED = True
CELERY_ENABLE_UTC = True

if BUILD_TYPE in ['staging', 'development']:
    pass

"""
django-rest-password reset config:
Password reset tokens are only valid for 1h!
This will nicely show all active tokens 
which are valid for only one password change!
"""
DJANGO_REST_MULTITOKENAUTH_RESET_TOKEN_EXPIRY_TIME = 1
DJANGO_REST_PASSWORDRESET_NO_INFORMATION_LEAKAGE = True
DJANGO_REST_MULTITOKENAUTH_REQUIRE_USABLE_PASSWORD = False


def get_redis_connect_url_port():
    return os.environ['DJ_REDIS_HOST'], os.environ['DJ_REDIS_PORT']


if IS_DEV:
    # autmaticly renders index.html when entering an absolute static path
    WHITENOISE_INDEX_FILE = True
    CELERY_BROKER_URL = 'redis://host.docker.internal:6379'
elif IS_STAGE or IS_PROD:
    # Sadly it turnsour that celery doesn't support redis clusters
    # So we will need to use Rabbit MQ instead
    # url, port = get_redis_connect_url_port()
    # CELERY_BROKER_URL = f"rediss://{url}:{port}/0"
    mb_usr, mb_pass, mb_host, mb_port = os.environ['DJ_RABBIT_MQ_USER'], os.environ[
        'DJ_RABBIT_MQ_PASSWORD'], os.environ['DJ_RABBIT_MQ_HOST'], os.environ['DJ_RABBIT_MQ_PORT']
    CELERY_BROKER_URL = f'amqps://{mb_usr}:{mb_pass}@{mb_host}:{mb_port}'

CELERY_RESULT_BACKEND = 'django-db'  # 'redis://host.docker.internal:6379'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = os.environ.get("DJ_CELERY_TIMEZONE", "Europe/Berlin")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

CELERY_RESULT_BACKEND = 'django-db'

# We enforce these authentication classes
# By that we force a crsf token to be present on **every** POST request
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ]
}


# pylint doesn't like it not sure why
REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = 'drf_spectacular.openapi.AutoSchema'

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


if IS_DEV:
    # or install redis in the container
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            # "BACKEND": "channels.layers.InMemoryChannelLayer",
            "CONFIG": {
                "hosts": [("host.docker.internal", 6379)],
            },
        }
    }
elif IS_STAGE or IS_PROD:
    """
    There are some quirks setting this up in production: 
    For aws memory db we can unly connect to channels from redis cli by using --tls
    I can also connect to redis with redis-py if I use ssl=True
    But I'm not sure how to tell django-channels to use ssl=True
    I think there actually isn't such an option, see this issue: https://github.com/django/channels_redis/issues/235
    Ok I did some digging in the channels_redis package
    It seems that It uses: aioredis.create_redis_pool(**kwargs)
    This is based on the host configuration and does accept an ssl=* param
    And that did acutally fucking work lol, go read some code kids
    """
    url, port = get_redis_connect_url_port()
    path = f"rediss://{url}:{port}"
    if IS_PROD:
        r_auth_token = os.environ['DJ_REDIS_PASSWORD']
        path = f"rediss://:{r_auth_token}@{url}:{port}"
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [{
                    'address': path,
                    'ssl': True
                }],
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
} if IS_DEV else {
    'default': {
        'ENGINE': 'django.db.backends.{}'.format(
            os.environ['DJ_DATABASE_ENGINE']
        ),
        'NAME': os.environ['DJ_DATABASE_NAME'],
        'USER': os.environ['DJ_DATABASE_USERNAME'],
        'PASSWORD': os.environ['DJ_DATABASE_PASSWORD'],
        'HOST': os.environ['DJ_DATABASE_HOST'],
        'PORT': os.environ['DJ_DATABASE_PORT'],
        'OPTIONS': {'sslmode': 'require'},
    },
}

if IS_PROD or IS_STAGE:
    EMAIL_HOST = 'smtp.sendgrid.net'
    EMAIL_HOST_USER = 'apikey'
    EMAIL_HOST_PASSWORD = os.environ['DJ_SG_SENDGRID_API_KEY']
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    DEFAULT_FROM_EMAIL = os.environ["DJ_SG_DEFAULT_FROM_EMAIL"]

"""
Default django password validator
We *dont* allow: 
- numeric passwords
- password to similar to user.first_name
- password to common ( sample of commonly enumerated passwords )
- password under 8 characters
"""
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
    'BUNDLE_DIR_NAME': f"/front/dist/{app}",
    'POLL_INTERVAL': 0.1,
    'IGNORE': [r'.+\.hot-update.js', r'.+\.map'],
} for app in FRONTENDS}

"""
Default language code of the application
this reflects which language the translation of the app are written in
so as long the default the incode translations are english **dont change this**
as default language the user will always have a fallback langugae 
english no matter if frontent translation failes
"""
LANGUAGE_CODE = 'en'
TIME_ZONE = os.environ.get('DJ_TIME_ZONE', 'UTC+1')  # UTC+1 = Berlin

"""
We use django internalization to enable use of 'django_language' cookie 
And the use of Accept-Language: <lang> headers
this e.g.: enables frontends to request api translation before calling the apis!
They would request the pseudo language 'tag' as reference
`tag` are the translation contexts for all `pgettext_lazy` calls
"""
USE_I18N = True
USE_L10N = True
USE_TZ = True


if DEBUG:
    info = '\n '.join([f'{n}: {globals()[n]}' for n in [
        'BASE_DIR', 'ALLOWED_HOSTS', 'CELERY_TIMEZONE', 'FRONTENDS', 'DATABASES']])
    print(f"configured django settings:\n {info}")

"""
Settings for the sleek admin panel
TODO we should remove cdn stuff like google fonts from this!
"""
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

        {"name": "Matching Pannel", "url": "/admin_panel",
            "new_window": True},

        {"name": "DB shema", "url": "/db",
            "new_window": True},

        {"name": "Admin Chat", "url": "/admin_chat",
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
        {"name": "Matching Pannel", "url": "/admin_panel",
            "new_window": True},
        {"name": "AdminChat", "url": f"{BASE_URL}/admin_chat",
            "new_window": True},
        {"name": "Home",  "url": "/app",
            "permissions": ["auth.view_user"]},
        {"name": "Repo", "url": "https://github.com/a-little-world/little-world-backend",
            "new_window": True},
        {"name": "DB shema", "url": "/db",
            "new_window": True},
        {"name": "Admin Chat", "url": "/admin_chat",
            "new_window": True},
        {"name": "Docs", "url": "/static/docs",
            "new_window": True},
        {"name": "API", "url": "/api/schema/swagger-ui/",
            "new_window": True},
        {"name": "Emails", "url": "/emails/welcome",
            "new_window": True},
        {"event": "tracking"},
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
        "emails.EmailLog": "fas fa-envelope",
        "django_private_chat2.DialogsModel": "fas fa-people-arrows",
        "django_private_chat2.MessageModel": "fas fa-comments",
        "cookie_consent.Cookie": "fas fa-cookie",
        "cookie_consent.CookieGroup": "fas fa-layer-group",
        "cookie_consent.LogItem": "fas fa-stream",
        "management.BackendState": "fas fa-code",
        "management.User": "fas fa-user",
        "management.State": "fas fa-user-cog",
        "management.MatchinScore": "fas fa-project-diagram",
        "management.ScoreTableSource": "fas fa-digital-tachograph",
        "management.Profile": "fas fa-user-circle",
        "management.Room": "fas fa-video",
        "management.Settings": "fas fa-cogs",
        "management.CommunityEvent": "fas fa-users",
        "management.Notification": "fas fa-comment-alt",
        "management.User": "fas fa-user",
        "django_celery_results.TaskResult": "fas fa-poll-h",
        "django_celery_results.GroupResult": "fas fa-th-list",
        "django_rest_passwordreset.ResetPasswordToken": "fas fa-key",
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

JAZZMIN_UI_TWEAKS = {
    "sidebar_nav_compact_style": True,
}

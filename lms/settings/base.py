import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import environ

import django

env = environ.Env()
# Try to read .env file, if it's not present, assume that application
# is deployed to production and skip reading the file
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    environ.Env.read_env(env_file=env.str("ENV_FILE", default=None))


ROOT_DIR = Path(__file__).parents[2]
ROOT_URLCONF = 'lms.urls'
SHARED_APPS_DIR = ROOT_DIR / "apps"

SITE_ID = env.int("SITE_ID", default=None)

DEBUG = env.bool("DEBUG", default=False)

RESTRICT_LOGIN_TO_LMS = True
REVERSE_TO_LMS_URL_NAMESPACES = (
    "staff",
    "study",
    "teaching",
    "files",
    "auth",
    "courses",
    "learning-api",
)

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [
    r"^health-check/$",
    r"^readiness/$",
]

# Default scheme for `core.urls.reverse`
DEFAULT_URL_SCHEME = env.str("REVERSE_URL_SCHEME", default="https")
LMS_SUBDOMAIN: Optional[str] = None
LMS_DOMAIN: Optional[str] = env.str("LMS_DOMAIN", default="example.com")

SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
SESSION_COOKIE_DOMAIN = env.str("DJANGO_SESSION_COOKIE_DOMAIN", default=None)
SESSION_COOKIE_NAME = env.str("DJANGO_SESSION_COOKIE_NAME", default="sessionid")
SESSION_COOKIE_SAMESITE = env.str("DJANGO_SESSION_COOKIE_SAMESITE", default=None)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=True)
CSRF_COOKIE_DOMAIN = env.str("DJANGO_CSRF_COOKIE_DOMAIN", default=None)
CSRF_COOKIE_NAME = env.str("DJANGO_CSRF_COOKIE_NAME", default="csrftoken")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])

# Upload Settings
# Affects client side only, server side upload size is limited by nginx
FILE_MAX_UPLOAD_SIZE = env.int(
    "DJANGO_FILE_MAX_UPLOAD_SIZE", default=1024 * 1024 * 100
)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE", default=2621440
)
USE_CLOUD_STORAGE = env.bool("USE_CLOUD_STORAGE", default=True)
AWS_DEFAULT_ACL: Optional[str] = None  # All files will inherit the bucket’s ACL
if USE_CLOUD_STORAGE:
    DEFAULT_FILE_STORAGE = "files.storage.PrivateMediaS3Storage"
    AWS_S3_ACCESS_KEY_ID = env.str("AWS_S3_ACCESS_KEY_ID")
    AWS_S3_SECRET_ACCESS_KEY = env.str("AWS_S3_SECRET_ACCESS_KEY")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME", default="lms-vault")
    AWS_S3_ENDPOINT_URL = env.str("AWS_S3_ENDPOINT_URL", None)
    AWS_S3_CUSTOM_DOMAIN = env.str("AWS_S3_CUSTOM_DOMAIN", None)
else:
    FILE_UPLOAD_DIRECTORY_PERMISSIONS = env.int(
        "DJANGO_FILE_UPLOAD_DIRECTORY_PERMISSIONS", default=0o755
    )
    FILE_UPLOAD_PERMISSIONS = env.int("DJANGO_FILE_UPLOAD_PERMISSIONS", default=0o664)
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    MEDIA_ROOT = env.str("DJANGO_PUBLIC_MEDIA_ROOT")
    if MEDIA_ROOT.startswith("."):
        # Relative path must be relative to the ROOT_DIR
        MEDIA_ROOT = str(ROOT_DIR.joinpath(MEDIA_ROOT).resolve())
    MEDIA_URL = "/media/"
    PRIVATE_FILE_STORAGE = "files.storage.PrivateFileSystemStorage"
    PRIVATE_MEDIA_ROOT = env.str("DJANGO_PRIVATE_MEDIA_ROOT")
    if PRIVATE_MEDIA_ROOT.startswith("."):
        # Relative path must be relative to the ROOT_DIR
        PRIVATE_MEDIA_ROOT = str(ROOT_DIR.joinpath(PRIVATE_MEDIA_ROOT).resolve())
    PRIVATE_MEDIA_URL = "/media/private/"

# Static Files Settings
DJANGO_ASSETS_ROOT = ROOT_DIR / "assets"
WEBPACK_ASSETS_ROOT = Path(
    env.str("WEBPACK_ASSETS_ROOT"), default=DJANGO_ASSETS_ROOT
).resolve()
STATICFILES_DIRS = [
    ROOT_DIR / "assets_static",
    str(DJANGO_ASSETS_ROOT),
    str(WEBPACK_ASSETS_ROOT),
]
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]
STATIC_ROOT = env.str("DJANGO_STATIC_ROOT", default=str(ROOT_DIR / "static"))
STATIC_URL = "/static/"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

WEBPACK_ENVIRONMENT = env.str("WEBPACK_ENVIRONMENT", default="prod")
WEBPACK_LOADER = {
    "V1": {
        "BUNDLE_DIR_NAME": f"v1/dist/{WEBPACK_ENVIRONMENT}/",  # relative to the ASSETS_ROOT
        "STATS_FILE": str(
            WEBPACK_ASSETS_ROOT
            / "v1"
            / "dist"
            / WEBPACK_ENVIRONMENT
            / "webpack-stats-v1.json"
        ),
    },
}

# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db_url(var="DATABASE_URL")}


MIDDLEWARE = [
    # TODO: Return SecurityMiddleware or configure security with nginx-ingress
    #  https://docs.djangoproject.com/en/4.0/ref/middleware/#module-django.middleware.security
    "core.middleware.HealthCheckMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "auth.middleware.AuthenticationMiddleware",
    "django.contrib.sites.middleware.CurrentSiteMiddleware",
    # EN language is not supported at this moment anyway
    "core.middleware.HardCodedLocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "notifications.middleware.UnreadNotificationsCacheMiddleware",
    "core.middleware.RedirectMiddleware",
]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REDIS_PASSWORD = env.str("REDIS_PASSWORD", default=None)
REDIS_HOST = env.str("REDIS_HOST", default="127.0.0.1")
REDIS_PORT = env.int("REDIS_PORT", default=6379)
REDIS_DB_INDEX = env.int("REDIS_DB_INDEX", default=SITE_ID)
REDIS_SSL = env.bool("REDIS_SSL", default=True)
RQ_QUEUES = {
    "default": {
        "HOST": REDIS_HOST,
        "PORT": REDIS_PORT,
        "DB": REDIS_DB_INDEX,
        "PASSWORD": REDIS_PASSWORD,
        "SSL": REDIS_SSL,
    },
    "high": {
        "HOST": REDIS_HOST,
        "PORT": REDIS_PORT,
        "DB": REDIS_DB_INDEX,
        "PASSWORD": REDIS_PASSWORD,
        "SSL": REDIS_SSL,
    },
}


# https://sorl-thumbnail.readthedocs.io/en/latest/reference/settings.html
THUMBNAIL_DEBUG = DEBUG
THUMBNAIL_DUMMY = True
THUMBNAIL_PRESERVE_FORMAT = True
THUMBNAIL_KVSTORE = "sorl.thumbnail.kvstores.redis_kvstore.KVStore"
THUMBNAIL_REDIS_HOST = REDIS_HOST
THUMBNAIL_REDIS_PORT = REDIS_PORT
# Use shared database for thumbnails
THUMBNAIL_REDIS_DB = 0
THUMBNAIL_REDIS_PASSWORD = REDIS_PASSWORD
THUMBNAIL_REDIS_SSL = REDIS_SSL

# Monitoring
SENTRY_DSN = env("SENTRY_DSN")
SENTRY_LOG_LEVEL = env.int("SENTRY_LOG_LEVEL", default=logging.INFO)

ESTABLISHED = 2011

# Template customization
FAVICON_PATH = "v1/img/center/favicon.svg"
LOGO_PATH = "v1/img/center/logo.svg"
# Provide zero value to disable counter rendering

DJANGO_ROOT_DIR = Path(django.__file__).parent
TEMPLATES: List[Dict[str, Any]] = [
    {
        "BACKEND": "django_jinja.backend.Jinja2",
        "APP_DIRS": False,
        "DIRS": [
            str(DJANGO_ROOT_DIR / "forms" / "jinja2"),
            str(ROOT_DIR / "lms" / "jinja2"),
        ],
        "NAME": "jinja2",
        "OPTIONS": {
            "match_extension": None,
            "match_regex": r"^(?!admin/|django/).*",
            "filters": {
                "markdown": "core.jinja2.filters.markdown",
                "pluralize": "core.jinja2.filters.pluralize",
                "thumbnail": "core.jinja2.filters.thumbnail",
                "with_classes": "core.jinja2.filters.with_classes",
                "youtube_video_id": "core.jinja2.filters.youtube_video_id",
                "date_soon_css": "core.jinja2.filters.date_soon_css",
                "naturalday": "django.contrib.humanize.templatetags.humanize.naturalday",
            },
            "constants": {
                "ESTABLISHED": ESTABLISHED,
                "FAVICON_PATH": FAVICON_PATH,
                "LOGO_PATH": LOGO_PATH,
                # JS configuration
                "FILE_MAX_UPLOAD_SIZE": FILE_MAX_UPLOAD_SIZE,
                "CSRF_COOKIE_NAME": CSRF_COOKIE_NAME,
                "SENTRY_DSN": SENTRY_DSN,
            },
            "globals": {
                "messages": "core.jinja2.globals.messages",
                "get_menu": "core.jinja2.globals.generate_menu",
                "crispy": "core.jinja2.globals.crispy",
            },
            "extensions": [
                "jinja2.ext.do",
                "jinja2.ext.loopcontrols",
                "jinja2.ext.i18n",
                "django_jinja.builtins.extensions.CsrfExtension",
                "django_jinja.builtins.extensions.CacheExtension",
                "django_jinja.builtins.extensions.TimezoneExtension",
                "django_jinja.builtins.extensions.StaticFilesExtension",
                "django_jinja.builtins.extensions.DjangoFiltersExtension",
                "webpack_loader.contrib.jinja2ext.WebpackExtension",
                "core.jinja2.ext.UrlExtension",
                "core.jinja2.ext.SpacelessExtension",
            ],
            "bytecode_cache": {
                "name": "default",
                "backend": "django_jinja.cache.BytecodeCache",
                "enabled": False,
            },
            "newstyle_gettext": True,
            "auto_reload": DEBUG,
            "translation_engine": "django.utils.translation",
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": False,
        "DIRS": [
            str(SHARED_APPS_DIR / "templates"),
            str(DJANGO_ROOT_DIR / "forms" / "templates"),
            str(SHARED_APPS_DIR / "staff" / "templates"),
        ],
        "OPTIONS": {
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                # FIXME: this setting overrides `APP_DIRS` behavior! WTF?
                "django.template.loaders.app_directories.Loader",
            ],
            "context_processors": (
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
                "core.context_processors.subdomain",
                "core.context_processors.common_context",
                "core.context_processors.js_config",
            ),
            "debug": DEBUG,
        },
    },
]
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

SECRET_KEY = env("DJANGO_SECRET_KEY")
# Sensitive model-based configuration is encrypted with this key.
# Don't forget to update site configuration after rotating a secret key.
DB_SECRET_KEY = env.str("DJANGO_DB_SECRET_KEY")


# Email settings
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER = env.str("DJANGO_EMAIL_ADDRESS")
EMAIL_HOST = env.str("DJANGO_EMAIL_HOST", default="smtp.yandex.ru")
EMAIL_HOST_PASSWORD = env.str("DJANGO_EMAIL_HOST_PASSWORD", default=None)
EMAIL_PORT = env.int("DJANGO_EMAIL_PORT", default=465)
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True
EMAIL_SEND_COOLDOWN = 0.5
EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
LMS_CURATOR_EMAIL = env.str("LMS_CURATOR_EMAIL", default=f"noreply@{LMS_DOMAIN}")
# Mailing
AWS_SES_ACCESS_KEY_ID = env.str("AWS_SES_ACCESS_KEY_ID")
AWS_SES_SECRET_ACCESS_KEY = env.str("AWS_SES_SECRET_ACCESS_KEY")
AWS_SES_REGION_NAME = env.str("AWS_SES_REGION_NAME", default="eu-west-1")
AWS_SES_REGION_ENDPOINT = env.str(
    "AWS_SES_REGION_ENDPOINT", default="email.eu-west-1.amazonaws.com"
)
AWS_SES_REGION_ENDPOINT_URL = env.str(
    "AWS_SES_REGION_ENDPOINT_URL", default="https://" + AWS_SES_REGION_ENDPOINT
)
AWS_SES_AUTO_THROTTLE = None

HASHIDS_SALT = env.str("HASHIDS_SALT")

if env.str('RECAPTCHA_PRIVATE_KEY', default=None) or env.str('RECAPTCHA_PUBLIC_KEY', default=None):
    RECAPTCHA_PRIVATE_KEY = env.str('RECAPTCHA_PRIVATE_KEY')
    RECAPTCHA_PUBLIC_KEY = env.str('RECAPTCHA_PUBLIC_KEY')
if env.bool('RECAPTCHA_TEST_MODE', default=False):
    SILENCED_SYSTEM_CHECKS = ['django_recaptcha.recaptcha_test_key_error']

INSTALLED_APPS = [
    "dal",
    "dal_select2",
    "core.apps.CustomAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.humanize",
    "loginas",
    "registration",
    "sorl.thumbnail",
    "crispy_forms",
    "crispy_bootstrap3",
    "import_export",
    "django_rq",
    "webpack_loader",
    "django_filters",
    "rest_framework",
    "taggit",
    "core.apps.CoreConfig",
    "menu",
    "universities.apps.UniversitiesConfig",
    # django.contrib.static with a customized list of ignore patterns
    "files.apps.StaticFilesConfig",
    "files.apps.MediaFilesConfig",
    "auth.apps.AuthConfig",  # custom `User` model is defined in `users` app
    "users.apps.UsersConfig",
    "courses.apps.CoursesConfig",
    "study_programs.apps.StudyProgramsConfig",
    "learning.apps.LearningConfig",
    "tasks",
    "notifications.apps.NotificationsConfig",
    "api.apps.APIConfig",
    'lms',
    'django_jinja',
    'staff',
    'info_blocks.apps.InfoBlocksConfig',
    'faq.apps.FAQConfig',
    'django_recaptcha',
    'alumni.apps.AlumniConfig',
]

# i18n, l10n
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("ru", "Russian"),
    ("en", "English"),
]
USE_I18N = True
USE_L10N = True
LOCALE_PATHS = [
    str(ROOT_DIR / "locale"),
]
USE_TZ = True
TIME_ZONE = "UTC"
DATE_FORMAT = "j E Y"
DEFAULT_TIMEZONE = ZoneInfo("Europe/Moscow")

# auth
AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = ("auth.backends.RBACModelBackend",)
CAN_LOGIN_AS = lambda request, target_user: request.user.is_superuser
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGINAS_FROM_USER_SESSION_FLAG = "loginas_from_user"

DEFAULT_CITY_CODE = "spb"
ADMIN_URL = "/narnia/"
ADMIN_REORDER: List[Any] = []
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap3"
CRISPY_TEMPLATE_PACK = "bootstrap3"


REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        # FIXME: Better to use more restricted rules by default
        "rest_framework.permissions.IsAuthenticatedOrReadOnly"
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
    ),
    "UNAUTHENTICATED_USER": "users.models.ExtendedAnonymousUser",
    # TODO: migrate all existing api views to the camel case renderer
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "JSON_UNDERSCOREIZE": {
        "no_underscore_before_number": True,
    },
    "DATE_INPUT_FORMATS": ["iso-8601", "%d.%m.%Y"],
}


IS_CERTIFICATES_OF_PARTICIPATION_ENABLED = env.bool(
    "IS_CERTIFICATES_OF_PARTICIPATION_ENABLED", default=True
)
IS_SOCIAL_ACCOUNTS_ENABLED = env.bool("IS_SOCIAL_ACCOUNTS_ENABLED", default=False)


# FIXME: Distribute values to production, then remove defaults
SOCIAL_AUTH_GITLAB_MANYTASK_KEY = env.str("SOCIAL_AUTH_GITLAB_MANYTASK_KEY", default="")
SOCIAL_AUTH_GITLAB_MANYTASK_SECRET = env.str(
    "SOCIAL_AUTH_GITLAB_MANYTASK_SECRET", default=""
)
SOCIAL_AUTH_GITHUB_KEY = env.str("SOCIAL_AUTH_GITHUB_KEY", default="")
SOCIAL_AUTH_GITHUB_SECRET = env.str("SOCIAL_AUTH_GITHUB_SECRET", default="")


LOG_FORMAT = env.str("LOG_FORMAT", default="json")

if DEBUG:
    # Django Debug Toolbar
    try:
        import debug_toolbar

        INTERNAL_IPS = ["127.0.0.1", "::1"]
        # `show_debug_toolbar` logic depends on auth middleware
        position = MIDDLEWARE.index("auth.middleware.AuthenticationMiddleware")
        MIDDLEWARE.insert(
            position + 1, "debug_toolbar.middleware.DebugToolbarMiddleware"
        )
        INSTALLED_APPS = INSTALLED_APPS + ["debug_toolbar"]
        DEBUG_TOOLBAR_CONFIG = {
            "SHOW_TOOLBAR_CALLBACK": "core.middleware.show_debug_toolbar"
        }
    except ModuleNotFoundError as err:
        warnings.warn(str(err), ImportWarning)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(levelname)s %(message)s"},
        "json": {
            "()": "core.logging.JsonFormatter",
            "format": "%(level)s %(name)s %(message)s",
        },
        "sql": {
            "()": "core.logging.SQLFormatter",
            "format": "[%(duration).3f] %(statement)s",
        },
        "rq_console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG" if DEBUG else "INFO",
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
        },
        "sql": {
            "class": "logging.StreamHandler",
            "formatter": "sql",
            "level": "DEBUG",
        },
        "null": {
            "class": "logging.NullHandler",
        },
        "rq_console": {
            "level": "DEBUG" if DEBUG else "INFO",
            "class": "rq.logutils.ColorizingStreamHandler",
            "formatter": "rq_console",
            "exclude": ["%(asctime)s"],
        },
    },
    "loggers": {
        # root logger
        "": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
        },
        "django": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": True,
        },
        "django.db.backends": {
            "handlers": ["null"],
            "level": "DEBUG" if DEBUG else "ERROR",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "ERROR",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.utils.autoreload": {
            "handlers": ["console" if DEBUG else "null"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.db.backends.schema": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django.template": {
            "handlers": ["console"],
            "level": "WARNING" if DEBUG else "ERROR",
            "propagate": False,
        },
        "rq.worker": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


LMS_MENU = 'lms.lms_menu'

SUBMISSION_SERVICE_URL = env.str('SUBMISSION_SERVICE_URL', 'https://educational-service.labs.jb.gg')
SUBMISSION_SERVICE_TOKEN = env.str('SUBMISSION_SERVICE_TOKEN')
SUBMISSION_SERVICE_REFRESH_INTERVAL_MINUTES = env.int('SUBMISSION_SERVICE_REFRESH_INTERVAL_MINUTES', 60 * 4)

ADMIN_NOTIFICATIONS_EMAILS = env.list('ADMIN_NOTIFICATIONS_EMAILS')

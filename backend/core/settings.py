from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(DEBUG=(bool, False))

environ.Env.read_env(BASE_DIR.parent / '.env')

SECRET_KEY = env('SECRET_KEY', default='dev-secret-key')
DEBUG = env('DEBUG', default=True)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '0.0.0.0'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'corsheaders',
    'evaluations',
    'benchmarks',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

IN_DOCKER = env.bool('IN_DOCKER', default=False)
DATABASE_URL = env('DATABASE_URL', default='')
if IN_DOCKER and DATABASE_URL:
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL)}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(BASE_DIR / 'db.sqlite3')}}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Evalix API',
    'DESCRIPTION': 'RAG evaluation service',
    'VERSION': '1.0.0',
}

CORS_ALLOW_ALL_ORIGINS = True

CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_TASK_ALWAYS_EAGER', default=not IN_DOCKER)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'evalix-tests',
    },
}
if not DEBUG:
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('CACHE_URL', default=env('REDIS_URL', default='redis://localhost:6379/1')),
    }

EVALUATOR_PROVIDER = env('EVALUATOR_PROVIDER', default='gemini')
EVALUATOR_MODEL = env('EVALUATOR_MODEL', default='gemini-3.1-flash-lite')
EVALUATOR_TEMPERATURE = env.float('EVALUATOR_TEMPERATURE', default=0.0)
EVALUATOR_PROMPT_VERSION = env('EVALUATOR_PROMPT_VERSION', default='v1')
EVALUATOR_MAX_RETRIES = env.int('EVALUATOR_MAX_RETRIES', default=3)
EVALUATOR_RETRY_BACKOFF_SECONDS = env.float('EVALUATOR_RETRY_BACKOFF_SECONDS', default=0.1)
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
OPENAI_BASE_URL = env('OPENAI_BASE_URL', default='https://api.openai.com/v1')
GEMINI_API_KEY = env('GEMINI_API_KEY', default='')
if EVALUATOR_PROVIDER == 'gemini' and (not GEMINI_API_KEY or GEMINI_API_KEY == 'replace-me'):
    print('Evalix startup warning: GEMINI_API_KEY is not configured. Set it in .env before using the Gemini evaluator.')
EVALUATOR_COST_PER_1K_TOKENS = env.float('EVALUATOR_COST_PER_1K_TOKENS', default=0.0)
MAX_BATCH_BYTES = env.int('MAX_BATCH_BYTES', default=5 * 1024 * 1024)
MAX_BATCH_CASES = env.int('MAX_BATCH_CASES', default=1000)
EVALUATION_TASK_CHUNK_SIZE = env.int('EVALUATION_TASK_CHUNK_SIZE', default=50)
EVALUATION_TASK_RATE_LIMIT = env('EVALUATION_TASK_RATE_LIMIT', default='60/m')
EVALUATION_WORKER_CONCURRENCY = env.int('EVALUATION_WORKER_CONCURRENCY', default=2)

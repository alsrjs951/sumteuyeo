import os
import environ
from pathlib import Path
from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# 환경변수 초기화
env = environ.Env(
    DEBUG=(bool, False)
)

# .env 파일 읽기 (BASE_DIR 바로 아래에 .env 파일이 있다고 가정)
env.read_env(os.path.join(BASE_DIR, '.env'))

# Quick-start development settings - unsuitable for production
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions', # Redis 세션 사용 시에도 필요
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core.apps.CoreConfig',
    'apps.users.apps.UsersConfig',
    'apps.items.apps.ItemsConfig',
    'apps.interactions.apps.InteractionsConfig',
    'apps.recommender.apps.RecommenderConfig',
    'pgvector.django',    # 첫 번째 파일에만 있었음
    'rest_framework',     # 첫 번째 파일에만 있었음
    # 'django_redis',     # django-redis는 INSTALLED_APPS에 필수는 아님
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', # 세션 미들웨어
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sumteuyeo.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sumteuyeo.wsgi.application'

# Database (PostgreSQL, AWS RDS 기준)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('POSTGRES_DB_NAME'),
        'USER': env('POSTGRES_DB_USER'),
        'PASSWORD': env('POSTGRES_DB_PASSWORD'),
        'HOST': env('POSTGRES_DB_HOST', default='localhost'),
        'PORT': env('POSTGRES_DB_PORT', cast=int, default=3306),
        'OPTIONS': {
            # MySQL 옵션 예시 주석 처리됨
        },
    }
}

# Cache (AWS ElastiCache for Redis 사용)
# https://django-redis-docs.readthedocs.io/en/latest/setup.html#setting-up-django-redis
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{env('REDIS_HOST')}:{env.int('REDIS_PORT')}/0",  # TLS 사용 시 rediss://
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # "PASSWORD": env('REDIS_PASSWORD', default=''), # ElastiCache 암호 설정 시
            "CONNECTION_POOL_KWARGS": {
                # "ssl_cert_reqs": "none",  # SSL 인증서 검증 비활성화
                "max_connections": 50   # 연결 풀 크기 조정
            },
            "SOCKET_CONNECT_TIMEOUT": 20,  # 연결 타임아웃(초)
            "SOCKET_TIMEOUT": 20,          # 작업 타임아웃(초)
        }
    }
}


# Session Engine (Redis)
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Logging (파일 및 콘솔)
LOG_DIR = os.path.join(BASE_DIR, 'management', 'log')
os.makedirs(LOG_DIR, exist_ok=True)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'logfile.log'),
            'encoding': 'utf-8',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Internationalization
LANGUAGE_CODE = 'ko-kr'      # 한국어로 통일
TIME_ZONE = 'Asia/Seoul'     # 서울로 통일
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'


# Media files (User-uploaded files)
# 사용자가 업로드하는 파일을 처리하기 위한 설정 (필요시)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles' # 사용자가 업로드한 파일이 저장될 실제 서버 경로


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# API 인증키값
TOUR_API_KEY = env('TOUR_API_KEY')
OPENAI_API_KEY = env('OPENAI_API_KEY')

# 상호작용 최대 개수
USER_INTERACTION_LIMIT = 1000

# Celery 설정
CELERY_BEAT_SCHEDULE = {
    'update_global_profile': {
        'task': 'users.tasks.update_global_profile_task',
        'schedule': crontab(hour=2, minute=30),
        'options': {'queue': 'batch'}
    }
}

CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'


# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# API 인증키값
TOUR_API_KEY = env('TOUR_API_KEY')

# 프로덕션 환경을 위한 추가 보안 설정 (선택 사항이지만 권장됨)
# if not DEBUG:
#     SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
#     SECURE_SSL_REDIRECT = True
#     SESSION_COOKIE_SECURE = True
#     CSRF_COOKIE_SECURE = True
#     SECURE_HSTS_SECONDS = 31536000  # 1 year
#     SECURE_HSTS_INCLUDE_SUBDOMAINS = True
#     SECURE_HSTS_PRELOAD = True
#     # X_FRAME_OPTIONS = 'DENY' # MIDDLEWARE에 이미 XFrameOptionsMiddleware가 있음
#     SECURE_CONTENT_TYPE_NOSNIFF = True
#     SECURE_BROWSER_XSS_FILTER = True

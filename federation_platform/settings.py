import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 添加联邦学习核心代码路径
FEDERATION_CORE_PATH = os.path.join(BASE_DIR, 'federation_core')

SECRET_KEY = 'django-insecure-your-secret-key-here'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'federation_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'federation_platform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'federation_platform.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# 自定义用户模型
AUTH_USER_MODEL = 'federation_app.User'

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 联邦学习配置


FEDERATION_CONFIG = {
    'default_params_path': os.path.join(FEDERATION_CORE_PATH, 'cifar_params.yaml'),
    'model_save_dir': os.path.join(FEDERATION_CORE_PATH, 'saved_models'),
    # 'log_dir': os.path.join(FEDERATION_CORE_PATH, 'logs'),
    'core_path': os.path.join(BASE_DIR, 'federation_core'),
    'model_save_dir': 'saved_models/',
    'log_dir': 'logs/',
    'core_path': FEDERATION_CORE_PATH,
}
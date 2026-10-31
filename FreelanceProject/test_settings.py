"""
Settings for the automated test suite.

Runs without Postgres, Redis, SMTP or Celery workers:
    python manage.py test --settings=FreelanceProject.test_settings
"""
import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")

from .settings import *  # noqa: E402,F401,F403

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@test.local"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

import tempfile  # noqa: E402

# Uploaded files written by tests go to a throwaway directory
MEDIA_ROOT = tempfile.mkdtemp(prefix="freelancer-test-media-")
SERVE_MEDIA = True

# Throttling would make repeated test requests flaky
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
}

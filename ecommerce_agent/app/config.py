import os

JWT_SECRET_KEY = "django-insecure-9jal3=*t5n-!8^ns-w9&yw7j9s1g&niy+q!em-x=-wun129zrj"
JWT_ALGORITHM = "HS256"

DB_CONFIG={
    "host":"localhost",
    "user":"root",
    "password":"123456",
    "database":"muxi_shop"
}

ALLOWED_ORIGINS=[
    "http://localhost",
    "http://localhost:80",
    "http://127.0.0.1",
    "http://localhost:8080",
    "http://127.0.0.1:8080"
]

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME = "user_preferences"

PROFILE_SUMMARY_MAX_LENGTH = 300
PROFILE_MAX_PREFERENCES = 50
PROFILE_DECAY_FACTOR = 0.95
PROFILE_MIN_WEIGHT = 0.1
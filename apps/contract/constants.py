from django.conf import settings

# -----------------------------
# FILE SIZE LIMITS
# -----------------------------

# 10 MB hard limit (you can change this later without touching serializers)
MAX_DOCUMENT_SIZE_MB = 10
MAX_DOCUMENT_SIZE_BYTES = MAX_DOCUMENT_SIZE_MB * 1024 * 1024


# -----------------------------
# ALLOWED FILE EXTENSIONS
# (context-safe, no executables, no media)
# -----------------------------

ALLOWED_DOCUMENT_EXTENSIONS = {
    # Documents
    "pdf",
    "doc",
    "docx",
    "txt",

    # Images (for screenshots / proofs)
    "jpg",
    "jpeg",
    "png",
    "webp",

    # Optional structured data
    "csv",
    "xlsx",
}

# Explicitly blocked (defensive)
BLOCKED_EXTENSIONS = {
    # Code
    "py", "js", "ts", "java", "cpp", "c", "go", "rs",

    # Archives
    "zip", "rar", "7z", "tar", "gz",

    # Audio / Video
    "mp3", "wav", "mp4", "mov", "avi", "mkv",

    # Executables
    "exe", "sh", "bat", "apk",
}


# -----------------------------
# MIME TYPES (secondary check)
# -----------------------------

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
    "image/webp",
}


# -----------------------------
# STORAGE (S3-safe paths)
# -----------------------------

def contract_document_upload_path(instance, filename):
    """
    S3-safe, predictable, non-user-controlled path
    """
    return (
        f"contracts/"
        f"{instance.contract_id}/"
        f"documents/"
        f"{filename}"
    )

import os
from rest_framework.exceptions import ValidationError
from apps.contract.constants import (
    MAX_DOCUMENT_SIZE_BYTES,
    ALLOWED_DOCUMENT_EXTENSIONS,
    BLOCKED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
)

def validate_contract_document(file):
    if not file:
        raise ValidationError("File is required.")

    # Size check
    if file.size > MAX_DOCUMENT_SIZE_BYTES:
        raise ValidationError(
            f"File too large. Max allowed size is {MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # Extension check
    ext = os.path.splitext(file.name)[1].lower().replace(".", "")
    if not ext:
        raise ValidationError("File extension missing.")

    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError("This file type is not allowed.")

    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError("Unsupported file format for contract documents.")

    # MIME check (secondary)
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError("Invalid file content type.")

    return True

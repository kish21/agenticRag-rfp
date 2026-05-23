"""
Validates documents before ingestion.
Prevents silent failures from scanned PDFs and corrupt files.
"""
import hashlib
import re


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_extracted_text(
    text: str,
    filename: str
) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    is_valid=False means do not ingest — return error to user.
    """
    if not text or len(text.strip()) < 100:
        return False, (
            f"{filename}: Only {len(text)} characters extracted. "
            f"This is likely a scanned PDF with no extractable text. "
            f"Please provide a digital PDF or use OCR to convert first."
        )

    words = text.split()
    if not words:
        return False, f"{filename}: No readable words found."

    avg_word_len = len(text) / len(words)
    if avg_word_len > 15:
        return False, (
            f"{filename}: Average word length {avg_word_len:.1f} "
            f"suggests garbled encoding. Check PDF character encoding."
        )

    unique_words = set(w.lower() for w in words if len(w) > 3)
    if len(unique_words) < 5:
        return False, (
            f"{filename}: Very low vocabulary diversity "
            f"({len(unique_words)} unique words). Document may be "
            f"mostly images or symbols."
        )

    return True, "ok"


def validate_zip_contents(
    file_list: list[str]
) -> tuple[bool, list[str], str]:
    """
    Validates contents of a ZIP submission.
    Returns (is_valid, accepted_files, warning_message).
    """
    supported = {".pdf", ".docx", ".txt", ".doc"}
    accepted = []
    rejected = []

    for f in file_list:
        ext = "." + f.rsplit(".", 1)[-1].lower() if "." in f else ""
        if ext in supported:
            accepted.append(f)
        else:
            rejected.append(f)

    if not accepted:
        return False, [], (
            "ZIP contains no supported document files. "
            f"Found: {file_list}. "
            f"Supported: {supported}"
        )

    warning = ""
    if rejected:
        warning = (
            f"Skipped unsupported files: {rejected}. "
            f"Processing: {accepted}"
        )

    return True, accepted, warning

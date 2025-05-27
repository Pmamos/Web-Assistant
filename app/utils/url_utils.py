def normalize_url(url: str) -> str:
    """Normalizuje URL, dodając domyślny protokół, jeśli brak."""
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
    return url

def validate_url(url: str) -> bool:
    """Sprawdza, czy URL jest poprawny."""
    return url.startswith(('http://', 'https://'))
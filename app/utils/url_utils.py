import re
from typing import Optional
from urllib.parse import urljoin, urlparse

def clean_text(text: str) -> str:
    """Oczyszcza tekst, usuwając nadmiarowe spacje i znaki specjalne."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    return text

def normalize_url(url: str, base_url: Optional[str] = None) -> str:
    """Normalizuje URL, rozwiązując linki relatywne."""
    if not url:
        return ""
    if base_url and not url.startswith(('http://', 'https://')):
        url = urljoin(base_url, url)
    
    return url

def validate_url(url: str) -> bool:
    """Sprawdza, czy URL jest prawidłowy."""
    try:

        parsed = urlparse(url)

        return all([parsed.scheme in ['http', 'https'], parsed.netloc])
    except Exception:
        return False
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

POPULAR_SUFFIXES = [".com", ".pl", ".org", ".net", ".info", ".edu", ".gov", ".io", ".co"]

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
    
    # Dodaj schemat, jeśli brakuje
    if not url.startswith(('http://', 'https://')):
        url = "http://" + url
    
    print(f"Normalizuję URL: {url}")
    parsed = urlparse(url)

    # Dodaj końcówkę domeny, jeśli brakuje
    if parsed.netloc and not has_valid_suffix(parsed.netloc):
        corrected_url = try_possible_suffixes(parsed.netloc)
        if corrected_url:
            print(f"Poprawiono URL do: {corrected_url}")
            return corrected_url
    return url

def has_valid_suffix(netloc: str) -> bool:
    """Sprawdza, czy netloc zawiera kropkę i co najmniej jeden znak po niej."""
    if '.' not in netloc:
        return False
    suffix = netloc.rsplit('.', 1)[-1]
    return len(suffix) > 0


def try_possible_suffixes(domain: str) -> Optional[str]:
    """Próbuje znaleźć poprawną domenę spośród popularnych końcówek."""
    for suffix in POPULAR_SUFFIXES:
        test_url = f"http://{domain.rstrip('.')}{suffix}"
        try:
            response = requests.head(test_url, timeout=2)
            if response.status_code < 400:
                return test_url
        except requests.RequestException:
            continue
    return None

def validate_url(url: str) -> bool:
    """Sprawdza, czy URL jest prawidłowy."""
    try:

        parsed = urlparse(url)

        return all([parsed.scheme in ['http', 'https'], parsed.netloc])
    except Exception:
        return False
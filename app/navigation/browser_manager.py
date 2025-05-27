import logging
from typing import Dict, List, Optional
from urllib.parse import quote_plus
from ai.summarization import summarize_text
from utils.url_utils import normalize_url, validate_url
from web.scraper import scrape_page
from playwright_stealth import stealth_sync
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

class BrowserError(Exception):
    """Niestandardowy wyjątek dla błędów przeglądarki."""
    pass

def speak(text: str) -> None:
    """Funkcja placeholder do komunikatów głosowych."""
    print(f"SPEAK: {text}")

class BrowserManager:

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.current_url: Optional[str] = None
        self.history: List[str] = []
        self.history_index: int = -1
        self.home_page = "https://www.google.com"
        self.default_search_engine = "https://www.google.com/search?q="
        self.page_data_cache: Dict[str, Dict] = {}

    def initialize(self):
        """Inicjalizuje przeglądarkę w głównym wątku."""
        if self.playwright:
            self.playwright.stop()
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars"]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            permissions=["geolocation"]
        )
        self.page = self.context.new_page()
        stealth_sync(self.page)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def _get_page_data(self, url: str) -> Dict:
        """Pobiera dane ze strony, używając cache'a jeśli dostępne."""
        if url not in self.page_data_cache:
            self.page_data_cache[url] = scrape_page(self.page)
        return self.page_data_cache[url]

    def _update_history(self, url: str) -> None:
        """Aktualizuje historię bez duplikatów."""
        if self.history and self.history[-1] == url:
            return
        self.history.append(url)
        self.history_index = len(self.history) - 1
        self.current_url = url
        
    def open_page(self, url: str) -> Optional[str]:
        """Otwiera stronę po normalizacji i walidacji URL."""
        try:
            url = normalize_url(url)
            if not validate_url(url):
                raise BrowserError("Nieprawidłowy adres URL.")
            self.page.goto(url)
            self._update_history(url)
            speak(f"Otworzyłem stronę: {url}")
            logger.info(f"Otwarto stronę: {url}")
            return url
        except Exception as e:
            logger.error(f"Błąd otwierania strony: {e}")
            speak("Nie udało się otworzyć strony.")
            raise BrowserError(str(e))
    
    def search_web(self, query: str) -> Optional[str]:
        """Wykonuje wyszukiwanie w sieci."""
        try:
            if not query:
                raise BrowserError("Brak frazy do wyszukania.")
            encoded_query = quote_plus(query)
            search_url = f"{self.default_search_engine}{encoded_query}"
            self.page.goto(search_url)
            self._update_history(search_url)
            speak(f"Wyszukuję: {query}")
            logger.info(f"Wyszukano: {query} -> {search_url}")
            return search_url
        except Exception as e:
            logger.error(f"Błąd wyszukiwania: {e}")
            speak("Nie udało się wykonać wyszukiwania.")
            raise BrowserError(str(e))

    def go_back(self) -> Optional[str]:
        """Cofa się w historii przeglądania."""
        try:
            if self.history_index > 0:
                self.history_index -= 1
                url = self.history[self.history_index]
                self.page.goto(url)
                speak(f"Wróciłem do: {url}")
                logger.info(f"Cofnięto do: {url}")
                return url
            speak("Brak poprzednich stron.")
            return None
        except Exception as e:
            logger.error(f"Błąd cofania: {e}")
            speak("Nie udało się cofnąć.")
            raise BrowserError(str(e))
    
    def go_forward(self) -> Optional[str]:
        """Przechodzi do przodu w historii przeglądania."""
        try:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                url = self.history[self.history_index]
                self.page.goto(url)
                speak(f"Przeszedłem do: {url}")
                logger.info(f"Przejście do przodu: {url}")
                return url
            speak("Brak następnych stron.")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do przodu: {e}")
            speak("Nie udało się przejść do przodu.")
            raise BrowserError(str(e))
    
    def refresh_page(self) -> Optional[str]:
        """Odświeża bieżącą stronę."""
        try:
            if self.current_url:
                self.page.reload()
                speak("Odświeżam stronę.")
                logger.info(f"Odświeżono stronę: {self.current_url}")
                return self.current_url
            speak("Brak aktywnej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd odświeżania strony: {e}")
            speak("Nie udało się odświeżyć strony.")
            raise BrowserError(str(e))
        
    def open_browser(self) -> str:
        try:
            self.page.goto(self.home_page)
            self._update_history(self.home_page)
            speak("Przeglądarka została uruchomiona")
            return self.home_page
        except Exception as e:
            logger.error(f"Błąd otwierania przeglądarki: {e}")
            speak("Nie udało się uruchomić przeglądarki")
            return None
    def close_browser(self) -> None:
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self.playwright = None
            self.browser = None
            self.context = None
            self.page = None
            self.current_url = None
            self.history.clear()
            self.page_data_cache.clear()
            self.history_index = -1
            speak("Przeglądarka została zamknięta.")
        except Exception as e:
            logger.error(f"Błąd zamykania przeglądarki: {e}")
            speak("Nie udało się zamknąć przeglądarki.")
            raise BrowserError(str(e))
    
    def read_headings(self) -> Optional[str]:
        if not self.current_url:
            speak("Najpierw przejdź na stronę.")
            return None
        try:
            page_data = self._get_page_data(self.current_url)
            headings = page_data.get('headings', [])
            if not headings:
                speak("Na tej stronie nie ma nagłówków.")
                return None
            heading_text = "\n".join([f"{h['level']}: {h['text']}" for h in headings])
            speak(f"Nagłówki na stronie: {heading_text}")
            return heading_text
        except Exception as e:
            logger.error(f"Błąd odczytu nagłówków: {e}")
            speak("Nie udało się odczytać nagłówków.")
            return None
        
    def summarize_page(self) -> Optional[str]:
        if not self.current_url:
            speak("Najpierw przejdź na stronę.")
            return None
        try:
            page_data = self._get_page_data(self.current_url)
            text = page_data.get('text', '')
            if not text:
                speak("Na tej stronie nie ma tekstu do streszczenia.")
                return None
            summary = summarize_text(text)
            speak(f"Streszczenie strony: {summary}")
            return summary
        except Exception as e:
            logger.error(f"Błąd streszczania strony: {e}")
            speak("Nie udało się streścić strony.")
            return None
    
    def read_content(self) -> Optional[str]:
        if not self.current_url:
            speak("Najpierw otwórz stronę.")
            return None
        try:
            page_data = self._get_page_data(self.page)
            content = page_data.get('text', '')
            if not content:
                speak("Na tej stronie nie ma treści do odczytania.")
                return None
            speak(f"Oto treść strony: {content[:500]}...")
            return content
        except Exception as e:
            logger.error(f"Błąd odczytu treści: {e}")
            speak("Nie udało się odczytać treści.")
            return None
    
    def go_home(self) -> Optional[str]:
        try:
            self.page.goto(self.home_page)
            self._update_history(self.home_page)
            speak("Wróciłem do strony domowej.")
            return self.home_page
        except Exception as e:
            logger.error(f"Błąd powrotu do strony domowej: {e}")
            speak("Nie udało się wrócić do strony domowej.")
            return None
    
    def show_history(self) -> Optional[str]:
        if not self.history:
            speak("Historia jest pusta.")
            return None
        history_str = ", ".join(self.history[-5:])
        speak(f"Ostatnie strony: {history_str}")
        return history_str
    
    def open_new_tab(self, url: str) -> Optional[str]:
        try:
            url = normalize_url(url)
            if not validate_url(url):
                speak("Nieprawidłowy adres URL.")
                return None
            new_page = self.context.new_page()
            new_page.goto(url)
            self._update_history(url)
            speak(f"Otworzyłem {url} w nowej karcie.")
            return url
        except Exception as e:
            logger.error(f"Błąd otwierania nowej karty: {e}")
            speak("Nie udało się otworzyć nowej karty.")
            return None
    
    def go_to_section(self, section_name: str) -> Optional[str]:
        try:
            if not section_name:
                speak("Proszę podać nazwę sekcji.")
                return None
            page_data = self._get_page_data(self.page)
            sections = page_data.get('sections', [])
            for section in sections:
                if section_name.lower() in section['name'].lower():
                    self.page.evaluate(f"window.scrollTo(0, document.getElementById('{section['id']}').offsetTop)")
                    speak(f"Przeszedłem do sekcji: {section['name']}")
                    return section['name']
            speak(f"Nie znaleziono sekcji: {section_name}")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do sekcji: {e}")
            speak("Nie udało się przejść do sekcji.")
            return None
    
    def get_current_url(self) -> Optional[str]:
        """Zwraca aktualny URL przeglądarki."""
        try:
            speak(f"Aktualny adres URL to: {self.current_url}")
        except Exception as e:
            logger.error(f"Błąd pobierania aktualnego URL: {e}")
            speak("Nie udało się pobrać aktualnego adresu URL.")
            raise BrowserError(str(e))
        
    def describe_image(self, image_index: int) -> Optional[str]:
        try:
            page_data = self._get_page_data(self.page)
            images = page_data.get('images', [])
            if image_index < 1 or image_index > len(images):
                speak("Nieprawidłowy numer obrazu.")
                return None
            image_url = images[image_index - 1]['src']
            description = "Opis obrazu"  # Placeholder
            speak(f"Opis obrazu: {description}")
            return description
        except Exception as e:
            logger.error(f"Błąd opisywania obrazu: {e}")
            speak("Nie udało się opisać obrazu.")
            return None

    def next_page(self) -> Optional[str]:
        try:
            next_button = self.page.query_selector('a[rel="next"]') or self.page.query_selector('a:text("Następna")')
            if next_button:
                next_button.click()
                self._update_history(self.page.url)
                speak("Przeszedłem do następnej strony.")
                return self.page.url
            speak("Nie znaleziono przycisku następnej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do następnej strony: {e}")
            speak("Nie udało się przejść do następnej strony.")
            return None

    def previous_page(self) -> Optional[str]:
        try:
            prev_button = self.page.query_selector('a[rel="prev"]') or self.page.query_selector('a:text("Poprzednia")')
            if prev_button:
                prev_button.click()
                self._update_history(self.page.url)
                speak("Przeszedłem do poprzedniej strony.")
                return self.page.url
            speak("Nie znaleziono przycisku poprzedniej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do poprzedniej strony: {e}")
            speak("Nie udało się przejść do poprzedniej strony.")
            return None
    
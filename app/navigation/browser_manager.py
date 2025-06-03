import logging
from typing import Dict, List, Optional
from urllib.parse import quote_plus
from ai.summarization import summarize_text
from web.scraper import WebScraper
from voice.text_to_speech import TTSWrapper
from utils.url_utils import normalize_url, validate_url
from playwright_stealth import stealth_sync
from playwright.sync_api import sync_playwright
import wikipediaapi
from pytube import Search

logger = logging.getLogger(__name__)

class BrowserError(Exception):
    """Niestandardowy wyjątek dla błędów przeglądarki."""
    pass

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
        self.tts = TTSWrapper()
        self.scraper = None
        self.wiki = wikipediaapi.Wikipedia('WebAssistBot/1.0', 'pl')
        self.youtube_results = []

    def initialize(self):
        """Inicjalizuje przeglądarkę w głównym wątku."""
        try:
            if self.playwright:
                self.close_browser()
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
            self.scraper = WebScraper(self.page)
            logger.info("Przeglądarka zainicjalizowana.")
        except Exception as e:
            logger.error(f"Błąd inicjalizacji przeglądarki: {e}")
            self.tts.speak("Nie udało się zainicjalizować przeglądarki.")
            raise BrowserError(str(e))

    def _get_page_data(self, url: str) -> Dict:
        """Pobiera dane ze strony, używając cache'a jeśli dostępne."""
        try:
            if not url:
                url = self.current_url
            print(f"Pobieranie danych dla URL: {url}")
            if url not in self.page_data_cache:
                self.page_data_cache[url] = self.scraper.scrape_page(url)
            return self.page_data_cache[url] or {}
        except Exception as e:
            logger.error(f"Błąd pobierania danych strony: {e}")
            return {}

    def _update_history(self, url: str) -> None:
        """Aktualizuje historię bez duplikatów."""
        if self.history and self.history[-1] == url:
            return
        self.history.append(url)
        self.history_index = len(self.history) - 1
        self.current_url = url

    def open_page(self, url: str, isSpeak = True) -> Optional[str]:
        """Otwiera stronę po normalizacji i walidacji URL."""
        try:
            url = normalize_url(url)
            if not validate_url(url):
                self.tts.speak("Nieprawidłowy adres URL.")
                raise BrowserError("Nieprawidłowy adres URL.")
            self.page.goto(url, wait_until="domcontentloaded")
            self._update_history(url)
            if isSpeak:
                self.tts.speak(f"Otworzono stronę: {url}")
            return url
        except Exception as e:
            logger.error(f"Błąd otwierania strony: {e}")
            self.tts.speak("Nie udało się otworzyć strony.")
            raise BrowserError(str(e))

    def search_web(self, query: str) -> Optional[str]:
        """Wykonuje wyszukiwanie w sieci."""
        try:
            if not query:
                self.tts.speak("Brak frazy do wyszukania.")
                raise BrowserError("Brak frazy do wyszukania.")
            encoded_query = quote_plus(query)
            search_url = f"{self.default_search_engine}{encoded_query}"
            self.page.goto(search_url, wait_until="domcontentloaded")
            self._update_history(search_url)
            self.tts.speak(f"Wyszukano: {query}")
            return search_url
        except Exception as e:
            logger.error(f"Błąd wyszukiwania: {e}")
            self.tts.speak("Nie udało się wykonać wyszukiwania.")
            raise BrowserError(str(e))

    def read_search_results(self, max_results: int = 5) -> Optional[List[Dict]]:
        """Odczytuje wyniki wyszukiwania."""
        try:
            if not self.current_url or not any(engine in self.current_url for engine in ["google.com/search", "bing.com/search", "duckduckgo.com"]):
                self.tts.speak("Najpierw wykonaj wyszukiwanie.")
                return None

            page_data = self._get_page_data(self.current_url)
            search_results = page_data.get('search_results', [])
            if not search_results:
                self.tts.speak("Nie znaleziono wyników wyszukiwania.")
                return None

            results = []
            for i, result in enumerate(search_results[:max_results], 1):
                title = result.get('title', 'Brak tytułu')
                url = result.get('url')
                if url and validate_url(url):
                    results.append({
                        "index": i,
                        "title": title,
                        "url": url
                    })

            if not results:
                self.tts.speak("Nie znaleziono prawidłowych wyników wyszukiwania.")
                return None

            result_text = "\n".join([f"Wynik {r['index']}: {r['title']}" for r in results])
            self.tts.speak(f"Wyniki wyszukiwania:\n{result_text}")
            return results
        except Exception as e:
            logger.error(f"Błąd odczytu wyników wyszukiwania: {e}")
            self.tts.speak("Wystąpił błąd podczas odczytywania wyników wyszukiwania.")
            return None

    def open_search_result(self, index: int) -> Optional[str]:
        """Otwiera wynik wyszukiwania o podanym numerze."""
        try:
            results = self.read_search_results(max_results=10)
            if not results:
                self.tts.speak("Brak wyników wyszukiwania.")
                return None
            for result in results:
                if result["index"] == index:
                    url = result["url"]
                    self.page.goto(url, wait_until="domcontentloaded")
                    self._update_history(url)
                    self.tts.speak(f"Otworzono wynik {index}: {result['title']}")
                    return url
            self.tts.speak(f"Nie znaleziono wyniku o numerze {index}.")
            return None
        except Exception as e:
            logger.error(f"Błąd otwierania wyniku wyszukiwania: {e}")
            self.tts.speak("Nie udało się otworzyć wyniku wyszukiwania.")
            return None

    def read_page_links(self, max_links: int = 5) -> Optional[List[Dict]]:
        """Odczytuje linki na bieżącej stronie."""
        try:
            if not self.current_url:
                self.tts.speak("Najpierw otwórz stronę.")
                return None
            page_data = self._get_page_data(self.current_url)
            links = page_data.get('links', [])[:max_links]
            if not links:
                self.tts.speak("Nie znaleziono linków na stronie.")
                return None
            link_text = "\n".join([f"Link {i+1}: {link['text']}" for i, link in enumerate(links)])
            self.tts.speak(f"Linki na stronie:\n{link_text}")
            return [{"index": i+1, "text": link['text'], "url": link['url']} for i, link in enumerate(links)]
        except Exception as e:
            logger.error(f"Błąd odczytu linków: {e}")
            self.tts.speak("Nie udało się odczytać linków.")
            return None

    def open_page_link(self, index: int) -> Optional[str]:
        """Otwiera link o podanym numerze na stronie."""
        try:
            links = self.read_page_links(max_results=10)
            if not links:
                self.tts.speak("Brak linków na stronie.")
                return None
            for link in links:
                if link["index"] == index:
                    url = link["url"]
                    self.page.goto(url, wait_until="domcontentloaded")
                    self._update_history(url)
                    self.tts.speak(f"Otworzono link {index}: {link['text']}")
                    return url
            self.tts.speak(f"Nie znaleziono linku o numerze {index}.")
            return None
        except Exception as e:
            logger.error(f"Błąd otwierania linku: {e}")
            self.tts.speak("Nie udało się otworzyć linku.")
            return None

    def go_back(self) -> Optional[str]:
        """Cofa się w historii przeglądania."""
        try:
            if self.history_index > 0:
                self.history_index -= 1
                url = self.history[self.history_index]
                self.page.goto(url, wait_until="domcontentloaded")
                self.tts.speak(f"Wrócono do: {url}")
                return url
            self.tts.speak("Brak poprzednich stron.")
            return None
        except Exception as e:
            logger.error(f"Błąd cofania: {e}")
            self.tts.speak("Nie udało się cofnąć.")
            raise BrowserError(str(e))

    def go_forward(self) -> Optional[str]:
        """Przechodzi do przodu w historii przeglądania."""
        try:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                url = self.history[self.history_index]
                self.page.goto(url, wait_until="domcontentloaded")
                self.tts.speak(f"Przejście do: {url}")
                return url
            self.tts.speak("Brak następnych stron.")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do przodu: {e}")
            self.tts.speak("Nie udało się przejść do przodu.")
            raise BrowserError(str(e))

    def refresh_page(self) -> Optional[str]:
        """Odświeża bieżącą stronę."""
        try:
            if self.current_url:
                self.page.reload(wait_until="domcontentloaded")
                self.page_data_cache.pop(self.current_url, None)
                self.tts.speak("Strona odświeżona.")
                return self.current_url
            self.tts.speak("Brak aktywnej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd odświeżania strony: {e}")
            self.tts.speak("Nie udało się odświeżyć strony.")
            raise BrowserError(str(e))

    def open_browser(self) -> Optional[str]:
        """Otwiera przeglądarkę na stronie domowej."""
        try:
            self.page.goto(self.home_page, wait_until="domcontentloaded")
            self._update_history(self.home_page)
            self.tts.speak("Przeglądarka uruchomiona.")
            return self.home_page
        except Exception as e:
            logger.error(f"Błąd otwierania przeglądarki: {e}")
            self.tts.speak("Nie udało się uruchomić przeglądarki.")
            raise BrowserError(str(e))

    def close_browser(self) -> None:
        """Zamyka przeglądarkę i czyści zasoby."""
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
            self.youtube_results = []
            self.tts.speak("Przeglądarka zamknięta.")
        except Exception as e:
            logger.error(f"Błąd zamykania przeglądarki: {e}")
            self.tts.speak("Nie udało się zamknąć przeglądarki.")
            raise BrowserError(str(e))

    def read_headings(self) -> Optional[str]:
        """Odczytuje nagłówki na bieżącej stronie."""
        try:
            if not self.current_url:
                self.tts.speak("Najpierw otwórz stronę.")
                return None
            page_data = self._get_page_data(self.current_url)
            headings = page_data.get('headings', [])
            if not headings:
                self.tts.speak("Brak nagłówków na stronie.")
                return None
            heading_text = "\n".join([f"Poziom {h['level']}: {h['text']}" + (f" ({h['aria_label']})" if h['aria_label'] else "") for h in headings])
            self.tts.speak(f"Nagłówki na stronie:\n{heading_text}")
            return heading_text
        except Exception as e:
            logger.error(f"Błąd odczytu nagłówków: {e}")
            self.tts.speak("Nie udało się odczytać nagłówków.")
            return None

    def summarize_page(self) -> Optional[str]:
        """Streszcza treść bieżącej strony."""
        try:
            if not self.current_url:
                self.tts.speak("Najpierw otwórz stronę.")
                return None
            if "wikipedia.org" in self.current_url:
                wiki_page = self.wiki.page(self.current_url.split("/")[-1])
                if wiki_page.exists():
                    summary = wiki_page.summary[:500] + ("..." if len(wiki_page.summary) > 500 else "")
                    self.tts.speak(f"Streszczenie artykułu z Wikipedii: {summary}")
                    return summary
            page_data = self._get_page_data(self.current_url)
            text = page_data.get('content', {}).get('text', '')
            if not text:
                self.tts.speak("Brak treści do streszczenia.")
                return None
            summary = summarize_text(text)
            self.tts.speak(f"Streszczenie strony: {summary}")
            return summary
        except Exception as e:
            logger.error(f"Błąd streszczania strony: {e}")
            self.tts.speak("Nie udało się streścić strony.")
            return None

    def read_content(self) -> Optional[str]:
        """Odczytuje treść bieżącej strony."""
        try:
            if not self.current_url:
                self.tts.speak("Najpierw otwórz stronę.")
                return None
            if "wikipedia.org" in self.current_url:
                wiki_page = self.wiki.page(self.current_url.split("/")[-1])
                if wiki_page.exists():
                    content = wiki_page.text[:500] + ("..." if len(wiki_page.text) > 500 else "")
                    self.tts.speak(f"Treść artykułu z Wikipedii: {content}")
                    return content
            page_data = self._get_page_data(self.current_url)
            content = page_data.get('content', {}).get('text', '')
            if not content:
                self.tts.speak("Brak treści do odczytania.")
                return None
            content_preview = content[:500] + ("..." if len(content) > 500 else "")
            self.tts.speak(f"Treść strony: {content_preview}")
            return content
        except Exception as e:
            logger.error(f"Błąd odczytu treści: {e}")
            self.tts.speak("Nie udało się odczytać treści.")
            return None

    def go_home(self) -> Optional[str]:
        """Wraca do strony domowej."""
        try:
            self.page.goto(self.home_page, wait_until="domcontentloaded")
            self._update_history(self.home_page)
            self.tts.speak("Wrócono do strony domowej.")
            return self.home_page
        except Exception as e:
            logger.error(f"Błąd powrotu do strony domowej: {e}")
            self.tts.speak("Nie udało się wrócić do strony domowej.")
            raise BrowserError(str(e))

    def show_history(self) -> Optional[str]:
        """Pokazuje ostatnie strony z historii."""
        if not self.history:
            self.tts.speak("Historia jest pusta.")
            return None
        history_str = ", ".join(self.history[-5:])
        self.tts.speak(f"Ostatnie strony: {history_str}")
        return history_str

    def open_new_tab(self, url: str) -> Optional[str]:
        """Otwiera nową kartę z podanym URL."""
        try:
            url = normalize_url(url)
            if not validate_url(url):
                self.tts.speak("Nieprawidłowy adres URL.")
                return None
            new_page = self.context.new_page()
            new_page.goto(url, wait_until="domcontentloaded")
            self.page = new_page
            self.scraper = WebScraper(self.page)
            self._update_history(url)
            self.tts.speak(f"Otworzono {url} w nowej karcie.")
            return url
        except Exception as e:
            logger.error(f"Błąd otwierania nowej karty: {e}")
            self.tts.speak("Nie udało się otworzyć nowej karty.")
            return None

    def go_to_section(self, section_name: str) -> Optional[str]:
        """Przechodzi do sekcji o podanej nazwie."""
        try:
            if not section_name:
                self.tts.speak("Podaj nazwę sekcji.")
                return None
            if "wikipedia.org" in self.current_url:
                wiki_page = self.wiki.page(self.current_url.split("/")[-1])
                if wiki_page.exists():
                    section = wiki_page.section_by_title(section_name)
                    if section:
                        self.tts.speak(f"Przejście do sekcji: {section_name}")
                        return section_name
                    self.tts.speak(f"Nie znaleziono sekcji: {section_name}")
                    return None
            page_data = self._get_page_data(self.current_url)
            sections = page_data.get('sections', [])
            for section in sections:
                if section_name.lower() in section['name'].lower():
                    section_id = section.get('id')
                    if section_id:
                        self.page.evaluate(f"document.getElementById('{section_id}')?.scrollIntoView()")
                    else:
                        self.tts.speak(f"Sekcja {section['name']} nie ma identyfikatora do przewinięcia.")
                    self.tts.speak(f"Przejście do sekcji: {section['name']}")
                    return section['name']
            self.tts.speak(f"Nie znaleziono sekcji: {section_name}")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do sekcji: {e}")
            self.tts.speak("Nie udało się przejść do sekcji.")
            return None

    def read_forms(self) -> Optional[List[Dict]]:
        """Odczytuje formularze na bieżącej stronie."""
        try:
            if not self.current_url:
                self.tts.speak("Najpierw otwórz stronę.")
                return None
            page_data = self._get_page_data(self.current_url)
            forms = page_data.get('forms', [])
            if not forms:
                self.tts.speak("Brak formularzy na stronie.")
                return None
            form_text = []
            for i, form in enumerate(forms, 1):
                fields = "\n".join([f"Pole {f['label']}: typ {f['type']}" for f in form['fields']])
                buttons = ", ".join([b['text'] for b in form['submit_buttons']])
                form_text.append(f"Formularz {i}:\nPola:\n{fields}\nPrzyciski: {buttons}")
            self.tts.speak("\n".join(form_text))
            return forms
        except Exception as e:
            logger.error(f"Błąd odczytu formularzy: {e}")
            self.tts.speak("Nie udało się odczytać formularzy.")
            return None

    def describe_image(self, image_index: int) -> Optional[str]:
        """Opisuje obraz o podanym numerze."""
        try:
            if not self.current_url:
                self.tts.speak("Najpierw otwórz stronę.")
                return None
            page_data = self._get_page_data(self.current_url)
            images = page_data.get('images', [])
            if image_index < 1 or image_index > len(images):
                self.tts.speak("Nieprawidłowy numer obrazu.")
                return None
            image = images[image_index - 1]
            description = image.get('alt', 'Brak opisu')
            self.tts.speak(f"Obraz {image_index}: {description}")
            return description
        except Exception as e:
            logger.error(f"Błąd opisywania obrazu: {e}")
            self.tts.speak("Nie udało się opisać obrazu.")
            return None

    def next_page(self) -> Optional[str]:
        """Przechodzi do następnej strony (np. w wynikach wyszukiwania)."""
        try:
            next_button = self.page.query_selector('a[rel="next"]') or self.page.query_selector('a:text("Następna")')
            if next_button:
                next_button.click()
                self.page.wait_for_load_state("domcontentloaded")
                self._update_history(self.page.url)
                self.page_data_cache.pop(self.current_url, None)
                self.tts.speak("Przejście do następnej strony.")
                return self.page.url
            self.tts.speak("Brak przycisku następnej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do następnej strony: {e}")
            self.tts.speak("Nie udało się przejść do następnej strony.")
            return None

    def previous_page(self) -> Optional[str]:
        """Przechodzi do poprzedniej strony (np. w wynikach wyszukiwania)."""
        try:
            prev_button = self.page.query_selector('a[rel="prev"]') or self.page.query_selector('a:text("Poprzednia")')
            if prev_button:
                prev_button.click()
                self.page.wait_for_load_state("domcontentloaded")
                self._update_history(self.page.url)
                self.page_data_cache.pop(self.current_url, None)
                self.tts.speak("Przejście do poprzedniej strony.")
                return self.page.url
            self.tts.speak("Brak przycisku poprzedniej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd przechodzenia do poprzedniej strony: {e}")
            self.tts.speak("Nie udało się przejść do poprzedniej strony.")
            return None

    def get_current_url(self) -> Optional[str]:
        """Zwraca aktualny URL przeglądarki."""
        try:
            if self.current_url:
                self.tts.speak(f"Aktualny adres: {self.current_url}")
                return self.current_url
            self.tts.speak("Brak aktywnej strony.")
            return None
        except Exception as e:
            logger.error(f"Błąd pobierania aktualnego URL: {e}")
            self.tts.speak("Nie udało się pobrać aktualnego adresu.")
            raise BrowserError(str(e))

    def search_youtube(self, query: str) -> Optional[str]:
        """Wyszukuje filmy na YouTube i zapisuje wyniki."""
        try:
            search = Search(query)
            self.youtube_results = search.results[:10]
            if not self.youtube_results:
                self.tts.speak(f"Nie znaleziono filmów na temat: {query}")
                return None
            result_text = "\n".join([f"Film {i+1}: {video.title}" for i, video in enumerate(self.youtube_results)])
            self.tts.speak(f"Wyniki wyszukiwania na YouTube:\n{result_text}")
            return query
        except Exception as e:
            logger.error(f"Błąd wyszukiwania na YouTube: {e}")
            self.tts.speak("Nie udało się wyszukać filmów na YouTube.")
            return None

    def read_youtube_results(self) -> Optional[str]:
        """Odczytuje wyniki wyszukiwania filmów na YouTube."""
        try:
            if not self.youtube_results:
                self.tts.speak("Najpierw wyszukaj filmy na YouTube.")
                return None
            result_text = "\n".join([f"Film {i+1}: {video.title}" for i, video in enumerate(self.youtube_results)])
            self.tts.speak(f"Wyniki wyszukiwania na YouTube:\n{result_text}")
            return result_text
        except Exception as e:
            logger.error(f"Błąd odczytu wyników YouTube: {e}")
            self.tts.speak("Nie udało się odczytać wyników YouTube.")
            return None

    def open_youtube_video(self, index: int) -> Optional[str]:
        """Otwiera film z YouTube o podanym numerze."""
        try:
            if not self.youtube_results or index < 1 or index > len(self.youtube_results):
                self.tts.speak("Nieprawidłowy numer filmu lub brak wyników wyszukiwania.")
                return None
            video = self.youtube_results[index - 1]
            self.open_page(video.watch_url)
            self.tts.speak(f"Otworzono film: {video.title}")
            return video.watch_url
        except Exception as e:
            logger.error(f"Błąd otwierania filmu YouTube: {e}")
            self.tts.speak("Nie udało się otworzyć filmu.")
            return None
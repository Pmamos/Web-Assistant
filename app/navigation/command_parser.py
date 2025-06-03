import json
import logging
import re
from typing import Callable, Dict, Optional
import wikipediaapi
from pytube import Search
from urllib.parse import quote_plus

from voice.text_to_speech import TTSWrapper
from navigation.browser_manager import BrowserManager
from navigation.thread_queue import ThreadSafeQueue

logger = logging.getLogger(__name__)

class CommandError(Exception):
    """Niestandardowy wyjątek dla błędów komend."""
    pass

class CommandParser:
    def __init__(self, browser_manager: BrowserManager, command_queue: ThreadSafeQueue):
        self.browser_manager = browser_manager
        self.command_queue = command_queue
        self.tts = TTSWrapper()
        self.wiki = wikipediaapi.Wikipedia('WebAssistBot/1.0', 'pl')
        self.command_patterns: Dict[str, Callable] = {
            r"wejdź na stronę\s+(.*)": lambda url: self.browser_manager.open_page(url),
            r"otwórz przeglądarkę": self.browser_manager.open_browser,
            r"otwórz stronę\s+(.*)": lambda url: self.browser_manager.open_page(url),
            r"cofnij": self.browser_manager.go_back,
            r"ponów": self.browser_manager.go_forward,
            r"przeczytaj nagłówki": self.browser_manager.read_headings,
            r"streść stronę": self.browser_manager.summarize_page,
            r"odśwież stronę": self.browser_manager.refresh_page,
            r"pokaż historię": self.browser_manager.show_history,
            r"przeczytaj treść": self.browser_manager.read_content,
            r"domyślna strona": self.browser_manager.go_home,
            r"zamknij przeglądarkę": self.browser_manager.close_browser,
            r"przejdź do sekcji\s+(.*)": lambda section: self.browser_manager.go_to_section(section),
            r"opisz obraz\s+(\d+)": lambda index: self.browser_manager.describe_image(int(index)),
            r"przejdź do następnej strony": self.browser_manager.next_page,
            r"przejdź do poprzedniej strony": self.browser_manager.previous_page,
            r"otwórz w nowej karcie\s+(.*)": lambda url: self.browser_manager.open_new_tab(url),
            r"przejdź do\s+(.*)": lambda url: self.browser_manager.open_page(url),
            r"zapytaj model\s+(.*)": lambda question: self._ask_model(question),
            r"znajdź na stronie\s+(.*)": lambda phrase: self._find_on_page(phrase),
            r"przeczytaj wyniki wyszukiwania": self.browser_manager.read_search_results,
            r"otwórz wynik\s+(\d+)": lambda index: self.browser_manager.open_search_result(int(index)),
            r"przeczytaj linki": self.browser_manager.read_page_links,
            r"otwórz link\s+(\d+)": lambda index: self.browser_manager.open_page_link(int(index)),
            r"wyszukaj na wikipedii\s+(.*)": lambda query: self._search_wikipedia(query),
            r"pokaż sekcje artykułu": self._read_wikipedia_sections,
            r"przeczytaj sekcję\s+(.*)": lambda section: self._read_wikipedia_section(section),
            r"wyszukaj filmy na youtube\s+(.*)": lambda query: self._search_youtube(query),
            r"przeczytaj filmy": self._read_youtube_results,
            r"otwórz film\s+(\d+)": lambda index: self._open_youtube_video(int(index)),
            r"przeczytaj formularze": self.browser_manager.read_forms,
            r"wyszukaj\s+(.*)": lambda query: self.browser_manager.search_web(query),
        }
        self.current_wiki_page = None
        self.youtube_results = []

    def parse_command(self, command: str) -> None:
        """Parsuje komendę i dodaje ją do kolejki."""
        command = command.lower().strip()
        for pattern, handler in self.command_patterns.items():
            match = re.match(pattern, command)
            if match:
                args = match.groups()
                self.command_queue.put((handler, args, {}))
                logger.info(f"Sparsowano komendę: {command}")
                return
        logger.warning(f"Nieznana komenda: {command}")
        self.tts.speak("Nie rozpoznano komendy.")
        raise CommandError(f"Nieznana komenda: {command}")

    def _search_wikipedia(self, query: str) -> Optional[str]:
        """Wyszukuje artykuł na Wikipedii i odczytuje jego streszczenie."""
        try:
            self.current_wiki_page = self.wiki.page(query)
            if not self.current_wiki_page.exists():
                self.tts.speak(f"Nie znaleziono artykułu na temat: {query}")
                return None
            summary = self.current_wiki_page.summary[:500] + ("..." if len(self.current_wiki_page.summary) > 500 else "")
            self.tts.speak(f"Streszczenie artykułu z Wikipedii: {summary}")
            self.browser_manager.open_page(self.current_wiki_page.fullurl, isSpeak=False)
            return summary
        except Exception as e:
            logger.error(f"Błąd wyszukiwania na Wikipedii: {e}")
            self.tts.speak("Nie udało się wyszukać artykułu na Wikipedii.")
            return None

    def _read_wikipedia_sections(self) -> Optional[str]:
        """Odczytuje sekcje artykułu z Wikipedii."""
        try:
            if not self.current_wiki_page:
                self.tts.speak("Najpierw wyszukaj artykuł na Wikipedii.")
                return None
            
            
            sections = list(self.current_wiki_page.sections)
            print(f"Znaleziono {len(sections)} sekcji w artykule.")
            if not sections:
                self.tts.speak("Artykuł nie zawiera sekcji.")
                return None
            section_text = "\n".join([f"Sekcja: {s}" for s in sections])
            self.tts.speak(f"Sekcje artykułu:\n{section_text}")
            return section_text
        except Exception as e:
            logger.error(f"Błąd odczytu sekcji Wikipedii: {e}")
            self.tts.speak("Nie udało się odczytać sekcji artykułu.")
            return None

    def _read_wikipedia_section(self, section_name: str) -> Optional[str]:
        """Odczytuje treść konkretnej sekcji artykułu z Wikipedii."""
        try:
            if not self.current_wiki_page:
                self.tts.speak("Najpierw wyszukaj artykuł na Wikipedii.")
                return None
            print(f"Szukam sekcji: {section_name.title()}")
            section = self.current_wiki_page.section_by_title(section_name.title())
            if not section:
                self.tts.speak(f"Nie znaleziono sekcji: {section_name}")
                return None
            text = section.text[:500] + ("..." if len(section.text) > 500 else "")
            print(f"Odczytano sekcję: {section_name}")
            print(f"Treść sekcji: {text}")
            self.tts.speak(f"Sekcja {section_name}: {text}")
            return text
        except Exception as e:
            logger.error(f"Błąd odczytu sekcji Wikipedii: {e}")
            self.tts.speak("Nie udało się odczytać sekcji.")
            return None

    def _search_youtube(self, query: str) -> Optional[str]:
        """Wyszukuje filmy na YouTube, otwiera stronę wyników i zapisuje wyniki."""
        try:
            # Otwórz stronę wyników wyszukiwania YouTube
            encoded_query = quote_plus(query)
            print(f"Wyszukuję filmy na YouTube: {encoded_query}")
            self.tts.speak(f"Wyszukuję filmy na YouTube: {query}")
            youtube_search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
            self.browser_manager.open_page(youtube_search_url, isSpeak=False)
            
            # Pobierz wyniki za pomocą pytube
            search = Search(query)
            self.youtube_results = search.results[:10]  # Ogranicz do 10 wyników
            if not self.youtube_results:
                self.tts.speak(f"Nie znaleziono filmów na temat: {query}")
                return None
            
            # Odczytaj wyniki
            self._read_youtube_results()
            return query
        except Exception as e:
            logger.error(f"Błąd wyszukiwania na YouTube: {e}")
            self.tts.speak("Nie udało się wyszukać filmów na YouTube.")
            return None

    def _read_youtube_results(self) -> Optional[str]:
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

    def _open_youtube_video(self, index: int) -> Optional[str]:
        """Otwiera film z YouTube o podanym numerze."""
        try:
            if not self.youtube_results or index < 1 or index > len(self.youtube_results):
                self.tts.speak("Nieprawidłowy numer filmu lub brak wyników wyszukiwania.")
                return None
            video = self.youtube_results[index - 1]
            self.browser_manager.open_page(video.watch_url)
            self.tts.speak(f"Otworzono film: {video.title}")
            return video.watch_url
        except Exception as e:
            logger.error(f"Błąd otwierania filmu YouTube: {e}")
            self.tts.speak("Nie udało się otworzyć filmu.")
            return None

    def _ask_model(self, question: str) -> Optional[str]:
        """Zadaje pytanie modelowi AI na podstawie treści strony."""
        try:
            page_data = self.browser_manager._get_page_data(self.browser_manager.current_url)
            text = page_data.get('content', {}).get('text', '')
            if not text:
                self.tts.speak("Brak treści do analizy.")
                return None
            answer = ask_ai_model(question, text)
            self.tts.speak(f"Odpowiedź: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Błąd zadawania pytania modelowi: {e}")
            self.tts.speak("Nie udało się uzyskać odpowiedzi.")
            return None

    def _find_on_page(self, phrase: str) -> Optional[str]:
        """Wyszukuje frazę na stronie."""
        try:
            page_data = self.browser_manager._get_page_data(self.browser_manager.current_url)
            text = page_data.get('content', {}).get('text', '')
            if not text:
                self.tts.speak("Brak treści do przeszukania.")
                return None
            if phrase.lower() in text.lower():
                self.tts.speak(f"Znaleziono frazę: {phrase}")
                return phrase
            self.tts.speak(f"Nie znaleziono frazy: {phrase}")
            return None
        except Exception as e:
            logger.error(f"Błąd wyszukiwania frazy: {e}")
            self.tts.speak("Nie udało się wyszukać frazy.")
            return None

# Placeholder dla integracji z modelem AI
def ask_ai_model(question: str, context: str) -> str:
    """Zadaje pytanie modelowi AI."""
    return "Odpowiedź od modelu AI (placeholder)"
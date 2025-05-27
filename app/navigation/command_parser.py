
import logging
import re
from typing import Callable, Dict, Optional

from navigation.browser_manager import BrowserManager, speak
from navigation.thread_queue import ThreadSafeQueue

class CommandError(Exception):
    """Niestandardowy wyjątek dla błędów komend."""
    pass


logger = logging.getLogger(__name__)

class CommandParser:
    def __init__(self, browser_manager: BrowserManager, command_queue: ThreadSafeQueue):
        self.browser_manager = browser_manager
        self.command_queue = command_queue
        self.command_patterns: Dict[str, Callable] = {
            r"wejdź na stronę\s+(.*)": lambda url: self.browser_manager.open_page(url),
            r"otwórz przeglądarkę": self.browser_manager.open_browser,
            r"otwórz stronę\s+(.*)": lambda url: self.browser_manager.open_page(url),
            r"wyszukaj\s+(.*)": lambda query: self.browser_manager.search_web(query),
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
        }
    
    
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
        speak("Nie rozpoznano komendy.")
        raise CommandError(f"Nieznana komenda: {command}")

    def _ask_model(self, question: str) -> Optional[str]:
        """Zadaje pytanie modelowi AI (Mistral-7B) na podstawie treści strony."""
        try:
            page_data = self.browser_manager._get_page_data()
            text = page_data.get('text', '')
            if not text:
                speak("Brak treści do analizy.")
                return None
            # Placeholder dla wywołania modelu Mistral-7B
            answer = ask_ai_model(question, text)
            speak(f"Odpowiedź modelu: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Błąd zadawania pytania modelowi: {e}")
            speak("Nie udało się uzyskać odpowiedzi od modelu.")
            return None

    def _find_on_page(self, phrase: str) -> Optional[str]:
        """Wyszukuje frazę na stronie za pomocą modelu AI (Mistral-7B)."""
        try:
            page_data = self.browser_manager._get_page_data()
            text = page_data.get('text', '')
            if not text:
                speak("Brak treści do przeszukania.")
                return None
            # Użycie modelu AI do inteligentnego wyszukiwania
            result = search_with_ai(phrase, text)
            if result:
                speak(f"Znaleziono: {result}")
                return result
            speak(f"Nie znaleziono frazy: {phrase}")
            return None
        except Exception as e:
            logger.error(f"Błąd wyszukiwania frazy: {e}")
            speak("Nie udało się wyszukać frazy na stronie.")
            return None
        

# Placeholder dla integracji z modelem AI
def ask_ai_model(question: str, context: str) -> str:
    """Zadaje pytanie modelowi Mistral-7B."""
    # Tutaj będzie rzeczywiste wywołanie API modelu
    return "Odpowiedź od modelu AI (placeholder)"

def search_with_ai(phrase: str, context: str) -> Optional[str]:
    """Wyszukuje frazę w kontekście za pomocą modelu AI."""
    # Tutaj będzie rzeczywiste wywołanie API modelu
    if phrase.lower() in context.lower():
        return "Znaleziono frazę w kontekście (placeholder)."
    return None
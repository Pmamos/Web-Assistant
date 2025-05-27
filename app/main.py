import time

from navigation.browser_manager import BrowserManager
from navigation.command_parser import CommandParser
from navigation.thread_queue import ThreadSafeQueue


def main():
    # Inicjalizacja komponentów
    queue = ThreadSafeQueue()
    browser_manager = BrowserManager()
    browser_manager.initialize()  # Inicjalizacja przeglądarki w głównym wątku
    parser = CommandParser(browser_manager, queue)

    # Lista testowych komend (wszystkie z pierwotnego kodu)
    test_commands = [
        "otwórz przeglądarkę",
        "otwórz stronę wikipedia.org",
        "wejdź na stronę google.com",
        "wyszukaj najnowsze wiadomości",
        "cofnij",
        "ponów",
        "przeczytaj nagłówki",
        "streść stronę",
        "odśwież stronę",
        "pokaż historię",
        "przeczytaj treść",
        "domyślna strona",
        "otwórz w nowej karcie python.org",
        "przejdź do sekcji historia",
        "opisz obraz 1",
        "przejdź do następnej strony",
        "przejdź do poprzedniej strony",
        "przejdź do https://example.com",
    ]

    # Dodawanie komend do kolejki
    for cmd in test_commands:
        try:
            parser.parse_command(cmd)
            print(f"Dodano komendę: {cmd}")
        except Exception as e:
            print(f"Błąd parsowania: {e}")

    # Przetwarzanie kolejki
    print("\nPrzetwarzanie kolejki...\n")
    while not queue.empty():
        try:
            handler, args, kwargs = queue.get()
            result = handler(*args, **kwargs)
            print(f"Wynik: {result}")
        except Exception as e:
            print(f"Błąd wykonania: {e}")
        time.sleep(0.5)  # Opóźnienie dla lepszej widoczności

if __name__ == "__main__":
    main()
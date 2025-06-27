import os
import time
import json

from ai.page_assistant import PageAssistant
from voice.voice_listener import VoiceListener
from navigation.browser_manager import BrowserManager
from navigation.command_parser import CommandParser
from navigation.thread_queue import ThreadSafeQueue


def save_results(results, output_dir="results"):
    """Zapisuje wyniki do pliku JSON."""
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "test_results2.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def generate_report(results, output_dir="results"):
    """Generuje raport w formacie Markdown."""
    report = "# Raport porównawczy modeli GGUF\n\n"
    report += "| Model | Średni czas streszczania (s) | Średni czas QA (s) | Średni czas struktury (s) | Średnie zużycie VRAM (MB) | Poprawność QA (%) | Ocena streszczenia (0-5) | Ocena struktury (0-5) | Błędy |\n"
    report += "|-------|-----------------------------|-------------------|--------------------------|---------------------------|------------------|-------------------------|-----------------------|-------|\n"

    for model_name, data in results.items():
        avg_summary_time = sum([r["time"] for r in data["summaries"] if not r.get("error")]) / max(1, len(data["summaries"]))
        avg_qa_time = sum([r["time"] for r in data["questions"] if not r.get("error")]) / max(1, len(data["questions"]))
        avg_structure_time = sum([r["time"] for r in data["structures"] if not r.get("error")]) / max(1, len(data["structures"]))
        avg_vram = sum([r["vram_usage"] for r in data["summaries"] + data["questions"] + data["structures"] if not r.get("error")]) / max(1, len(data["summaries"] + data["questions"] + data["structures"]))
        qa_correct = sum(1 for r in data["questions"] if r.get("correct", False)) / max(1, len(data["questions"])) * 100
        avg_summary_score = sum(r.get("score", 0) for r in data["summaries"]) / max(1, len(data["summaries"]))
        avg_structure_score = sum(r.get("score", 0) for r in data["structures"]) / max(1, len(data["structures"]))
        errors = sum(1 for r in data["summaries"] + data["questions"] + data["structures"] if r.get("error"))

        report += f"| {model_name} | {avg_summary_time:.2f} | {avg_qa_time:.2f} | {avg_structure_time:.2f} | {avg_vram:.2f} | {qa_correct:.2f} | {avg_summary_score:.2f} | {avg_structure_score:.2f} | {errors} |\n"

    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Raport zapisany w {os.path.join(output_dir, 'report.md')}")


def main():
    # Inicjalizacja komponentów
    
    # page_assistant = PageAssistant(
    #     model_repo_id="speakleash/Bielik-4.5B-v3.0-Instruct-GGUF",
    #     model_filename="Bielik-4.5B-v3.0-Instruct-f16.gguf"
    # )
    # browser_manager.initialize(page_assistant)  # Inicjalizacja przeglądarki w głównym wątku
    # parser = CommandParser(browser_manager, queue)

    # # Inicjalizacja systemu głosowego
    # voice_listener = VoiceListener(parser)
    # voice_listener.start()

    # # Lista testowych komend (wszystkie z pierwotnego kodu)
    # test_commands = [
    #     "otwórz przeglądarkę",
    #     "otwórz stronę wikipedia.org",
    #     "wejdź na stronę google.com",
    #     "wyszukaj najnowsze wiadomości",
    #     "cofnij",
    #     "ponów",
    #     "przeczytaj nagłówki",
    #     "streść stronę",
    #     "odśwież stronę",
    #     "pokaż historię",
    #     "przeczytaj treść",
    #     "domyślna strona",
    #     "otwórz w nowej karcie python.org",
    #     "przejdź do sekcji historia",
    #     "opisz obraz 1",
    #     "przejdź do następnej strony",
    #     "przejdź do poprzedniej strony",
    #     "przejdź do https://example.com",
    # ]

    # # Dodawanie komend do kolejki
    # for cmd in test_commands:
    #     try:
    #         parser.parse_command(cmd)
    #         print(f"Dodano komendę: {cmd}")
    #     except Exception as e:
    #         print(f"Błąd parsowania: {e}")

    # # Przetwarzanie kolejki
    # print("\nPrzetwarzanie kolejki...\n")
    # while not queue.empty():
    #     try:
    #         handler, args, kwargs = queue.get()
    #         result = handler(*args, **kwargs)
    #         print(f"Wynik: {result}")
    #     except Exception as e:
    #         print(f"Błąd wykonania: {e}")
    #     time.sleep(0.5)  # Opóźnienie dla lepszej widoczności

   
        # Główna pętla aplikacji
        # while True:
        #     # Przetwarzanie komend z kolejki
        #     while not queue.empty():
        #         try:
        #             handler, args, kwargs = queue.get()
        #             result = handler(*args, **kwargs)
        #             print(f"Wynik: {result}")
        #         except Exception as e:
        #             print(f"Błąd wykonania: {e}")
        #     time.sleep(0.1)


    # # Lista komend testowych
    # test_commands = [
    #         "otwórz przeglądarkę",
    #         "otwórz stronę https://aniastarmach.pl/przepis/pierogi-ruskie/",
    #         # "streść stronę",
    #         "zapytaj model jakie składniki są potrzebne do pierogów ruskich",
    #         "zapytaj model jak długo gotować pierogi",
    #         "zapytaj model czy pierogi można zamrozić",
    #         "otwórz stronę https://www.olx.pl/d/oferta/woom-explore-5-czerwony-CID767-ID161TEb.html",
    #         "streść stronę",
    #         "zapytaj model ile kosztuje rower",
    #         "zapytaj model jaka jest lokalizacja roweru",
    #         "zapytaj model kto jest sprzedawcą",
    #         "zapytaj model jakie są szczegóły techniczne roweru",
    #         "otwórz stronę https://eobuwie.com.pl/p/sneakersy-adidas-campus-00s-jh7275-rozowy-0000304471186?snrai_campaign=chYFpL9kxGQT&snrai_id=cba21e58-83df-47f2-9291-67c40b152e58",
    #         "streść stronę",
    #         "zapytaj model jaki to model butów",
    #         "zapytaj model w jakich rozmiarach są dostępne",
    #         "zapytaj model czy produkt jest przeceniony",
    #         "otwórz stronę https://zpe.gov.pl/a/klimat-polski/D1GwXj5uF",
    #         "streść stronę",
    #         "zapytaj model jakie są cechy klimatu Polski",
    #         "zapytaj model jakie czynniki wpływają na klimat Polski",
    #         "zapytaj model czym różni się klimat Polski od klimatu śródziemnomorskiego",
    #         "otwórz stronę https://pl.wikipedia.org/wiki/Kozacy",
    #         "streść stronę",
    #         "zapytaj model kim byli Kozacy",
    #         "zapytaj model jakie były najważniejsze powstania kozackie",
    #         "zapytaj model czym różnili się Kozacy zaporoscy od dońskich",
    #         "zamknij przeglądarkę"
    #     ]

    # models = [
    #     {"repo_id": "bartowski/Mistral-7B-Instruct-v0.3-GGUF", "filename": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"},
    #     {"repo_id": "speakleash/Bielik-4.5B-v3.0-Instruct-GGUF", "filename": "Bielik-4.5B-v3.0-Instruct-f16.gguf"},
    #     {"repo_id": "mradermacher/Krakowiak-7B-v3-GGUF", "filename": "Krakowiak-7B-v3.Q4_K_M.gguf"},
    #     # {"repo_id": "mradermacher/Curie-7B-v1-GGUF", "filename": "Curie-7B-v1.IQ4_XS.gguf"},
    #     # {"repo_id": "bartowski/Llama-3.2-3B-Instruct-GGUF", "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf"},
    #     {"repo_id": "mradermacher/DeepSeek-V2-Lite-GGUF", "filename": "DeepSeek-V2-Lite.Q4_K_M.gguf"},
    #     {"repo_id": "mradermacher/PLLuM-12B-instruct-GGUF", "filename": "PLLuM-12B-instruct.Q4_K_M.gguf"},
    # ]

    # # models = [
    # #     {"repo_id": "speakleash/Bielik-1.5B-v3.0-Instruct-GGUF", "filename": "Bielik-1.5B-v3.0-Instruct-fp16.gguf"},
    # #     {"repo_id": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", "filename": "tinyllama-1.1b-chat-v1.0.Q8_0.gguf"},
    # #     {"repo_id": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", "filename": "tinyllama-1.1b-chat-v1.0.Q5_K_M.gguf"},
    # #     {"repo_id": "TheBloke/phi-2-GGUF", "filename": "phi-2.Q8_0.gguf"},
    # # ]
    # results = {}
    # try:
    #     for model in models:
    #         model_name = f"{model['repo_id']}/{model['filename']}"
    #         print(f"Testowanie modelu: {model_name}")
    #         results[model_name] = {"summaries": [], "questions": [], "structures": []}
    #         try:
    #             print(f"Ładowanie modelu {model_name}...")
    #             page_assistant = PageAssistant(
    #                 model_repo_id=model["repo_id"],
    #                 model_filename=model["filename"]
    #             )
    #             print(f"Model {model_name} załadowany.")
    #             browser_manager = BrowserManager(page_assistant)
    #             browser_manager.initialize()
    #             parser = CommandParser(browser_manager, queue)
    #             voice_listener = VoiceListener(parser)
    #             voice_listener.start()
    #             with open("result_log3.txt", "a", encoding="utf-8") as f:
    #                     f.write(f"Model: {model['filename']}\n")

    #             for cmd in test_commands:
    #                 try:
    #                     parser.parse_command(cmd)
    #                 except Exception as e:
    #                     print(f"Błąd parsowania komendy '{cmd}' dla modelu {model_name}: {e}")

    #             while not queue.empty():
    #                 try:
    #                     handler, args, kwargs = queue.get()
    #                     result = handler(*args, **kwargs)
    #                     print(f"Wynik komendy: {result}")
    #                     with open("result_log3.txt", "a", encoding="utf-8") as f:
    #                         f.write(f"Wynik komendy: {result}\n")
    #                     if isinstance(result, dict) and "text" in result:
    #                         if "streść stronę" in cmd:
    #                             results[model_name]["summaries"].append(result["text"])
    #                         elif "zapytaj model" in cmd:
    #                             results[model_name]["questions"].append(result["text"])
    #                         elif "opisz strukturę strony" in cmd:
    #                             results[model_name]["structures"].append(result["text"])
    #                     time.sleep(10)  
    #                 except Exception as e:
    #                     print(f"Błąd wykonania komendy dla modelu {model_name}: {e}")

    #             save_results(results)
    #         except Exception as e:
    #             print(f"Błąd testowania modelu {model_name}: {e}")
    #         finally:
    #             if voice_listener:
    #                 voice_listener.stop()
    #             if browser_manager:
    #                 browser_manager.close_browser()
                    

    #     generate_report(results)
    # except KeyboardInterrupt:
    #     print("Przerwano testy.")
    # finally:
    #     # if voice_listener:
    #     #     voice_listener.stop()
    #     # if browser_manager:
    #     #     browser_manager.close_browser()
    #     print("Testy zakończone. Wyniki zapisane.")
    
    # test_commands = [
    #     # Inicjalizacja przeglądarki
    #     "otwórz przeglądarkę",
        
    #     # Test 1: Strona z wieloma obrazami (np. galeria)
    #     "otwórz stronę https://unsplash.com",
    #     "opisz obraz 1",
    #     "opisz obraz 20",
    #     "opisz obraz 24",
        
    #     # Test 2: Strona z obrazami produktowymi
    #     "otwórz stronę https://www.ikea.com/pl/pl/",
    #     "opisz obraz 1",
    #     "opisz obraz 2",
    #     "opisz obraz 3",
    #     "opisz obraz 4",
    #     "opisz obraz 5",
    #     "opisz obraz 6",
    #     "opisz obraz 7",
        
    #     # Test 3: Strona z infografikami
    #     "otwórz stronę https://www.nationalgeographic.com",
    #     "opisz obraz 1",
    #     "opisz obraz 2",
    #     "opisz obraz 3",
    #     "opisz obraz 4",
        
    #     # Test 4: Wikipedia z obrazami historycznymi
    #     "otwórz stronę https://pl.wikipedia.org/wiki/Warszawa",
    #     "opisz obraz 1",
    #     "opisz obraz 2",
    #     "opisz obraz 6",
        
    #     # Test 5: Strona z diagramami technicznymi
    #     "otwórz stronę https://www.raspberrypi.org",
    #     "opisz obraz 1",
    #     "opisz obraz 2",
    #     "opisz obraz 3",
        
        
    #     # Test 8: Nieprawidłowe przypadki
    #     "opisz obraz 0",  # Nieprawidłowy indeks
    #     "opisz obraz 999",  # Indeks poza zakresem
        
    #     # Zamknięcie przeglądarki
    #     "zamknij przeglądarkę"
    # ]

            
        
    # finally:
    #     # voice_listener.stop()
    #     # browser_manager.close_browser()
    #     print("Aplikacja zamknięta.")
    queue = ThreadSafeQueue()
    page_assistant = PageAssistant(
                     model_repo_id="speakleash/Bielik-4.5B-v3.0-Instruct-GGUF",
                     model_filename="Bielik-4.5B-v3.0-Instruct-f16.gguf"
                 )
    print(f"Model załadowany.")
    browser_manager = BrowserManager(page_assistant)
    browser_manager.initialize()
    parser = CommandParser(browser_manager, queue)
    voice_listener = VoiceListener(parser)
    voice_listener.start()
    test_commands = [
        # Inicjalizacja przeglądarki
        "otwórz przeglądarkę",
        
        # Test 1: Strona z wieloma obrazami (np. galeria)
        "otwórz stronę https://unsplash.com",
        "opisz obraz 1",
        "opisz obraz 20",
        "opisz obraz 24",
        
        # Test 2: Strona z obrazami produktowymi
        "otwórz stronę https://www.ikea.com/pl/pl/",
        "opisz obraz 1",
        "opisz obraz 2",
        "opisz obraz 3",
        "opisz obraz 4",
        "opisz obraz 5",
        "opisz obraz 6",
        "opisz obraz 7",
        
        # Test 3: Strona z infografikami
        "otwórz stronę https://www.nationalgeographic.com",
        "opisz obraz 1",
        "opisz obraz 2",
        "opisz obraz 3",
        "opisz obraz 4",
        
        # Test 4: Wikipedia z obrazami historycznymi
        "otwórz stronę https://pl.wikipedia.org/wiki/Warszawa",
        "opisz obraz 1",
        "opisz obraz 2",
        "opisz obraz 6",
        
        # Test 5: Strona z diagramami technicznymi
        "otwórz stronę https://www.raspberrypi.org",
        "opisz obraz 1",
        "opisz obraz 2",
        "opisz obraz 3",
        
        
        # Test 8: Nieprawidłowe przypadki
        "opisz obraz 0",  # Nieprawidłowy indeks
        "opisz obraz 999",  # Indeks poza zakresem
        
        # Zamknięcie przeglądarki
        "zamknij przeglądarkę"
    ]
    for cmd in test_commands:
        parser.parse_command(cmd)
    try:
        while True:
            # Przetwarzanie komend z kolejki
            while not queue.empty():
                try:
                    handler, args, kwargs = queue.get()
                    result = handler(*args, **kwargs)
                    with open("result_log_images.txt", "a", encoding="utf-8") as f:
                        f.write(f"Wynik komendy: {result}\n")
                    print(f"Wynik: {result}")
                except Exception as e:
                    print(f"Błąd wykonania: {e}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nZamykanie aplikacji...")
    finally:
        voice_listener.stop()
        browser_manager.close_browser()

if __name__ == "__main__":
    main()
import time
import torch
import logging
import numpy as np
import vosk
import json
import re
from typing import Optional
from transformers import pipeline
from Levenshtein import distance as levenshtein_distance

logger = logging.getLogger(__name__)

class SpeechRecognizer:
    """Klasa do transkrypcji mowy z obsługą Whisper i Vosk oraz korektą komend"""

    # Słownik komend (lista fraz kluczowych)
    COMMANDS = [
        r"wejdź na stronę\s+(.*)",
        r"otwórz przeglądarkę",
        r"otwórz stronę\s+(.*)",
        r"cofnij",
        r"ponów",
        r"przeczytaj nagłówki",
        r"streść stronę",
        r"odśwież stronę",
        r"pokaż historię",
        r"przeczytaj treść",
        r"domyślna strona",
        r"zamknij przeglądarkę",
        r"przejdź do sekcji\s+(.*)",
        r"opisz obraz\s+(\d+)",
        r"przejdź do następnej strony",
        r"przejdź do poprzedniej strony",
        r"otwórz w nowej karcie\s+(.*)",
        r"przejdź do\s+(.*)",
        r"zapytaj model\s+(.*)",
        r"znajdź na stronie\s+(.*)",
        r"przeczytaj wyniki wyszukiwania",
        r"otwórz wynik\s+(\d+)",
        r"przeczytaj linki",
        r"otwórz link\s+(\d+)",
        r"wyszukaj na wikipedii\s+(.*)",
        r"pokaż sekcje artykułu",
        r"przeczytaj sekcję\s+(.*)",
        r"wyszukaj filmy na youtube\s+(.*)",
        r"przeczytaj filmy",
        r"otwórz film\s+(\d+)",
        r"przeczytaj formularze",
        r"wyszukaj\s+(.*)",
        r"komputer",
        r"stop"
    ]


    COMMANDS_VOSK = [
        r"otwórz przeglądarkę",
        r"cofnij",
        r"ponów",
        r"przeczytaj nagłówki",
        r"streść stronę",
        r"odśwież stronę",
        r"pokaż historię",
        r"przeczytaj treść",
        r"domyślna strona",
        r"zamknij przeglądarkę",
        r"przejdź do następnej strony",
        r"przejdź do poprzedniej strony",
        r"przeczytaj wyniki wyszukiwania",
        r"otwórz wynik\s+(\d+)",
        r"przeczytaj linki",
        r"otwórz link\s+(\d+)",
        r"pokaż sekcje artykułu",
        r"przeczytaj filmy",
        r"otwórz film\s+(\d+)",
        r"przeczytaj formularze",
        r"komputer",
        r"stop"
    ]

    def __init__(self, whisper_model_id: str = "openai/whisper-large-v3", 
                 vosk_model_path: str = "D:/magisterka/Web Assistant/app/models/vosk/vosk-model-small-pl-0.22", 
                 sample_rate: int = 16000, use_vosk: bool = True, init: bool = True, whisper_pipe: Optional[pipeline] = None):
        self.sample_rate = sample_rate
        self.use_vosk = use_vosk
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        
        print(f"Inicjalizacja SpeechRecognizer na urządzeniu: {self.device}")
        
        if use_vosk and init:
            # Inicjalizacja Vosk
            try:
                self.vosk_model = vosk.Model(vosk_model_path)
                self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, sample_rate)
                print("Model Vosk pomyślnie załadowany.")

                self.whisper_pipe = pipeline(
                    "automatic-speech-recognition",
                    model=whisper_model_id,
                    device=self.device,
                    torch_dtype=self.torch_dtype,
                    model_kwargs={"attn_implementation": None} if torch.cuda.is_available() else {}
                )
                print("Model Whisper pomyślnie załadowany.")
            except Exception as e:
                logger.error(f"Błąd inicjalizacji modelu Vosk: {e}")
                raise
            
        elif init:
            # Inicjalizacja Whisper
            try:
                self.whisper_pipe = pipeline(
                    "automatic-speech-recognition",
                    model=whisper_model_id,
                    device=self.device,
                    torch_dtype=self.torch_dtype,
                    model_kwargs={"attn_implementation": None} if torch.cuda.is_available() else {}
                )
                print("Model Whisper pomyślnie załadowany.")
            except Exception as e:
                logger.error(f"Błąd inicjalizacji modelu Whisper: {e}")
                raise
        else:
            # Użyj istniejącej instancji Whisper
            if whisper_pipe is None:
                raise ValueError("Musisz podać instancję pipeline Whisper, jeśli nie inicjalizujesz modelu.")
            self.whisper_pipe = whisper_pipe

    def _correct_transcription(self, text: str) -> str:
        """Korekta transkrypcji na podstawie słownika komend"""
        if not text:
            return text

        # Usuń znaki specjalne i normalizuj tekst
        text = text.lower().strip()

        # Sprawdź, czy tekst pasuje dokładnie do którejś komendy
        for command_pattern in self.COMMANDS:
            if re.fullmatch(command_pattern, text):
                return text

        # Jeśli nie ma dokładnego dopasowania, znajdź najbliższą komendę
        min_distance = float('inf')
        best_match = text
        for command_pattern in self.COMMANDS:
            # Generuj możliwe frazy z wzorca (bez parametrów)
            base_command = re.sub(r"\s+\(.*\)", "", command_pattern)
            dist = levenshtein_distance(text, base_command)
            if dist < min_distance:
                min_distance = dist
                best_match = base_command

        # Jeśli odległość Levenshteina jest wystarczająco mała, zwróć poprawioną komendę
        if min_distance <= len(text) // 2:  # Próg dopasowania (można dostosować)
            print(f"Poprawiono transkrypcję: '{text}' -> '{best_match}'")
            return best_match
        return text

    def transcribe(self, audio_data: bytes, fallback_to_whisper: bool = True) -> Optional[str]:
        """Transkrypcja audio na tekst (Whisper lub Vosk)"""
        try:
            print("Rozpoczynam transkrypcję...")
            t0 = time.time()

            if self.use_vosk:
                # Transkrypcja z Vosk
                self.vosk_recognizer.AcceptWaveform(audio_data)
                result = json.loads(self.vosk_recognizer.Result())
                text = result.get("text", "").strip()
            else:
                # Transkrypcja z Whisper
                with torch.no_grad():
                    result = self.whisper_pipe(
                        audio_data,
                        generate_kwargs={"language": "polish"}
                    )
                text = result.get("text", "").strip()

            t1 = time.time()
            print(f"Czas transkrypcji: {t1-t0:.2f} sekund")
            
            # Korekta transkrypcji na podstawie słownika
            corrected_text = self._correct_transcription(text)
            

            is_known_command = any(
                re.fullmatch(pattern, corrected_text) for pattern in self.COMMANDS_VOSK
            )

                    # Jeśli wynik nie pasuje do żadnej znanej komendy i fallback jest włączony
            if self.use_vosk and fallback_to_whisper and not is_known_command:
                print("Nie znaleziono dopasowanej komendy w Vosk. Próba z Whisper...")
                whisper_recognizer = SpeechRecognizer(use_vosk=False, init = False, whisper_pipe = self.whisper_pipe)
                return whisper_recognizer.transcribe(audio_data, fallback_to_whisper=False)

            print(f"Transkrypcja zakończona: '{corrected_text}'")
            return corrected_text if corrected_text else None

        except Exception as e:
            logger.error(f"Błąd transkrypcji: {e}")
            return None



# if __name__ == "__main__":

#     # Inicjalizacja z Whisper
    
    
#     # Załóżmy, że mamy dane WAV z wcześniejszego nagrywania
#     with open("last_command.wav", "rb") as f:
#         audio_data = f.read()
    
#     # Przełącz na Vosk
#     recognizer = SpeechRecognizer()
#     text = recognizer.transcribe(audio_data)
#     recognizer = SpeechRecognizer(use_vosk=False)
#     text = recognizer.transcribe(audio_data)

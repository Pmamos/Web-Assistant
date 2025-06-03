import os
import hashlib
import logging
import queue
import threading
import shutil
from typing import Optional
from dataclasses import dataclass
import miniaudio

import pyttsx3
from gtts import gTTS

logger = logging.getLogger(__name__)

@dataclass
class TTSConfig:
    """Konfiguracja dla TTSWrapper"""
    voice: str = 'polish'  # Domyślny język: polski
    volume: float = 1.0    # Głośność (0.0 - 1.0)
    rate: int = 150        # Szybkość mowy (w słowach na minutę)
    engine: str = 'pyttsx3'  # Domyślny silnik: pyttsx3

class TTSWrapper:
    """Wrapper dla Text-to-Speech z obsługą pyttsx3 i gTTS, cache'owaniem i wielowątkowością"""

    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig()
        self.job_queue = queue.Queue()
        self.engine_objects = {}
        self.lock = threading.Lock()
        self.active_device = None
        self.cache_dir = "tts_cache"
        self.running = False
        self.worker_thread = None

        self._init_engines()
        self._init_cache()
        self._start_worker()

    def _init_engines(self):
        """Inicjalizacja silników TTS"""
        try:
            if 'pyttsx3' in self.config.engine or not self.config.engine:
                self.engine_objects['pyttsx3'] = pyttsx3.init()
                engine = self.engine_objects['pyttsx3']
                engine.setProperty('rate', self.config.rate)
                engine.setProperty('volume', self.config.volume)
                # Ustaw głos dla języka polskiego (jeśli dostępny)
                voices = engine.getProperty('voices')
                for voice in voices:
                    if self.config.voice.lower() in voice.name.lower() or 'polish' in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
                else:
                    logger.warning("Nie znaleziono polskiego głosu dla pyttsx3, używam domyślnego")
            if 'gtts' in self.config.engine or not self.config.engine:
                self.engine_objects['gtts'] = gTTS
            print(f"Zainicjalizowano silniki TTS: {list(self.engine_objects.keys())}")
        except Exception as e:
            logger.error(f"Błąd inicjalizacji silników TTS: {e}")
            raise

    def _init_cache(self):
        """Inicjalizacja katalogu cache dla plików audio"""
        try:
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir, exist_ok=True, mode=0o755)
            else:
                # Czyszczenie cache przy inicjalizacji
                for filename in os.listdir(self.cache_dir):
                    file_path = os.path.join(self.cache_dir, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        logger.error(f"Błąd usuwania pliku cache {file_path}: {e}")
            print(f"Zainicjalizowano katalog cache: {self.cache_dir}")
        except Exception as e:
            logger.error(f"Błąd inicjalizacji cache: {e}")
            raise

    def _start_worker(self):
        """Uruchamia wątek roboczy do przetwarzania kolejki TTS"""
        self.running = True
        self.worker_thread = threading.Thread(target=self._process_queue)
        self.worker_thread.daemon = True
        self.worker_thread.start()
        print("Uruchomiono wątek roboczy TTS")

    def _generate_cache_key(self, text: str) -> str:
        """Generuje unikalny klucz cache dla tekstu i konfiguracji"""
        params = f"{text}-{self.config.engine}-{self.config.voice}-{self.config.rate}-{self.config.volume}"
        return hashlib.sha256(params.encode()).hexdigest()

    def _synthesize_pyttsx3(self, text: str) -> Optional[str]:
        """Generowanie mowy za pomocą pyttsx3"""
        cache_key = self._generate_cache_key(text)
        file_path = os.path.join(self.cache_dir, f"{cache_key}.wav")

        if os.path.exists(file_path):
            print(f"Użyto pliku z cache: {file_path}")
            return file_path

        try:
            engine = self.engine_objects['pyttsx3']
            engine.save_to_file(text, file_path)
            engine.runAndWait()
            print(f"Wygenerowano audio pyttsx3: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Błąd syntezy pyttsx3: {e}")
            return None

    def _synthesize_gtts(self, text: str) -> Optional[str]:
        """Generowanie mowy za pomocą gTTS"""
        cache_key = self._generate_cache_key(text)
        file_path = os.path.join(self.cache_dir, f"{cache_key}.mp3")

        if os.path.exists(file_path):
            print(f"Użyto pliku z cache: {file_path}")
            return file_path

        try:
            tts = self.engine_objects['gtts'](text=text, lang=self.config.voice.split('-')[0])
            tts.save(file_path)
            print(f"Wygenerowano audio gTTS: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Błąd syntezy gTTS: {e}")
            return None

    def _play_audio(self, file_path: str):
        """Odtwarzanie audio za pomocą funkcji speak z BrowserManager"""
        try:
            with self.lock:
                # Zatrzymaj aktualne odtwarzanie
                if self.active_device:
                    self.active_device.close()

                with open(file_path, "rb") as f:
                    audio_data = f.read()
                # Rozpocznij nowe odtwarzanie w osobnym wątku
                def play():
                    stream = miniaudio.stream_memory(audio_data)
                    self.active_device = miniaudio.PlaybackDevice()
                    self.active_device.start(stream)

                self.playback_thread = threading.Thread(target=play)
                self.playback_thread.start()
        except Exception as e:
            logger.error(f"Błąd odtwarzania audio: {e}")

    def synthesize(self, text: str) -> Optional[str]:
        """Główna metoda syntezy mowy"""
        if not text.strip():
            logger.warning("Pusty tekst do syntezy")
            return None

        synthesizer = {
            'pyttsx3': self._synthesize_pyttsx3,
            'gtts': self._synthesize_gtts
        }.get(self.config.engine)

        if not synthesizer:
            logger.error(f"Nieobsługiwany silnik TTS: {self.config.engine}")
            return None

        return synthesizer(text)

    def speak(self, text: str, blocking: bool = False):
        """Dodaje tekst do kolejki odtwarzania"""
        if not text.strip():
            logger.warning("Pusty tekst, pomijam")
            return
        self.job_queue.put((text, blocking))
        print(f"Dodano tekst do kolejki TTS: {text[:50]}...")

    def _process_queue(self):
        """Przetwarzanie zadań z kolejki"""
        while self.running:
            try:
                task = self.job_queue.get(timeout=0.5)
                if task == 'shutdown':
                    break

                text, blocking = task
                file_path = self.synthesize(text)

                if file_path:
                    self._play_audio(file_path)
                    if blocking:
                        # Czekaj na zakończenie odtwarzania (placeholder, jeśli potrzebne)
                        pass

                self.job_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Błąd przetwarzania kolejki TTS: {e}")

    def configure(self, **kwargs):
        """Aktualizacja konfiguracji TTS"""
        valid_keys = ['voice', 'volume', 'rate', 'engine']
        for key, value in kwargs.items():
            if key in valid_keys:
                setattr(self.config, key, value)

        if 'pyttsx3' in self.engine_objects and 'pyttsx3' in self.config.engine:
            engine = self.engine_objects['pyttsx3']
            if 'rate' in kwargs:
                engine.setProperty('rate', self.config.rate)
            if 'volume' in kwargs:
                engine.setProperty('volume', self.config.volume)
            if 'voice' in kwargs:
                voices = engine.getProperty('voices')
                for voice in voices:
                    if self.config.voice.lower() in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
                else:
                    logger.warning(f"Głos {self.config.voice} niedostępny, używam domyślnego")

        print(f"Aktualna konfiguracja TTS: {self.config}")
        # Czyszczenie cache przy zmianie konfiguracji
        self._clean_cache()

    def stop(self):
        """Zatrzymanie odtwarzania i czyszczenie kolejki"""
        with self.lock:
            self.job_queue.queue.clear()
            print("Wyczyszczono kolejkę TTS")

    def _clean_cache(self):
        """Czyszczenie cache audio"""
        try:
            if os.path.exists(self.cache_dir):
                for filename in os.listdir(self.cache_dir):
                    file_path = os.path.join(self.cache_dir, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        logger.error(f"Błąd usuwania pliku cache {file_path}: {e}")
                print("Wyczyszczono cache TTS")
        except Exception as e:
            logger.error(f"Błąd czyszczenia cache: {e}")

    def shutdown(self):
        """Bezpieczne zamykanie komponentów"""
        self.running = False
        self.stop()
        self.job_queue.put('shutdown')

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)

        if 'pyttsx3' in self.engine_objects:
            self.engine_objects['pyttsx3'].stop()

        self._clean_cache()
        print("TTSWrapper zamknięty")
import logging
import queue
import threading
import time
import numpy as np
import sounddevice as sd
from collections import deque
from voice.audio_processor import AudioProcessor
from voice.speech_recognition import SpeechRecognizer
from voice.wake_word_detector import WakeWordDetector

logger = logging.getLogger(__name__)

class VoiceListener:
    """Główny system nasłuchiwania głosu z lepszą detekcją mowy"""
    
    def __init__(self, command_parser):
        self.command_parser = command_parser
        self.wake_detector = WakeWordDetector()
        self.recognizer = SpeechRecognizer()
        self.is_listening = False
        self.is_wake_up = False 
        self.stop_event = threading.Event()
        self.sample_rate = 16000
        self.silence_threshold = 0.01  # Dostosuj w zależności od środowiska
        self.speech_threshold = 0.02   # Próg dla rozpoczęcia mowy
        self.silence_duration = 1.5    # Sekundy ciszy potrzebne do zakończenia
        self.chunk_duration = 0.1      # Krótsze fragmenty dla lepszej responsywności
        self.buffer_seconds = 1.5      # Bufor przechowujący ostatnie 1.5s dźwięku
        self.audio_queue = queue.Queue()

    def start(self):
        """Uruchomienie systemu w tle"""
        if self.is_listening:
            return

        self.is_listening = True
        listener_thread = threading.Thread(target=self._listening_loop)
        listener_thread.daemon = True
        listener_thread.start()

    def _listening_loop(self):
        """Główna pętla nasłuchiwania z wake word detection"""
        try:
            while not self.stop_event.is_set():
                if self.is_wake_up:
                    print("Przetwarzanie komendy...")
                    self._process_command()
                elif self.wake_detector.check_for_wake_word():
                    print("Wykryto słowo aktywujące!")
                    self.is_wake_up = True
                    self._play_notification_sound(frequency=440, duration=0.6)
                
                
                time.sleep(0.05)
        except Exception as e:
            logger.error(f"Błąd w pętli nasłuchującej: {e}")
        finally:
            self.wake_detector.stop()

    def _process_command(self):
        """Przetwarzanie komendy głosowej z dynamicznym nagrywaniem"""
        try:
            # Nagrywanie komendy z detekcją mowy i ciszy
            audio_data = self._record_command()
            
            if audio_data is None or audio_data.size == 0:
                print("Nie nagrano żadnej komendy.")
                self._play_notification_sound(frequency=600, duration=0.3)
                return
            
            # Konwersja do formatu WAV
            wav_data = AudioProcessor.convert_to_wav(audio_data)
            
            # Transkrypcja mowy na tekst
            command = self.recognizer.transcribe(wav_data)
            if command:
                if command.lower().strip() == "stop":
                    print("Otrzymano komendę stop.")
                    self._play_notification_sound(frequency=600, duration=0.3)
                    self.is_wake_up = False
                else:
                    print(f"Rozpoznano komendę: {command}")
                    self.command_parser.parse_command(command)
                    self._play_notification_sound(frequency=800, duration=0.2)
        except Exception as e:
            logger.error(f"Błąd przetwarzania komendy: {e}")
            self._play_notification_sound(frequency=300, duration=0.5)


    def _record_command(self):
        """Uruchomienie nagrywania i analizy w osobnych wątkach"""
        try:
            # Wyczyść kolejkę
            while not self.audio_queue.empty():
                self.audio_queue.get()
            
            # Uruchom wątek nagrywania
            record_thread = threading.Thread(target=self._record_audio_stream)
            record_thread.start()
            
            # Analiza w głównym wątku (można przenieść do osobnego wątku)
            recording = self._analyze_audio()
            
            # Zatrzymaj nagrywanie
            self.stop_event.set()
            record_thread.join()
            self.stop_event.clear()
            
            return recording
            
        except Exception as e:
            logging.error(f"Błąd podczas nagrywania komendy: {e}")
            return None
    
    def _analyze_audio(self):
        """Analiza audio z kolejki z detekcją mowy i ciszy"""
        buffer_size = int(self.buffer_seconds / self.chunk_duration)
        audio_buffer = deque(maxlen=buffer_size)
        recording_chunks = []
        speech_detected = False
        silence_counter = 0
        max_silence_chunks = int(self.silence_duration / self.chunk_duration)
        
        print("Oczekiwanie na komendę...")
        
        while not self.stop_event.is_set():
            try:
                # Pobierz fragment audio z kolejki
                chunk = self.audio_queue.get(timeout=1.0)
                audio_buffer.append(chunk)
                
                # Analiza amplitudy
                amplitude = np.abs(chunk).max()
                # print(f"Amplituda: {amplitude:.4f}")
                
                # Detekcja mowy
                if not speech_detected:
                    if amplitude > self.speech_threshold:
                        print("Wykryto początek mowy")
                        speech_detected = True
                        recording_chunks.extend(audio_buffer)
                        silence_counter = 0
                else:
                    recording_chunks.append(chunk)
                    
                    # Detekcja ciszy
                    if amplitude < self.silence_threshold:
                        silence_counter += 1
                    else:
                        silence_counter = 0
                    
                    # Zakończ po okresie ciszy
                    if silence_counter >= max_silence_chunks:
                        print("Wykryto koniec mowy")
                        break
                        
            except queue.Empty:
                continue
        
        # Połącz fragmenty i zapisz
        if recording_chunks:
            print("Nagrywanie zakończone, przetwarzanie...")
            recording = np.concatenate(recording_chunks)
            wav_data = AudioProcessor.convert_to_wav(recording, self.sample_rate)
            with open("last_command.wav", "wb") as f:
                f.write(wav_data)
            return recording
        return np.array([])

    def _play_notification_sound(self, frequency, duration):
        """Odtwarzanie sygnału dźwiękowego"""
        try:
            samples = np.linspace(0, duration, int(self.sample_rate * duration))
            tone = 0.5 * np.sin(2 * np.pi * frequency * samples)
            sd.play(tone, samplerate=self.sample_rate)
            sd.wait()
        except Exception as e:
            logger.error(f"Błąd odtwarzania dźwięku: {e}")

    def _record_audio_stream(self):
        """Ciągłe nagrywanie audio i umieszczanie próbek w kolejce"""
        def callback(indata, frames, time, status):
            if status:
                logging.error(f"Błąd nagrywania: {status}")
            self.audio_queue.put(indata.copy().flatten())
        
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32', 
                              blocksize=int(self.sample_rate * self.chunk_duration),
                              callback=callback):
                while not self.stop_event.is_set():
                    sd.sleep(int(self.chunk_duration * 1000))  
        except Exception as e:
            logging.error(f"Błąd nagrywania strumienia: {e}")

    def stop(self):
        """Zatrzymanie systemu"""
        self.stop_event.set()
        self.is_listening = False
        self.is_wake_up = False
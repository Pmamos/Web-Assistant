import io
import logging
import re
import wave
import numpy as np
import sounddevice as sd
import speech_recognition as sr
from typing import Optional

from voice.speech_recognition import SpeechRecognizer

logger = logging.getLogger(__name__)

class WakeWordDetector:
    def __init__(self, wake_word: str = "komputer", sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.wake_word_regex = re.compile(rf'\b{wake_word}\b', re.IGNORECASE)
        self.audio_buffer = np.array([], dtype=np.float32)
        self.stream = None

        self.recognizer = SpeechRecognizer()

    def start_listening(self):
        """Rozpoczyna nasłuchiwanie mikrofonu."""
        if self.stream is not None:
            logger.warning("Już nasłuchuję!")
            return

        self.audio_buffer = np.array([], dtype=np.float32)
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            callback=self._audio_callback
        )
        self.stream.start()
        logger.info("Nasłuchiwanie rozpoczęte.")

    def _audio_callback(self, indata, frames, time, status):
        self.audio_buffer = np.append(self.audio_buffer, indata[:, 0])

    def check_for_wake_word(self, duration: float = 1.0) -> bool:
        """Nagrywa krótki fragment i sprawdza, czy pojawiło się słowo aktywujące."""
        r = sr.Recognizer()
        r.pause_threshold = 1.0
        try:
            with sr.Microphone() as source:
                logger.info("Słucham...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=3, phrase_time_limit=duration)
                wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)
                text =  self.recognizer.transcribe(wav_data)
                return bool(self.wake_word_regex.search(text))
        except sr.WaitTimeoutError:
            logger.info("Timeout nasłuchu")
        except sr.UnknownValueError:
            logger.warning("Nie rozpoznano mowy")
        except Exception as e:
            logger.error(f"Błąd rozpoznawania: {e}")
        
        

    # def _convert_to_wav(self, audio: np.ndarray) -> bytes:
    #     """Konwertuje numpy array do WAV."""
    #     with io.BytesIO() as wav_buffer:
    #         with wave.open(wav_buffer, 'wb') as wav_file:
    #             wav_file.setnchannels(1)
    #             wav_file.setsampwidth(2)
    #             wav_file.setframerate(self.sample_rate)
    #             wav_file.writeframes((audio * 32767).astype(np.int16).tobytes())
    #         return wav_buffer.getvalue()
        
    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()

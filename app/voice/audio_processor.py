import logging
import numpy as np
import sounddevice as sd
from typing import Optional
import wave
import io

class AudioProcessor:
    """Przetwarzanie i konwersja danych audio"""

    
    @staticmethod
    def convert_to_wav(audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[bytes]:
        """Konwersja do formatu WAV"""
        try:
            if audio_data.size == 0:
                return None
                
            # Normalizacja i konwersja do 16-bit
            audio_data = audio_data * (32767 / max(1, np.max(np.abs(audio_data))))
            audio_data = audio_data.astype(np.int16)
            
            with io.BytesIO() as wav_buffer:
                with wave.open(wav_buffer, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_data.tobytes())
                return wav_buffer.getvalue()
        except Exception as e:
            logging.error(f"Błąd konwersji do WAV: {e}")
            return None
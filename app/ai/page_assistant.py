import logging
import time
import subprocess
import json
import os
from typing import List, Dict, Optional
import numpy as np
from llama_cpp import Llama, LlamaTokenizer
from huggingface_hub import hf_hub_download
from sentence_transformers import SentenceTransformer, util
import re

logger = logging.getLogger(__name__)

class PageAssistant:
    def __init__(self, 
                 model_repo_id: str = "mradermacher/Krakowiak-7B-v3-GGUF",
                 model_filename: str = "Krakowiak-7B-v3.Q4_K_M.gguf",
                 models_dir: str = "D:\\magisterka\\modele_LLM",
                 n_gpu_layers: int = -1,
                 n_ctx: int = 8192):
        self.models_dir = models_dir
        self.n_ctx = n_ctx
        self.max_input_tokens = n_ctx - 300
        self.loaded_context = None
        self.context_chunks = None  # Cache dla fragmentów kontekstu
        self.chunk_embeddings_cache = None  # Cache dla osadzeń fragmentów
        self.chunk_relevance_cache = {}  # Cache dla istotnych fragmentów per pytanie
        os.makedirs(self.models_dir, exist_ok=True)

        print(f"Używanie modelu repozytorium: {model_repo_id}, plik modelu: {model_filename}")
        # Inicjalizacja modelu osadzania
        try:
            print("Ładowanie modelu osadzania sentence-transformers...")
            self.embedder = SentenceTransformer('distiluse-base-multilingual-cased')
            print("Załadowano model osadzania sentence-transformers")
        except Exception as e:
            logger.error(f"Błąd ładowania modelu osadzania: {e}")
            raise

        # Inicjalizacja modelu LLM
        try:
            print(f"Ładowanie modelu LLM z repozytorium {model_repo_id}...")
            model_path = hf_hub_download(
                repo_id=model_repo_id,
                filename=model_filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False
            )
            print(f"Ścieżka modelu: {model_path}")
            self.llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=False
            )
            self.tokenizer = LlamaTokenizer(self.llm)
            print(f"Załadowano model {model_repo_id}/{model_filename}")
        except Exception as e:
            logger.error(f"Błąd ładowania modelu {model_repo_id}: {e}")
            raise

    def _get_vram_usage(self) -> float:
        """Zwraca zużycie VRAM w MB za pomocą nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv"],
                capture_output=True, text=True
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                vram = float(lines[1].split()[0])
                return vram
        except Exception as e:
            logger.warning(f"Błąd pobierania zużycia VRAM: {e}")
        return 0.0

    def _chunk_text(self, text: str, chunk_size: int = None) -> List[str]:
        """Dzieli tekst na fragmenty z dynamicznym rozmiarem."""
        start_time = time.time()
        try:
            if not text:
                return []
            chunk_size = chunk_size or max(500, min(self.max_input_tokens, len(self.tokenizer.encode(text)) // 4))
            tokens = self.tokenizer.encode(text, add_bos=False)
            chunks = []
            for i in range(0, len(tokens), chunk_size - 100):
                chunk_tokens = tokens[i:i + chunk_size]
                chunk_text = self.tokenizer.decode(chunk_tokens).strip()
                if chunk_text:
                    chunks.append(chunk_text)
            print(f"Podzielono tekst na {len(chunks)} fragmentów w {time.time() - start_time:.2f}s")
            return chunks
        except Exception as e:
            logger.error(f"Błąd dzielenia tekstu: {e}")
            return [text[:chunk_size]]
        finally:
            print(f"Czas chunkingu: {time.time() - start_time:.2f}s")

    def _generate_response(self, prompt: str, max_tokens: int = 200, stop_sequences: list = None) -> Dict:
        """Generuje odpowiedź za pomocą modelu LLM."""
        start_time = time.time()
        vram_start = self._get_vram_usage()
        try:
            print(f"Generowanie odpowiedzi dla promptu: {prompt[:100]}... (max_tokens={max_tokens})")
            default_stop = ["\n\n", "<|endoftext|>"]
            stop = default_stop + (stop_sequences or [])
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                repeat_penalty=1.3,
                stop=stop,
                mirostat_mode=2,      # Aktywuj Mirostat 2.0
                mirostat_tau=5.0,     # Celowa perpleksja = 5.0
                mirostat_eta=0.1,     # Umiarkowane tempo adaptacji
                echo=False
            )
            print(f"Response: {response}")
            text = response["choices"][0]["text"].strip()
            vram_end = self._get_vram_usage()
            print(f"Generowanie odpowiedzi ({len(text)} znaków) w {time.time() - start_time:.2f}s, VRAM: {vram_end:.2f} MB")
            return {
                "text": text,
                "time": time.time() - start_time,
                "vram_usage": max(vram_start, vram_end)
            }
        except Exception as e:
            logger.error(f"Błąd generowania odpowiedzi: {e}")
            return {"text": "", "time": time.time() - start_time, "vram_usage": vram_start}
        finally:
            print(f"Czas generowania: {time.time() - start_time:.2f}s")

    def load_context(self, text: str):
        """Ładuje kontekst, dzieli na fragmenty i generuje osadzenia."""
        if not text:
            logger.warning("Brak tekstu do załadowania kontekstu.")
            self.loaded_context = None
            self.context_chunks = None
            self.chunk_embeddings_cache = None
            self.chunk_relevance_cache.clear()
            return

        self.loaded_context = text
        self.context_chunks = self._chunk_text(text)
        if self.context_chunks:
            try:
                self.chunk_embeddings_cache = self.embedder.encode(self.context_chunks, convert_to_tensor=True)
                print(f"Wygenerowano osadzenia dla {len(self.context_chunks)} fragmentów")
            except Exception as e:
                logger.error(f"Błąd generowania osadzeń: {e}")
                self.chunk_embeddings_cache = None
        else:
            self.chunk_embeddings_cache = None
        self.chunk_relevance_cache.clear()
        print(f"Kontekst strony załadowany. Długość: {len(text)} znaków, fragmentów: {len(self.context_chunks)}")

    def answer_question(self, question: str) -> Dict:
        """Odpowiada na pytanie na podstawie kontekstu strony, używając osadzeń do selekcji fragmentów."""
        start_time = time.time()
        vram_start = self._get_vram_usage()
        result = {"text": None, "time": 0.0, "vram_usage": vram_start, "error": None}
        try:
            if not self.loaded_context or not self.context_chunks or self.chunk_embeddings_cache is None:
                result["error"] = "Nie załadowano wcześniej kontekstu strony."
                return result

            # Sprawdzanie cache'u dla pytania
            question_key = question.lower().strip()
            if question_key in self.chunk_relevance_cache:
                print(f"Użyto cache dla pytania: {question}")
                relevant_indices = self.chunk_relevance_cache[question_key]
                relevant_chunks = [self.context_chunks[i] for i in relevant_indices]
            else:
                # Generowanie osadzenia pytania
                question_embedding = self.embedder.encode(question, convert_to_tensor=True)
                # Obliczanie podobieństwa kosinusowego
                similarities = util.cos_sim(question_embedding, self.chunk_embeddings_cache)[0]
                similarities = similarities.cpu().numpy()  # Przeniesienie na CPU dla sortowania
                
                # Wybór top-k fragmentów (np. top-3 lub te z podobieństwem > 0.5)
                k = min(3, len(self.context_chunks))
                relevant_indices = np.argsort(similarities)[-k:][::-1]  # Top-k indeksów
                print(f"Znaleziono {len(relevant_indices)} fragmentów o najwyższym podobieństwie dla pytania: {question}")
                relevant_indices = [int(idx) for idx in relevant_indices if similarities[idx] > 0.05]
                print(f"Znaleziono {len(relevant_indices)} istotnych fragmentów dla pytania: {question}")
                if not relevant_indices:
                    print(f"Brak istotnych fragmentów dla pytania: {question}")
                    result["error"] = "Nie znaleziono istotnych fragmentów zawierających odpowiedź na pytanie."
                    return result
                
                relevant_chunks = [self.context_chunks[i] for i in relevant_indices]
                print(f"Wybrano {len(relevant_chunks)} istotnych fragmentów dla pytania: {question}")

                # Cache'owanie wyników
                self.chunk_relevance_cache[question_key] = relevant_indices
                print(f"Zaktualizowano cache dla pytania: {question}, fragmentów: {len(relevant_chunks)}")

            # Łączenie fragmentów
            combined_context = "\n---\n".join(relevant_chunks)
            if len(combined_context) > self.max_input_tokens:
                combined_context = combined_context[:self.max_input_tokens-1]

            # Generowanie odpowiedzi
            prompt = (
                f"Na podstawie poniższych fragmentów odpowiedz tylko na podane pytanie w języku polskim.\n"
                f"Jeśli nie ma wystarczających informacji, odpowiedz wyłącznie 'Brak informacji'.\n"
                f"Format odpowiedzi: TYLKO treść odpowiedzi bez dodatkowych elementów.\n\n"
                f"Fragmenty:\n{combined_context}\n\n"
                f"Pytanie: {question}\n"
                f"Odpowiedź: "
            )
            stop_sequences = [
                "\nPytanie:", "Pytanie:", "\n###", "###", 
                "\nOdpowiedź:", "<|endoftext|>", "\n---"
            ]
            response = self._generate_response(prompt, max_tokens=300, stop_sequences=stop_sequences)
            print(f"Odpowiedź: {response['text']}")

            result["text"] = response["text"] or "Brak informacji"
            result["time"] = response["time"]
            result["vram_usage"] = max(vram_start, response["vram_usage"])

            print(f"Odpowiedź wygenerowana w {result['time']:.2f}s, VRAM: {result['vram_usage']:.2f} MB")
            return result
        except Exception as e:
            result["error"] = str(e)
            return result["text"]
        finally:
            result["time"] = time.time() - start_time
            print(f"Całkowity czas QA: {result['time']:.2f}s")

    def summarize_page(self) -> Dict:
        """Streszcza stronę sekwencyjnie, bez ThreadPoolExecutor."""
        start_time = time.time()
        vram_start = self._get_vram_usage()
        result = {"text": None, "time": 0.0, "vram_usage": vram_start, "error": None}
        try:
            text = self.loaded_context
            if not text:
                result["error"] = "Brak tekstu do streszczenia"
                return result

            chunks = self._chunk_text(text)
            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                prompt = (
                    f"Stwórz zwięzłe streszczenie tekstu w języku polskim, maksymalnie 150 słów. "
                    f"Skup się na kluczowych informacjach.\n\nTekst:\n{chunk}\n\nStreszczenie:"
                )
              
                summary = self._generate_response(prompt, max_tokens=200)
                if summary["text"]:
                    chunk_summaries.append(summary["text"])
                    print(f"Streszczenie fragmentu {i+1}/{len(chunks)} w {summary['time']:.2f}s")
                else:
                    logger.warning(f"Nie udało się wygenerować streszczenia dla fragmentu {i+1}")
                result["time"] += summary["time"]
                result["vram_usage"] = max(result["vram_usage"], summary["vram_usage"])

            if not chunk_summaries:
                result["error"] = "Brak streszczeń fragmentów"
                return result

            summaries_text = "\n".join(chunk_summaries)
            if len(chunk_summaries) == 1:
                result["text"] = chunk_summaries[0]
            else:
                final_prompt = (
                    f"Połącz poniższe streszczenia w jedno spójne w języku polskim, maksymalnie 200 słów:\n"
                    f"{summaries_text}\n\nFinalne streszczenie:"
                )
                final_response = self._generate_response(final_prompt, max_tokens=250, stop_sequences=["\n\n", "###", "<|endoftext|>", "Streszczenie:"])
                result["text"] = final_response["text"]
                result["time"] += final_response["time"]
                result["vram_usage"] = max(result["vram_usage"], final_response["vram_usage"])

            vram_end = self._get_vram_usage()
            result["vram_usage"] = max(result["vram_usage"], vram_end)
            print(f"Wygenerowano końcowe streszczenie w {result['time']:.2f}s, VRAM: {result['vram_usage']:.2f} MB")
            return result
        except Exception as e:
            result["error"] = str(e)
            return result["text"]
        finally:
            result["time"] = time.time() - start_time
            print(f"Całkowity czas streszczania: {result['time']:.2f}s")

    def describe_structure(self, headings: List[Dict], sections: List[Dict] = None) -> Dict:
        """Opisuje strukturę strony."""
        start_time = time.time()
        vram_start = self._get_vram_usage()
        result = {"text": None, "time": 0.0, "vram_usage": vram_start, "error": None}
        try:
            if not headings:
                result["error"] = "Brak nagłówków do opisu struktury"
                return result

            heading_list = "\n".join([f"Poziom {h['level']}: {h['text']}" for h in headings])
            section_list = ""
            if sections:
                section_list = "\nSekcje:\n" + "\n".join([f"{s['name']} ({s['role']})" for s in sections])

            prompt = (
                f"Opisz strukturę strony w języku polskim na podstawie:\n"
                f"Nagłówki:\n{heading_list}{section_list}\n\nOpis:"
            )
            response = self._generate_response(prompt, max_tokens=250)
            result["text"] = response["text"]
            result["time"] = response["time"]
            result["vram_usage"] = max(vram_start, response["vram_usage"])
            print(f"Wygenerowano opis struktury w {result['time']:.2f}s, VRAM: {result['vram_usage']:.2f} MB")
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
        finally:
            result["time"] = time.time() - start_time
            print(f"Całkowity czas opisu struktury: {result['time']:.2f}s")
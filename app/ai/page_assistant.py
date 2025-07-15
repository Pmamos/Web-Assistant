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
                 model_repo_id: str = "speakleash/Bielik-4.5B-v3.0-Instruct-GGUF",
                 model_filename: str = "Bielik-4.5B-v3.0-Instruct-f16.gguf",
                 models_dir: str = "D:\\magisterka\\modele_LLM",
                 n_gpu_layers: int = -1,
                 n_ctx: int = 32768):
        self.models_dir = models_dir
        self.n_ctx = n_ctx
        self.max_input_tokens = 1024
        self.loaded_context = None
        self.context_chunks = None
        self.chunk_embeddings_cache = None
        self.chunk_relevance_cache = {}
        os.makedirs(self.models_dir, exist_ok=True)

        print(f"Używanie modelu repozytorium: {model_repo_id}, plik modelu: {model_filename}")
        # Inicjalizacja modelu osadzania
        try:
            print("Ładowanie modelu osadzania sentence-transformers...")
            self.embedder = SentenceTransformer('sentence-transformers/static-similarity-mrl-multilingual-v1')
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
            print(f"Dzielę tekst na fragmenty o maksymalnej długości {chunk_size} tokenów")
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
                temperature=0.5,
                top_p=0.9,
                top_k=40,
                repeat_penalty=1.3,
                stop=stop,
                mirostat_mode=2,
                mirostat_tau=5.0,
                mirostat_eta=0.1,
                echo=False
            )
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

    def load_context(self, content: Dict):
        """Ładuje kontekst z danych scrapera, uwzględniając strukturę treści."""
        if not content or not isinstance(content, dict):
            logger.warning("Brak lub nieprawidłowe dane kontekstu.")
            self.loaded_context = None
            self.context_chunks = None
            self.chunk_embeddings_cache = None
            self.chunk_relevance_cache.clear()
            return

        # Budowanie kontekstu z różnych elementów
        context_parts = []

        # Dodaj nagłówki
        if content.get('headings'):
            headings_text = "\n".join([f"### Nagłówek {h['level']}: {h['text']}" for h in content['headings']])
            context_parts.append(f"Nagłówki strony:\n{headings_text}")

        # Dodaj paragrafy
        if content.get('paragraphs'):
            paragraphs_text = "\n".join([f"- {p}" for p in content['paragraphs']])
            context_parts.append(f"Treść paragrafów:\n{paragraphs_text}")

        # Dodaj listy
        if content.get('lists'):
            lists_text = []
            for list_type, lists in content['lists'].items():
                for i, items in enumerate(lists, 1):
                    items_text = "\n".join([f"  * {item}" for item in items])
                    lists_text.append(f"Lista {list_type} {i}:\n{items_text}")
            if lists_text:
                context_parts.append(f"Listy na stronie:\n{'\n'.join(lists_text)}")

        # Dodaj linki
        if content.get('links'):
            links_text = "\n".join([f"- {l['text']} ({l['url']})" for l in content['links']])
            context_parts.append(f"Linki na stronie:\n{links_text}")

        # Dodaj główny tekst
        if content.get('text'):
            context_parts.append(f"Główna treść:\n{content['text']}")

        # Połącz wszystkie części
        combined_context = "\n\n".join([part for part in context_parts if part])
        self.loaded_context = combined_context
        print(f"Załadowano kontekst strony. Długość: {len(combined_context)} znaków")
        print(f"{context_parts}")

        # Dziel na fragmenty i generuj osadzenia
        self.context_chunks = self._chunk_text(combined_context)
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
        print(f"Kontekst strony załadowany. Długość: {len(combined_context)} znaków, fragmentów: {len(self.context_chunks)}")

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
                similarities = similarities.cpu().numpy()
                
                # Wybór top-k fragmentów
                k = min(6, len(self.context_chunks))
                top_indices = np.argsort(similarities)[-k:][::-1]
                max_sim = np.max(similarities)
                dynamic_threshold = max(0.1, max_sim * 0.75)

                relevant_indices = [int(idx) for idx in top_indices if similarities[idx] >= dynamic_threshold]
                if not relevant_indices:
                    relevant_indices = [np.argmax(similarities)]
                    print(f"Użyto awaryjnie najlepszego fragmentu: {similarities[relevant_indices[0]]:.4f}")

                # Rozszerz o sąsiednie fragmenty
                expanded_indices = set()
                for idx in relevant_indices:
                    expanded_indices.add(idx)
                    if idx > 0:
                        expanded_indices.add(idx-1)
                        if idx > 1:
                            expanded_indices.add(idx-2)
                    if idx < len(self.context_chunks)-1:
                        expanded_indices.add(idx+1)
                        if idx < len(self.context_chunks)-2:
                            expanded_indices.add(idx+2)
                relevant_indices = sorted(expanded_indices)
                relevant_chunks = [self.context_chunks[i] for i in relevant_indices]
                self.chunk_relevance_cache[question_key] = relevant_indices
                print(f"Wybrano {len(relevant_chunks)} fragmentów (próg: {dynamic_threshold:.4f})")

            # Połącz fragmenty
            combined_context = "\n\n".join(relevant_chunks)
            # if len(combined_context) > self.n_ctx - 300:
            #     combined_context = combined_context[:self.n_ctx - 300]
            #     last_space = combined_context.rfind(' ')
            #     if last_space > 0:
            #         combined_context = combined_context[:last_space] + " [...]"

            # Generowanie odpowiedzi
            prompt = (
                f"### Kontekst:\n{combined_context}\n\n"
                f"### Pytanie:\n{question}\n\n"
                f"### Instrukcje:\n"
                f"1. Odpowiedz precyzyjnie w języku polskim\n"
                f"2. Jeśli kontekst nie zawiera odpowiedzi, zwróć 'Brak informacji'\n"
                f"3. Unikaj wprowadzenia własnej wiedzy\n"
                f"### Odpowiedź:\n"
            )
            response = self._generate_response(
                prompt, 
                max_tokens=400,
                stop_sequences=["\n###", "<|endoftext|>"]
            )
            result["text"] = response["text"]
            result["time"] = response["time"]
            result["vram_usage"] = max(vram_start, response["vram_usage"])
            print(f"Odpowiedź wygenerowana w {result['time']:.2f}s, VRAM: {result['vram_usage']:.2f} MB")
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
        finally:
            result["time"] = time.time() - start_time
            print(f"Całkowity czas QA: {result['time']:.2f}s")

    def summarize_page(self) -> Dict:
        """Streszcza stronę, wykorzystując strukturalne dane z WebScraper."""
        start_time = time.time()
        vram_start = self._get_vram_usage()
        result = {"text": None, "time": 0.0, "vram_usage": vram_start, "error": None}
        try:
            if not self.loaded_context:
                result["error"] = "Brak załadowanego kontekstu strony"
                return result

            # Pobierz fragmenty z kontekstu
            chunks = self.context_chunks
            if not chunks:
                result["error"] = "Brak fragmentów kontekstu do streszczenia"
                return result
            
            MAX_TOKENS_PER_PROMPT = 28000  

            merged_chunks = []
            current_group = []

            log_content = []  # Lista do przechowywania komunikatów logów

            log_content.append(f"Łączenie fragmentów strony do maksymalnie {MAX_TOKENS_PER_PROMPT} znaków...")
            log_content.append(f"Liczba fragmentów do połączenia: {len(chunks)}")

            current_token_count = 0
            print(f"Łączenie fragmentów strony do maksymalnie {MAX_TOKENS_PER_PROMPT} znaków...")
            print(f"Liczba fragmentów do połączenia: {len(chunks)}")
            for chunk in chunks:
                chunk_token_count = len(self.tokenizer.encode(chunk))
                if chunk_token_count + current_token_count <= MAX_TOKENS_PER_PROMPT:
                    current_group.append(chunk)
                    current_token_count += chunk_token_count
                else:
                    merged_chunks.append("\n\n".join(current_group))
                    current_group = [chunk]
                    current_token_count = chunk_token_count
            print(f"ile grup: {len(merged_chunks)}")
            if current_group:
                merged_chunks.append("\n\n".join(current_group))
            print(f"Połączono w {len(merged_chunks)} grup fragmentów strony")
            print(f"Długość połączonych fragmentów: {sum(len(self.tokenizer.encode(c)) for c in merged_chunks)} tokenów")
            log_content.append(f"Połączono w {len(merged_chunks)} grup fragmentów strony")
            log_content.append(f"Długość połączonych fragmentów: {sum(len(self.tokenizer.encode(c)) for c in merged_chunks)} tokenów")
            with open("merge_chunks_log.txt", "a", encoding="utf-8") as log_file:
                log_file.write("\n".join(log_content) + "\n\n")
                log_file.write("="*80 + "\n")  # Linia separatora między różnymi operacjami

            chunk_summaries = []
            for i, chunk in enumerate(merged_chunks):
                prompt = (
                    f"Stwórz zwięzłe streszczenie fragmentu w języku polskim, maksymalnie 400 słów. "
                    f"Skup się na kluczowych informacjach, takich jak nagłówki, paragrafy i ogólną tematyke strony.\n\n"
                    f"Fragment:\n{chunk}\n\nStreszczenie:"
                )
                summary = self._generate_response(prompt, max_tokens=500)
                if summary["text"]:
                    chunk_summaries.append(summary["text"])
                    print(f"Streszczenie fragmentu {i+1}/{len(merged_chunks)} w {summary['time']:.2f}s")
                else:
                    logger.warning(f"Nie udało się wygenerować streszczenia dla fragmentu {i+1}")
                result["time"] += summary["time"]
                result["vram_usage"] = max(result["vram_usage"], summary["vram_usage"])

            if not chunk_summaries:
                result["error"] = "Brak streszczeń fragmentów"
                return result

            # Połącz streszczenia w jedno
            summaries_text = "\n".join(chunk_summaries)
            if len(chunk_summaries) == 1:
                result["text"] = chunk_summaries[0]
            else:
                final_prompt = (
                    f"Połącz poniższe streszczenia w jedno spójne w języku polskim, maksymalnie 400 słów. "
                    f"Zachowaj kluczowe informacje.\n\n{summaries_text}\n\nFinalne streszczenie:"
                )
                final_response = self._generate_response(final_prompt, max_tokens=500, stop_sequences=["\n\n", "###", "<|endoftext|>", "Streszczenie:"])
                result["text"] = final_response["text"]
                result["time"] += final_response["time"]
                result["vram_usage"] = max(result["vram_usage"], final_response["vram_usage"])

            vram_end = self._get_vram_usage()
            result["vram_usage"] = max(result["vram_usage"], vram_end)
            print(f"Wygenerowano końcowe streszczenie w {result['time']:.2f}s, VRAM: {result['vram_usage']:.2f} MB")
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
        finally:
            result["time"] = time.time() - start_time
            print(f"Całkowity czas streszczania: {result['time']:.2f}s")

    def describe_structure(self, scraped_data: Dict) -> Dict:
        """Opisuje strukturę strony na podstawie danych z WebScraper."""
        start_time = time.time()
        vram_start = self._get_vram_usage()
        result = {"text": None, "time": 0.0, "vram_usage": vram_start, "error": None}
        try:
            headings = scraped_data.get('headings', [])
            sections = scraped_data.get('sections', [])

            if not headings and not sections:
                result["error"] = "Brak danych o nagłówkach lub sekcjach do opisu struktury"
                return result

            heading_list = "\n".join([f"Poziom {h['level']}: {h['text']}" for h in headings])
            section_list = ""
            if sections:
                section_list = "\nSekcje:\n" + "\n".join([f"{s['name']} ({s['role']})" for s in sections])

            prompt = (
                f"Opisz strukturę strony w języku polskim na podstawie poniższych danych:\n"
                f"Nagłówki:\n{heading_list}\n{section_list}\n\n"
                f"Opis:"
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
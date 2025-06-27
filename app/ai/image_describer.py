import logging
import re
import requests
from io import BytesIO
from typing import List, Dict, Optional
from PIL import Image
import torch
from transformers import AutoModelForImageTextToText, AutoModelForSeq2SeqLM, AutoProcessor, AutoTokenizer
from utils.url_utils import clean_text 

logger = logging.getLogger(__name__)

class ImageDescriber:
    def __init__(self, caption_model_id: str = "microsoft/git-large-textcaps",
                 translator_model_id: str = "facebook/nllb-200-distilled-600M"):
        """
        Initializes the image description class for accessibility, compatible with a scraper.

        Args:
            caption_model_id (str): Hugging Face model ID for image captioning.
            translator_model_id (str): Hugging Face model ID for translation (English to Polish).
        """
        try:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Using device: {self.device}")

            # Load captioning model and processor
            self.processor = AutoProcessor.from_pretrained(caption_model_id)
            self.caption_model = AutoModelForImageTextToText.from_pretrained(
                caption_model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            ).to(self.device)
            print(f"Loaded caption model {caption_model_id} on {self.device}")

            # Load translation model and tokenizer (English to Polish)
            self.translator_tokenizer = AutoTokenizer.from_pretrained(translator_model_id)
            self.translator_model = AutoModelForSeq2SeqLM.from_pretrained(
                translator_model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            ).to(self.device)
            self.tgt_lang = "pol_Latn"
            print(f"Loaded translation model {translator_model_id} on {self.device}")
        except Exception as e:
            logger.error(f"Error loading models: {e}")
            raise

    def translate_text(self, text: str) -> str:
        """
        Translates English text to Polish.

        Args:
            text (str): Text to translate.

        Returns:
            str: Translated text in Polish.
        """
        if not text:
            print("Empty text provided for translation")
            return ""

        try:
            tokenizer = self.translator_tokenizer
            model = self.translator_model
            tgt_lang = self.tgt_lang
            self.translator_tokenizer.src_lang = "eng_Latn"

            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self.device)
            forced_bos_token_id=self.translator_tokenizer.convert_tokens_to_ids(tgt_lang)

            outputs = model.generate(
                **inputs,
                forced_bos_token_id=forced_bos_token_id,
                max_length=512
            )

            translated = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            print(f"Translated text: {translated}")
            return translated
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text  # Fallback to original text if translation fails

    def describe_image(self, image_data: Dict, max_tokens: int = 200) -> Optional[str]:
        """
        Generates a detailed image description for blind users if the alt text is insufficient.
        Args:
            image_data (Dict): Dictionary with image data: {'src': str, 'alt': str, 'is_meanful_alt': bool}.
            max_tokens (int: Maximum number of tokens for the generated description.

        Returns:
            Optional[str]: Image description or None if an error occurs.
        """
        try:
            src = image_data.get("src","")
            alt = clean_text(image_data.get("alt", ""))
            is_meaningful_alt = image_data.get("is_meaningful_alt", False)

            print(f"Processing image: {src}")
            print(f"Is alt meaningful?: {'Tak' if is_meaningful_alt else 'Nie'}")

            # Return meaningful alt text after translation if it exists
            if is_meaningful_alt and alt:
                print("Using existing meaningful alt text")
                alt_pl = self.translate_text(alt)
                return alt_pl

            if not src:
                logger.warning("No image URL provided")
                return None

            response = requests.get(src, timeout=15)
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as image:
                image = image.convert("RGB")

                inputs = self.processor(
                    images=image,
                    return_tensors="pt"
                ).to(self.device)

                generated_ids = self.caption_model.generate(
                    pixel_values=inputs["pixel_values"],
                    max_length=max_tokens,
                    num_beams=5,
                    early_stopping=True
                )

                caption = self.processor.decode(generated_ids[0], skip_special_tokens=True)
               
                return self.translate_text(caption)

        except Exception as e:
            logger.error(f"Error describing image {src}: {e}")
            return None

    def describe_images(self, images: List[Dict]) -> List[Dict]:
        """
        Generates descriptions for a list of images from a scraper.

        Args:
            images (List[Dict]): List of dictionaries with image data [{'src': str, 'alt': str, 'is_meaningful_alt': bool}].

        Returns:
            List[Dict]: List of dictionaries with added 'description' field.
        """
        results = []
        for i, image_data in enumerate(images):
            print(f"Processing image {i+1}/{len(images)}")
            description = self.describe_image(image_data)
            result = image_data.copy()
            result["description"] = description or "No description available"
            results.append(result)
        return results
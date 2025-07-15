import json
import logging
import re
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Optional
from readability import Document
from bs4 import BeautifulSoup, Tag, NavigableString
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from utils.url_utils import clean_text, normalize_url, validate_url

logger = logging.getLogger(__name__)

class WebScraper:
    """Scraper internetowy zoptymalizowany dla asystenta głosowego, ekstrakcji wyników wyszukiwania i dostępności."""

    def __init__(self, page: Page):
        """
        Inicjalizuje scraper z istniejącym obiektem Page z Playwright (z BrowserManager).
        
        Args:
            page: Obiekt Playwright Page do renderowania i scrapowania.
        """
        self.page = page
        self.page.route("**/*", self._intercept_route)
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 WebAssistBot/1.0"
        )
    
    def _intercept_route(self, route):
        url = route.request.url
        if any(p in url for p in ['tracker', 'analytics', 'adservice']):
            route.abort()
        else:
            route.continue_()

    def scrape_page(self, url: Optional[str] = None) -> Optional[Dict]:
        """
        Scrapuje stronę i zwraca strukturalne dane: nagłówki, wyniki wyszukiwania, treść, obrazy, linki, sekcje i formularze.
        
        Args:
            url: URL strony do scrapowania (opcjonalny, używa page.url jeśli brak).

        Returns:
            Dict zawierający metadane, nagłówki, wyniki wyszukiwania, treść, obrazy, linki, sekcje i formularze,
            lub None w przypadku błędu.
        """
        if not url:
            url = self.page.url
        if not validate_url(url):
            logger.error(f"Nieprawidłowy URL: {url}")
            return None

        try:
            # 1. Załaduj stronę, jeśli URL różni się od aktualnego
            if url != self.page.url:
                self.page.goto(url, wait_until="commit", timeout=20000)
                self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                self.page.wait_for_selector("body:not(:empty)", timeout=10000)
            print(f"Scrapowanie strony: {url}")

            # 2. Pobierz HTML strony
            html_content = self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")
            
            data = {
                "metadata": {
                    "title": self.page.title(),
                    "url": self.page.url,
                    "language": self.page.evaluate("document.documentElement.lang || 'pl'")
                },
                "headings": self._extract_headings(soup),
                "search_results": self._extract_search_results(soup),
                "content": self._extract_content(soup),
                "images": self._extract_images(soup),
                "links": self._extract_links(soup),
                "sections": self._extract_sections(soup),
                "forms": self._extract_forms(soup)
            }

            with open('output.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return data
        except PlaywrightTimeoutError as e:
            logger.error(f"Przekroczono limit czasu podczas scrapowania {url}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Krytyczny błąd podczas scrapowania {url}: {e}")
            return None

    def _extract_headings(self, soup: BeautifulSoup) -> List[Dict]:
        """Ekstrahuje nagłówki (<h1>-<h6>) z strony, w tym atrybuty ARIA."""
        headings = []
        for tag in soup.find_all(re.compile(r'^h[1-6]$')):
            text = clean_text(tag.get_text())
            if text:
                label = None
                if 'aria-label' in tag.attrs:
                    label = tag['aria-label']
                elif 'aria-labelledby' in tag.attrs:
                    labelledby_id = tag['aria-labelledby']
                    label_elem = soup.find(id=labelledby_id)
                    if label_elem:
                        label = clean_text(label_elem.get_text())
                headings.append({
                    "level": int(tag.name[1]),
                    "text": text,
                    "aria_label": label if label else None
                })
        logger.info(f"Znaleziono {len(headings)} nagłówków")
        return headings

    def _extract_search_results(self, soup: BeautifulSoup) -> List[Dict]:
        """Ekstrahuje tytuły i opisy z wyników wyszukiwania z różnych wyszukiwarek."""
        results = []
        parsed_url = urlparse(self.page.url)
        domain = parsed_url.netloc.lower()

        search_engine_selectors = {
            "google.com": {
                "result": "div.tF2Cxc",
                "title": "h3",
                "link": "a"
            },
            "bing.com": {
                "result": "li.b_algo",
                "title": "h2",
                "link": "a"
            },
            "duckduckgo.com": {
                "result": "div.result",
                "title": "a.result__a",
                "link": "a.result__a"
            }
        }

        for engine, selectors in search_engine_selectors.items():
            if engine in domain:
                result_elements = soup.select(selectors["result"])
                for index, result in enumerate(result_elements[:10], 1):
                    title_elem = result.select_one(selectors["title"])
                    link_elem = result.select_one(selectors["link"])
                    title = clean_text(title_elem.get_text()) if title_elem else "Brak tytułu"
                    url = link_elem['href'] if link_elem and link_elem.has_attr('href') else None
                    if url and validate_url(url):
                        results.append({
                            "index": index,
                            "title": title,
                            "url": normalize_url(url, base_url=self.page.url),
                        })
                break
        logger.info(f"Znaleziono {len(results)} wyników wyszukiwania")
        return results

    def _extract_content(self, soup: BeautifulSoup) -> Dict:
        """Ekstrahuje główną treść strony, w tym ceny, dane kontaktowe i specyfikacje, eliminując reklamy i nieistotne elementy."""
        try:
            def is_visible(tag: Tag) -> bool:
                if not tag or not isinstance(tag, Tag):
                    return False
                # Check for hidden elements via style attributes
                style = tag.attrs.get('style', '').replace(' ', '').lower()
                hidden = ['display:none', 'visibility:hidden', 'opacity:0']
                if any(h in style for h in hidden):
                    return False
                # Exclude non-content tags
                if tag.name in ['script', 'style', 'noscript', 'svg', 'meta', 'head']:
                    return False
                # Exclude advertisement and category-related elements
                ad_category_classes = ['ad', 'banner', 'sponsored', 'advertisement', 'category', 'tag', 'references', 'source']
                class_list = tag.get('class', [])
                if any(c in cls.lower() for cls in class_list for c in ad_category_classes):
                    return False
                return True

            def get_main_candidate(soup: BeautifulSoup) -> Tag:
                """Zwraca najbardziej prawdopodobny tag zawierający treść, w tym ceny i specyfikacje."""
                candidates = [
                    soup.select_one('main'),
                    soup.select_one('article'),
                    soup.select_one('[role="main"]'),
                    soup.select_one('#content'),
                    soup.select_one('.content'),
                    soup.select_one('.description'),
                    soup.select_one('[itemprop="articleBody"]')
                ]
                for c in candidates:
                    if c and len(clean_text(c.get_text(strip=True))) > 100:  # Lowered threshold to include prices/specs
                        return c

                # Fallback: select div with significant text, avoiding ads/categories
                max_div = max(
                    (div for div in soup.find_all('div') if is_visible(div)),
                    key=lambda d: len(clean_text(d.get_text(strip=True))),
                    default=None
                )
                return max_div

            main_content = get_main_candidate(soup)

            # Fallback to Readability if main content is insufficient
            if not main_content or len(clean_text(main_content.get_text(strip=True))) < 100:
                doc = Document(str(soup))
                main_html = doc.summary()
                main_content = BeautifulSoup(main_html, "html.parser")

            # Collect meaningful content, including prices, contact info, and specs
            visible_text_parts = []
            paragraphs = []
            headings = []
            links = []
            lists = {'ordered': [], 'unordered': []}
            base_url = self.page.url

            for elem in main_content.find_all(True):
                if not is_visible(elem):
                    continue

                # Headings
                if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    text = clean_text(elem.get_text(strip=True))
                    if text:
                        headings.append({
                            'level': int(elem.name[1]),
                            'text': text,
                            'aria_label': elem.get('aria-label', None)
                        })
                        visible_text_parts.append(text)

                # Paragraphs
                elif elem.name == 'p':
                    text = clean_text(elem.get_text(strip=True))
                    if text:
                        paragraphs.append(text)
                        visible_text_parts.append(text)

                # Links (collect but don't add to text to avoid noise)
                elif elem.name == 'a' and elem.get('href'):
                    href = normalize_url(elem['href'], base_url=base_url)
                    text = clean_text(elem.get_text(strip=True))
                    if href and validate_url(href):
                        links.append({
                            'text': text or 'Link bez tekstu',
                            'url': href
                        })

                # Lists (include specs or contact info)
                elif elem.name in ['ul', 'ol']:
                    list_type = 'ordered' if elem.name == 'ol' else 'unordered'
                    items = [clean_text(li.get_text(strip=True)) for li in elem.find_all('li') if clean_text(li.get_text(strip=True))]
                    if items:
                        lists[list_type].append(items)
                        visible_text_parts.extend(items)

                # Divs and other elements (include prices, specs, contact info)
                elif is_visible(elem):
                    text = clean_text(elem.get_text(strip=True))
                    if text:
                        visible_text_parts.append(text)

            # Combine visible text, remove duplicates, and ensure clean formatting
            visible_text = ' '.join(list(dict.fromkeys(visible_text_parts)))  # Remove duplicates while preserving order

            word_count = len(visible_text.split())
            sentence_count = len(re.split(r'[.!?]+', visible_text)) - 1 if visible_text else 0
            main_language = self.page.evaluate("document.documentElement.lang") or "unknown"

            return {
                "text": clean_text(visible_text),
                "length": len(visible_text),
                "word_count": word_count,
                "sentence_count": sentence_count,
                "language": main_language,
                "paragraphs": paragraphs,
                "headings": headings,
                "links": links,
                "lists": lists,
                "semantic_tags": list(set(tag.name for tag in main_content.find_all(True) if is_visible(tag))),
                "aria_roles": [role for role in main_content.get('role', '').split() if role] if main_content.has_attr('role') else []
            }

        except Exception as e:
            logger.error(f"Błąd ekstrakcji treści: {e}")
            return {
                "text": "",
                "length": 0,
                "word_count": 0,
                "sentence_count": 0,
                "language": "unknown",
                "paragraphs": [],
                "headings": [],
                "links": [],
                "lists": {'ordered': [], 'unordered': []},
                "semantic_tags": [],
                "aria_roles": []
            }
    
    def _extract_images(self, soup: BeautifulSoup) -> List[Dict]:
        """Ekstrahuje obrazy z sensownymi atrybutami alt, podpisami lub istotnymi nazwami."""
        images = []
        base_url = self.page.url
        seen_srcs = set()

        print(f"\n=== START: Ekstrakcja obrazów ze strony: {base_url} ===")

        # 1. Ekstrahuj obrazy z <figure> z filtrowaniem rozmiaru
        figures = soup.find_all("figure")
        print(f"Znaleziono {len(figures)} tagów <figure>")

        for idx, figure in enumerate(figures, 1):
            img = figure.find("img")
            if img and 'src' in img.attrs:
                src = normalize_url(img["src"], base_url=base_url)
                
                if 'crop=faces&fit=crop&h=32' in src or 'h=32' in src:
                    continue
                    
                alt = img.get("alt", "")
                caption = figure.find("figcaption")

                if caption:
                    caption_text = clean_text(caption.get_text())
                    alt = f"{alt} - {caption_text}".strip() if alt else caption_text

                if src and validate_url(src) and src not in seen_srcs:
                    seen_srcs.add(src)
                    images.append({
                        "src": src,
                        "alt": alt,
                        "is_meaningful_alt": len(alt.strip()) > 20
                    })

        # 2. Ekstrahuj inne obrazy z Playwright
        print("\n--- Próba ekstrakcji obrazów z DOM za pomocą Playwright ---")
        try:
            other_images = self.page.evaluate("""
                () => Array.from(document.images)
                    .filter(img => {
                        const alt = img.alt || '';
                        const src = img.src || '';
                        if (/\\b(profile|avatar|user)\\b/i.test(alt) || 
                            /\\b(profile|avatar|user)\\b/i.test(src)) {
                            return false;
                        }
                        if (img.naturalWidth < 100 && img.naturalHeight < 100) {
                            return false;
                        }
                        if (src.includes('crop=faces') || src.includes('fit=crop') || src.includes('h=32')) {
                            return false;
                        }
                        return (
                            alt.trim().length > 20 ||
                            src.match(/(diagram|schemat|mapa|wykres|chart|infographic|illustration|photo|image)/i) ||
                            img.width >= 100
                        );
                    })
                    .map(img => ({
                        alt: img.alt || '',
                        src: img.src || '',
                        width: img.naturalWidth,
                        height: img.naturalHeight
                    }))
            """)

            for idx, img in enumerate(other_images, 1):
                src = normalize_url(img["src"], base_url=base_url)
                if any(kw in src for kw in ['profile-', 'avatar', 'user=', 'h=32', 'crop=faces']):
                    continue
                if img['width'] < 100 and img['height'] < 100:
                    continue
                    
                alt = clean_text(img["alt"])
                if src and validate_url(src) and src not in seen_srcs:
                    seen_srcs.add(src)
                    images.append({
                        "src": src,
                        "alt": alt,
                        "width": img['width'],
                        "height": img['height'],
                        "is_meaningful_alt": len(alt.strip()) > 20
                    })

            print(f"\n>>> Łącznie znaleziono {len(images)} istotnych obrazów")
        except Exception as e:
            print(f"Błąd ekstrakcji obrazów z Playwright: {e}")
            logger.error(f"Błąd ekstrakcji obrazów: {e}")

        print("=== KONIEC ekstrakcji obrazów ===\n")
        print(f"Znaleziono {len(images)} obrazów na stronie: {base_url}")
        return images

    def _extract_links(self, soup: BeautifulSoup) -> List[Dict]:
        """Ekstrahuje linki z tekstem i URL-ami, pomijając linki nawigacyjne."""
        links = []
        base_url = self.page.url
        try:
            for a in soup.find_all("a", href=True):
                if a.find_parent(lambda tag: tag.has_attr('role') and 'navigation' in tag['role'] or tag.name in ['nav', 'footer']):
                    continue
                href = a["href"].strip()
                text = clean_text(a.get_text(strip=True))
                if not text:
                    img_alt = a.find("img", alt=True)
                    text = clean_text(img_alt["alt"]) if img_alt else "Link bez tekstu"
                if href and not href.startswith(("#", "javascript:")):
                    full_url = normalize_url(href, base_url=base_url)
                    if validate_url(full_url):
                        links.append({
                            "text": text,
                            "url": full_url
                        })
            logger.info(f"Znaleziono {len(links)} linków")
        except Exception as e:
            logger.error(f"Błąd ekstrakcji linków: {e}")
        return links

    def _extract_sections(self, soup: BeautifulSoup) -> List[Dict]:
        """Ekstrahuje sekcje strony (np. <section>, <div> z ARIA) z opisami ról."""
        sections = []
        role_descriptions = {
            "navigation": "nawigacja",
            "main": "główna treść",
            "search": "wyszukiwarka",
            "contentinfo": "informacje o stronie",
            "complementary": "dodatkowe informacje",
            "banner": "baner",
            "region": "sekcja"
        }
        try:
            for elem in soup.select('section, [role], [aria-label], [aria-labelledby]'):
                role = elem.get("role", "unknown")
                description = role_descriptions.get(role, "nieznana rola")
                label = elem.get("aria-label") or elem.get("id") or clean_text(elem.get_text(strip=True)[:50])
                if label:
                    sections.append({
                        "name": label,
                        "id": elem.get("id") or "",
                        "role": role,
                        "description": description
                    })
            logger.info(f"Znaleziono {len(sections)} sekcji")
        except Exception as e:
            logger.error(f"Błąd ekstrakcji sekcji: {e}")
        return sections

    def _extract_forms(self, soup: BeautifulSoup) -> List[Dict]:
        """Ekstrahuje formularze z polami i przyciskami."""
        forms = []
        try:
            for form in soup.find_all("form"):
                fields = []
                for input_elem in form.find_all(["input", "textarea", "select"]):
                    label = None
                    if 'id' in input_elem.attrs:
                        label_elem = form.find("label", attrs={"for": input_elem['id']})
                        if label_elem:
                            label = clean_text(label_elem.get_text())
                    if not label and 'aria-label' in input_elem.attrs:
                        label = input_elem['aria-label']
                    fields.append({
                        "type": input_elem.name,
                        "name": input_elem.get("name", ""),
                        "label": label or "Brak etykiety",
                        "value": input_elem.get("value", "")
                    })
                submit_buttons = [
                    {"text": btn.get_text(strip=True), "type": btn.get("type", "submit")}
                    for btn in form.find_all("button", type="submit")
                ]
                forms.append({
                    "action": form.get("action", ""),
                    "method": form.get("method", "GET"),
                    "fields": fields,
                    "submit_buttons": submit_buttons
                })
            logger.info(f"Znaleziono {len(forms)} formularzy")
        except Exception as e:
            logger.error(f"Błąd ekstrakcji formularzy: {e}")
        return forms
#!/usr/bin/env python3
"""
    BibTeX Field Filler and Formatter

    This script performs two main tasks:
    1) Searches for missing fields in a BibTeX file and fills them using the Crossref API.
    2) Reformats the BibTeX file with consistent indentation and trailing commas.

    Status message logic:
        * [PASS]     (green)  : The entry was already complete.
        * [UPDATED]  (green)  : Some fields were filled and now it is complete.
        * [WARNING]  (red)    : Some fields remain missing.
        * [INFO]     (blue)   : General information messages.
  
    Dependencies:
        * requests
        * tqdm
    
    Examples:
        * python doi_scraper.py
        * python doi_scraper.py -i input.bib -o output.bib
        * python doi_scraper.py --format-only
  
    Author: Alberto Cuadra Lara
    Last Updated: Mar 20 2025
    
    License: MIT
"""

import re
import sys
import logging
import argparse
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from tqdm import tqdm

# ------------------------------
# CONFIGURATION & GLOBAL CONSTANTS
# ------------------------------

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

INDENT_PRE = 4      # Number of spaces before the field name
INDENT_POST = 16    # Column where the '=' sign aligns

FIELD_REGEX = re.compile(r'^\s*([^=\s]+)\s*=\s*(.*?)(,?)\s*$', re.IGNORECASE)

# Global mapping from internal field names to Crossref keys.
CROSSREF_MAPPING: Dict[str, str] = {
    "doi": "DOI",
    "title": "title",
    "journal": "container-title",
    "pages": "page",
    "article_number": "article-number",
    "authors": "author",
    "publisher": "publisher",
    "volume": "volume",
    "number": "issue",
    "year": "published-print"
}

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------

def prepare_title(title: str) -> str:
    """Normalize a title by lowercasing, stripping whitespace, and removing braces/dashes."""
    title = title.lower().strip()
    title = re.sub(r'[–‐]', '-', title)
    title = re.sub(r'--+', '-', title)
    title = re.sub(r'[{}]', '', title)
    return title

def extract_year(date_info: Any) -> Optional[str]:
    """
    Extract the year from a Crossref date-part structure.
    Expected format: {"date-parts": [[year, month, day], ...]}.
    """
    if isinstance(date_info, dict):
        date_parts = date_info.get("date-parts")
        if date_parts and isinstance(date_parts, list) and isinstance(date_parts[0], list) and date_parts[0]:
            return str(date_parts[0][0])
    return None

def format_field(field_name: str, field_value: str) -> str:
    """
    Format a BibTeX field line with uniform indentation and a trailing comma.
    """
    clean_value = field_value.strip().rstrip(',')
    spacing = max(1, INDENT_POST - len(field_name))
    return f"{' ' * INDENT_PRE}{field_name}{' ' * spacing}= {clean_value},"

# ------------------------------
# CROSSREF CLIENT CLASS
# ------------------------------

class CrossrefClient:
    """Handles Crossref API queries with caching and connection reuse."""
    
    def __init__(self) -> None:
        self.cache: Dict[str, Dict[str, str]] = {}
        self.session = requests.Session()
        # Set up a retry strategy for the session
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
    
    def fetch_metadata(self, title: str, rows: int = 3, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata from Crossref for a given title.
        
        :param title: The title to search for.
        :param rows: Number of search results to return.
        :param timeout: Request timeout in seconds.
        :return: Parsed JSON response or None on error.
        """
        api_url = 'https://api.crossref.org/works'
        params = {'query.bibliographic': title, 'rows': rows}
        try:
            response = self.session.get(api_url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error("Error fetching/parsing Crossref data for '%s': %s", title, e)
        return None

    def get_metadata(self, title: str, entry_type: Optional[str] = None) -> Dict[str, str]:
        """
        Retrieve metadata from Crossref for the given title, using caching.
        
        :param title: The title of the BibTeX entry.
        :param entry_type: The entry type (e.g., 'inproceedings') which may adjust the lookup.
        :return: A dictionary mapping field names to their values.
        """
        normalized = prepare_title(title)
        if normalized in self.cache:
            return self.cache[normalized]
        
        response_json = self.fetch_metadata(title)
        if not response_json:
            return {}
        
        items = response_json.get('message', {}).get('items', [])
        if not items:
            return {}
        
        # For inproceedings, prefer items that are proceedings-article or conference-paper
        if entry_type and entry_type.lower() == "inproceedings":
            filtered = [item for item in items if item.get("type") in ["proceedings-article", "conference-paper"]]
            items = filtered if filtered else items
        
        best_item = next((item for item in items if item.get("DOI") and str(item.get("DOI")).strip()), items[0])
        result: Dict[str, str] = {}
        for field in CROSSREF_MAPPING.keys():
            crossref_key = CROSSREF_MAPPING.get(field)
            if not crossref_key:
                continue
            value = best_item.get(crossref_key)
            if field == "year":
                year_val = extract_year(value) or extract_year(best_item.get("published-online"))
                value = year_val
            if isinstance(value, list) and value:
                value = value[0]
            if value:
                value_str = str(value).strip()
                # Skip DOIs ending with ".vid"
                if field == "doi" and value_str.endswith(".vid"):
                    continue
                result[field] = value_str
        self.cache[normalized] = result
        return result

# ------------------------------
# BIBTEX ENTRY CLASSES
# ------------------------------

class BibEntry:
    """
    Base class representing a single BibTeX entry.
    Provides methods for parsing, updating missing fields, and formatting.
    """
    
    def __init__(self, header: str, fields: List[Tuple[str, str]], closing: str) -> None:
        self.header = header
        self.fields = fields
        self.closing = closing

    @classmethod
    def from_text(cls, text: str) -> "BibEntry":
        """
        Parse a BibTeX entry text and return an instance of the appropriate subclass.
        """
        lines = text.strip().splitlines()
        if not lines:
            return cls("", [], "")
        
        header = lines[0].strip()
        closing = "}" if lines[-1].strip() == "}" else ""
        if closing:
            lines = lines[:-1]

        fields: List[Tuple[str, str]] = []
        for line in lines[1:]:
            match = FIELD_REGEX.match(line)
            if match:
                field_name = match.group(1)
                field_value = match.group(2).strip()
                trailing_comma = match.group(3) or ""
                fields.append((field_name, field_value + trailing_comma))
            else:
                if fields:
                    prev_name, prev_val = fields[-1]
                    fields[-1] = (prev_name, prev_val + "\n" + line)
                else:
                    fields.append(("unknown", line))
        
        # Determine entry type from header:
        entry_type = ""
        if header.startswith("@"):
            entry_type = header.split("{")[0][1:].strip().lower()
        
        # Factory logic: instantiate the appropriate subclass.
        entry_classes = {
            "article": Article,
            "book": Book,
            "inproceedings": InProceedings,
            "techreport": TechReport,
            "phdthesis": PhDThesis,
            "mastersthesis": MastersThesis,
            "conference": Conference,
            "unpublished": Unpublished,
            "incollection": InCollection,
        }

        return entry_classes.get(entry_type, BibEntry)(header, fields, closing)
    
    def get_local_title(self) -> str:
        """Extract and return the title from the entry's fields without braces or trailing commas."""
        existing = {name.lower(): value for name, value in self.fields}
        raw_title = existing.get("title", "").rstrip(',').strip()
        return re.sub(r'[{}]', '', raw_title)
    
    def get_entry_type(self) -> str:
        """Return the entry type extracted from the header."""
        if self.header.startswith("@"):
            return self.header.split("{")[0][1:].strip().lower()
        return ""
    
    def get_field_value(self, field_name: str) -> Optional[str]:
        """
        Return a field's value after stripping surrounding braces and trailing commas.
        """
        for name, value in self.fields:
            if name.lower() == field_name.lower():
                val = value.strip().rstrip(',')
                if val.startswith('{') and val.endswith('}'):
                    return val[1:-1]
                return val
        return None
    
    @property
    def required_fields(self) -> List[str]:
        """
        Default required fields for a BibTeX entry.
        Subclasses can override this property.
        """
        return ["doi", "title", "journal", "pages", "volume", "number", "year"]
    
    def get_missing_fields(self) -> List[str]:
        """
        Return a list of required fields that are missing from this entry.
        """
        return [field for field in self.required_fields if not self.get_field_value(field)]
    
    def is_complete(self) -> bool:
        """Check if this entry has all required fields filled."""
        return len(self.get_missing_fields()) == 0

    def _update_fields(self, metadata: Dict[str, str], allowed_fields: Optional[List[str]] = None) -> bool:
        """
        Helper method to update missing fields from metadata using a list of allowed fields.
        
        :param metadata: Dictionary with metadata from Crossref.
        :param allowed_fields: List of field names that can be updated.
                               Defaults to the instance's required_fields.
        :return: True if new fields were added; False otherwise.
        """
        if allowed_fields is None:
            allowed_fields = self.required_fields
        existing = {name.lower(): value.strip() for name, value in self.fields}
        original_fields_count = len(self.fields)
        original_title = self.get_local_title()
        normalized_original_title = prepare_title(original_title)
        
        for field in allowed_fields:
            if not existing.get(field.lower(), "") and field in metadata:
                if field == "doi" and "title" in metadata:
                    normalized_metadata_title = prepare_title(metadata["title"])
                    if normalized_metadata_title != normalized_original_title:
                        continue
                self.fields.append((field, f"{{{metadata[field]}}},"))
        return len(self.fields) > original_fields_count

    def update_with_metadata(self, metadata: Dict[str, str]) -> bool:
        """
        Update this entry with missing fields from the provided metadata.
        Additionally, if the "pages" field is missing, try to fill it using "article_number" from the metadata.
        """
        updated = self._update_fields(metadata)
        if not self.get_field_value("pages") and "article_number" in metadata:
            self.fields.append(("pages", f"{{{metadata['article_number']}}},"))
            updated = True
        return updated

    def format(self) -> str:
        """
        Return the formatted BibTeX entry with uniform indentation and commas.
        """
        lines = [self.header] + [format_field(name, value) for name, value in self.fields]
        if self.closing:
            lines.append(self.closing)
        return "\n".join(lines)

    # ---------------
    # Author Formatting Methods
    # ---------------
    
    def parse_authors_list(self) -> List[str]:
        """
        Parse the 'author' field and return a list of names formatted as "Lastname, F.".
        """
        authors_raw = self.get_field_value("author") or ""
        authors = [a.strip() for a in authors_raw.split(" and ") if a.strip()]
        return [self.format_single_author(author_str) for author_str in authors] if authors else []

    def format_single_author(self, author_str: str) -> str:
        """
        Format a single author name as "Lastname, F.".
          - If a comma exists, assume "Lastname, Firstname(s)".
          - Otherwise, assume "Firstname(s) Lastname".
          - Uses only the first initial of the first name.
        """
        author_str = author_str.strip()
        if not author_str:
            return "Unknown"
        if ',' in author_str:
            parts = [p.strip() for p in author_str.split(',', 1)]
            last_name = parts[0]
            first_part = parts[1] if len(parts) > 1 else ""
            first_name = first_part.split()[0] if first_part else ""
            initial = first_name[0] + "." if first_name else ""
            return f"{last_name}, {initial}"
        else:
            tokens = author_str.split()
            if len(tokens) == 1:
                return f"{tokens[0]}, ?"
            last_name = tokens[-1]
            first_name = tokens[0]
            initial = first_name[0] + "." if first_name else ""
            return f"{last_name}, {initial}"

    def format_authors_short(self) -> str:
        """
        Return a short authors string:
          - No authors: "Unknown Author"
          - 1 author: "Lastname, F."
          - 2 authors: "Auth1 and Auth2"
          - More than 2: "Auth1 et al."
        """
        authors = self.parse_authors_list()
        if not authors:
            return "Unknown Author"
        if len(authors) == 1:
            return authors[0]
        elif len(authors) == 2:
            return f"{authors[0]} and {authors[1]}"
        else:
            return f"{authors[0]} et al."

# ------------------------------
# ENTRY TYPE SUBCLASSES
# ------------------------------

class Article(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "year", "journal", "pages", "volume", "number", "doi"]

    def update_with_metadata(self, metadata: Dict[str, str]) -> bool:
        return super().update_with_metadata(metadata)

    def format(self) -> str:
        return super().format()

class Book(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "year", "publisher"]

    def update_with_metadata(self, metadata: Dict[str, str]) -> bool:
        return super().update_with_metadata(metadata)

    def format(self) -> str:
        return super().format()

class InProceedings(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "year", "doi", "pages"]

    def update_with_metadata(self, metadata: Dict[str, str]) -> bool:
        return super().update_with_metadata(metadata)

    def format(self) -> str:
        return super().format()

class TechReport(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        # Exclude 'journal' for tech reports.
        return ["author", "title", "year"]

    def update_with_metadata(self, metadata: Dict[str, str]) -> bool:
        # Remove any existing journal field before updating.
        self.fields = [field for field in self.fields if field[0].lower() != "journal"]
        return super().update_with_metadata(metadata)

    def format(self) -> str:
        return super().format()

class PhDThesis(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "school", "year"]

class MastersThesis(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "school", "year"]

class Conference(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "booktitle", "year"]

class Unpublished(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "year"]

class InCollection(BibEntry):
    @property
    def required_fields(self) -> List[str]:
        return ["author", "title", "booktitle", "publisher", "year"]

# ------------------------------
# CONCURRENT FILLING FUNCTION
# ------------------------------

def fill_entries_concurrently(entries: List[BibEntry], client: CrossrefClient) -> None:
    """
    Perform concurrent Crossref lookups grouped by normalized title,
    update entries with fetched metadata, and print per-entry status messages.
    """
    title_to_entries: Dict[str, List[BibEntry]] = {}
    for entry in entries:
        local_title = entry.get_local_title()
        if local_title:
            norm = prepare_title(local_title)
            title_to_entries.setdefault(norm, []).append(entry)
    
    total_groups = len(title_to_entries)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_group: Dict[Any, Tuple[str, List[BibEntry]]] = {}
        for norm_title, entry_list in title_to_entries.items():
            rep_entry = entry_list[0]
            local_title = rep_entry.get_local_title()
            entry_type = rep_entry.get_entry_type()
            future = executor.submit(client.get_metadata, local_title, entry_type)
            future_to_group[future] = (norm_title, entry_list)
        
        for future in tqdm(as_completed(future_to_group), total=total_groups, desc="Processing groups"):
            norm_title, group_entries = future_to_group[future]
            metadata = future.result()
            for entry in group_entries:
                was_complete_before = entry.is_complete()
                entry.update_with_metadata(metadata)
                missing_fields = entry.get_missing_fields()
                still_missing = bool(missing_fields)

                if was_complete_before:
                    status = "[PASS]"
                    color = "\033[92m"  # green
                else:
                    if not still_missing:
                        status = "[UPDATED]"
                        color = "\033[92m"  # green
                    else:
                        status = "[WARNING]"
                        color = "\033[91m"  # red
                
                authors_str = entry.format_authors_short()
                year = entry.get_field_value("year") or "n.d."
                title = entry.get_local_title() or "Untitled"
                msg = f"{status} {authors_str} ({year}), {title}"
                doi = entry.get_field_value("doi")
                if doi:
                    msg += f", DOI: https://doi.org/{doi}"
                if still_missing:
                    msg += f" - MISSING FIELDS: {', '.join(missing_fields)}"
                
                if color:
                    msg = f"{color}{status}\033[0m {authors_str} ({year}), {title}"
                    if doi:
                        msg += f", DOI: https://doi.org/{doi}"
                    if still_missing:
                        msg += f" - MISSING FIELDS: {', '.join(missing_fields)}"
                
                tqdm.write(msg)

# ------------------------------
# FILE PROCESSING & MAIN FUNCTION
# ------------------------------

def process_bib_file(input_path: str, output_path: str, format_only: bool = False) -> None:
    """
    Read the input BibTeX file, optionally update missing fields using Crossref,
    and write the formatted content to the output file.
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except IOError as e:
        logging.error("Error reading file %s: %s", input_path, e)
        sys.exit(1)
    
    # Split the file into individual entries by lines that start with '@'
    raw_entries = re.split(r'(?=@)', content)
    entries: List[BibEntry] = [BibEntry.from_text(text) for text in raw_entries if text.strip()]
    
    if not format_only:
        client = CrossrefClient()
        fill_entries_concurrently(entries, client)
    
    updated_content = "\n\n".join(entry.format() for entry in entries) + "\n"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
    except IOError as e:
        logging.error("Error writing to file %s: %s", output_path, e)
        sys.exit(1)
    
    tqdm.write(f"\033[94m[INFO] Updated .bib file saved as {output_path}\033[0m")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill missing BibTeX fields using Crossref or reformat the .bib file with uniform formatting."
    )
    parser.add_argument('-i', '--input', default='input.bib', help="Path to the input .bib file")
    parser.add_argument('-o', '--output', default='output.bib', help="Path to the output .bib file")
    parser.add_argument('--format-only', action='store_true', help="Only reformat without performing Crossref lookups")
    args = parser.parse_args()
    process_bib_file(args.input, args.output, format_only=args.format_only)

if __name__ == "__main__":
    main()

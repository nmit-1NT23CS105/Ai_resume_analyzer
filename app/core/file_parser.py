"""File parsing helpers for TXT, DOCX, and PDF uploads."""

from __future__ import annotations

import hashlib
import io
import re
import zlib
import zipfile
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from threading import RLock
from xml.etree import ElementTree as ET

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised only when dependency is unavailable
    PdfReader = None

from app.core.text_processing import compact_whitespace

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
SUPPORTED_FILE_TYPES = {".txt", ".docx", ".pdf"}
WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
CACHE_ENTRY_LIMIT = 12
PDF_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
PDF_TEXT_BLOCK_PATTERN = re.compile(rb"BT(.*?)ET", re.DOTALL)
PDF_LITERAL_SHOW_PATTERN = re.compile(rb"(\((?:\\.|[^\\()])*\))\s*(?:Tj|'|\")")
PDF_HEX_SHOW_PATTERN = re.compile(rb"(<[0-9A-Fa-f\s]+>)\s*Tj")
PDF_ARRAY_SHOW_PATTERN = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
PDF_LITERAL_PATTERN = re.compile(rb"\((?:\\.|[^\\()])*\)")
PDF_HEX_PATTERN = re.compile(rb"<([0-9A-Fa-f\s]+)>")
_TEXT_CACHE: OrderedDict[str, tuple[str, str]] = OrderedDict()
_CACHE_LOCK = RLock()


class FileParsingError(ValueError):
    """Raised when an uploaded file cannot be parsed safely."""


def validate_upload(filename: str | None, file_bytes: bytes) -> str:
    if not filename:
        raise FileParsingError("Uploaded file must include a filename.")

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_FILE_TYPES:
        raise FileParsingError("Supported file types are .txt, .docx, and .pdf.")
    if not file_bytes:
        raise FileParsingError("Uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileParsingError("Uploaded file exceeds the 5 MB size limit.")

    return extension


def extract_text_from_bytes(filename: str | None, file_bytes: bytes) -> tuple[str, str]:
    extension = validate_upload(filename, file_bytes)
    cache_key = _build_cache_key(extension, file_bytes)

    with _CACHE_LOCK:
        cached = _TEXT_CACHE.get(cache_key)
        if cached is not None:
            _TEXT_CACHE.move_to_end(cache_key)
            return cached

    if extension == ".txt":
        result = (extension, _extract_text_from_txt(file_bytes))
    elif extension == ".docx":
        result = (extension, _extract_text_from_docx(file_bytes))
    elif extension == ".pdf":
        result = (extension, _extract_text_from_pdf(file_bytes))
    else:
        raise FileParsingError("Unsupported file type.")

    with _CACHE_LOCK:
        _TEXT_CACHE[cache_key] = result
        _TEXT_CACHE.move_to_end(cache_key)
        while len(_TEXT_CACHE) > CACHE_ENTRY_LIMIT:
            _TEXT_CACHE.popitem(last=False)

    return result


def normalize_document_text(text: str) -> str:
    normalized_lines: list[str] = []
    previous_blank = False

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = compact_whitespace(raw_line)
        if cleaned:
            normalized_lines.append(cleaned)
            previous_blank = False
        elif normalized_lines and not previous_blank:
            normalized_lines.append("")
            previous_blank = True

    if normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()

    return "\n".join(normalized_lines).strip()


def _build_cache_key(extension: str, file_bytes: bytes) -> str:
    digest = hashlib.blake2b(file_bytes, digest_size=16).hexdigest()
    return f"{extension}:{len(file_bytes)}:{digest}"


def _extract_text_from_txt(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            text = file_bytes.decode(encoding)
            normalized = normalize_document_text(text)
            if normalized:
                return normalized
        except UnicodeDecodeError:
            continue

    raise FileParsingError("Unable to decode the uploaded text file.")


def _extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            if "word/document.xml" not in archive.namelist():
                raise FileParsingError("The uploaded DOCX file does not contain readable document text.")

            paragraphs = _extract_docx_member_text(archive.read("word/document.xml"))
            if not paragraphs:
                fallback_members = [
                    name
                    for name in archive.namelist()
                    if name.startswith("word/header") or name.startswith("word/footer")
                ]
                for member in fallback_members:
                    paragraphs.extend(_extract_docx_member_text(archive.read(member)))
    except zipfile.BadZipFile as exc:
        raise FileParsingError("The uploaded DOCX file is invalid or corrupted.") from exc
    except ET.ParseError as exc:
        raise FileParsingError("The uploaded DOCX file could not be parsed.") from exc

    normalized = normalize_document_text("\n".join(paragraphs))
    if not normalized:
        raise FileParsingError("No readable text was found in the DOCX file.")

    return normalized


def _extract_docx_member_text(member_bytes: bytes) -> list[str]:
    xml_root = ET.fromstring(member_bytes)
    paragraphs: list[str] = []

    for paragraph in xml_root.findall(".//w:p", WORD_NAMESPACE):
        fragments = [
            node.text.strip()
            for node in paragraph.findall(".//w:t", WORD_NAMESPACE)
            if node.text and node.text.strip()
        ]
        if fragments:
            paragraphs.append(" ".join(fragments))

    return paragraphs


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    if not file_bytes.startswith(b"%PDF"):
        raise FileParsingError("The uploaded PDF file is invalid.")

    extracted_with_pypdf = _extract_text_from_pdf_with_pypdf(file_bytes)
    if extracted_with_pypdf:
        return extracted_with_pypdf

    fragments: list[str] = []
    for stream in _iter_pdf_streams(file_bytes):
        fragments.extend(_extract_text_fragments_from_pdf_stream(stream))

    if not fragments:
        fragments.extend(_extract_text_fragments_from_pdf_stream(file_bytes))

    normalized = normalize_document_text("\n".join(fragment.strip() for fragment in fragments if fragment.strip()))
    if normalized:
        return normalized

    raise FileParsingError(
        "No readable text was found in the PDF file. Image-based PDFs require OCR, which is not included yet."
    )


def _extract_text_from_pdf_with_pypdf(file_bytes: bytes) -> str | None:
    if PdfReader is None:
        return None

    try:
        reader = PdfReader(io.BytesIO(file_bytes), strict=False)
    except Exception:
        return None

    page_texts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        if text.strip():
            page_texts.append(text)

    normalized = normalize_document_text("\n\n".join(page_texts))
    return normalized or None


def _iter_pdf_streams(file_bytes: bytes) -> list[bytes]:
    streams: list[bytes] = []
    for match in PDF_STREAM_PATTERN.finditer(file_bytes):
        stream_data = match.group(1)
        prefix = file_bytes[max(0, match.start() - 250) : match.start()]

        if b"/FlateDecode" in prefix:
            try:
                stream_data = zlib.decompress(stream_data)
            except zlib.error:
                continue

        streams.append(stream_data)

    return streams


def _extract_text_fragments_from_pdf_stream(stream_bytes: bytes) -> list[str]:
    fragments: list[str] = []
    text_blocks = [match.group(1) for match in PDF_TEXT_BLOCK_PATTERN.finditer(stream_bytes)] or [stream_bytes]

    for block in text_blocks:
        for match in PDF_LITERAL_SHOW_PATTERN.finditer(block):
            decoded = _decode_pdf_literal_string(match.group(1)[1:-1])
            if decoded.strip():
                fragments.append(decoded)

        for match in PDF_HEX_SHOW_PATTERN.finditer(block):
            decoded = _decode_pdf_hex_string(match.group(1)[1:-1])
            if decoded.strip():
                fragments.append(decoded)

        for match in PDF_ARRAY_SHOW_PATTERN.finditer(block):
            decoded = _decode_pdf_array(match.group(1))
            if decoded.strip():
                fragments.append(decoded)

    return fragments


def _decode_pdf_array(array_bytes: bytes) -> str:
    parts: list[str] = []

    for literal in PDF_LITERAL_PATTERN.findall(array_bytes):
        decoded = _decode_pdf_literal_string(literal[1:-1])
        if decoded:
            parts.append(decoded)

    for hex_literal in PDF_HEX_PATTERN.findall(array_bytes):
        decoded = _decode_pdf_hex_string(hex_literal)
        if decoded:
            parts.append(decoded)

    return "".join(parts)


@lru_cache(maxsize=256)
def _decode_pdf_hex_string(hex_literal: bytes) -> str:
    cleaned = re.sub(rb"\s+", b"", hex_literal)
    if not cleaned:
        return ""
    if len(cleaned) % 2:
        cleaned += b"0"

    try:
        raw_bytes = bytes.fromhex(cleaned.decode("ascii"))
    except ValueError:
        return ""

    for encoding in ("utf-16-be", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            if text.strip():
                return text
        except UnicodeDecodeError:
            continue

    return ""


def _decode_pdf_literal_string(literal: bytes) -> str:
    decoded = bytearray()
    index = 0

    while index < len(literal):
        byte = literal[index]

        if byte != 92:
            decoded.append(byte)
            index += 1
            continue

        index += 1
        if index >= len(literal):
            break

        escaped = literal[index]
        simple_escapes = {
            ord("n"): b"\n",
            ord("r"): b"\r",
            ord("t"): b"\t",
            ord("b"): b"\b",
            ord("f"): b"\f",
            ord("("): b"(",
            ord(")"): b")",
            ord("\\"): b"\\",
        }

        if escaped in simple_escapes:
            decoded.extend(simple_escapes[escaped])
            index += 1
            continue

        if escaped in b"\r\n":
            if escaped == ord("\r") and index + 1 < len(literal) and literal[index + 1] == ord("\n"):
                index += 2
            else:
                index += 1
            continue

        if 48 <= escaped <= 55:
            octal_digits = bytes([escaped])
            index += 1
            for _ in range(2):
                if index < len(literal) and 48 <= literal[index] <= 55:
                    octal_digits += bytes([literal[index]])
                    index += 1
                else:
                    break
            decoded.append(int(octal_digits, 8))
            continue

        decoded.append(escaped)
        index += 1

    return decoded.decode("latin-1", errors="ignore")

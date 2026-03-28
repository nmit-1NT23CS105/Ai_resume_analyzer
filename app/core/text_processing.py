"""Lightweight text processing helpers for resume analysis."""

from __future__ import annotations

import math
import re
from collections import Counter

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
    "using",
    "used",
    "build",
    "built",
    "developed",
    "implemented",
    "experience",
    "project",
    "projects",
    "system",
    "application",
    "applications",
    "work",
    "team",
    "skills",
    "skill",
    "candidate",
    "candidates",
    "role",
    "job",
    "description",
    "requirements",
}

IMPORTANT_SHORT_TOKENS = {"ai", "ml", "nlp", "sql", "aws", "api", "etl", "cv"}
TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-/]{1,}")
EMAIL_PATTERN = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3}\)?[\s\-]?)?\d{3}[\s\-]?\d{4}")


def compact_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_token(token: str) -> str:
    return token.lower().replace(".", "").replace("-", "")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_PATTERN.findall(text.lower()):
        token = normalize_token(raw_token)
        if token in STOP_WORDS:
            continue
        if len(token) < 3 and token not in IMPORTANT_SHORT_TOKENS:
            continue
        tokens.append(token)
    return tokens


def term_frequency(tokens: list[str]) -> Counter[str]:
    return Counter(tokens)


def cosine_similarity(text_a: str, text_b: str) -> float:
    tokens_a = tokenize(text_a)
    tokens_b = tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0

    documents = [term_frequency(tokens_a), term_frequency(tokens_b)]
    vocabulary = set(documents[0]) | set(documents[1])

    vector_a: list[float] = []
    vector_b: list[float] = []

    for term in vocabulary:
        document_frequency = sum(1 for document in documents if term in document)
        idf = math.log((len(documents) + 1) / (document_frequency + 1)) + 1
        vector_a.append(documents[0].get(term, 0) * idf)
        vector_b.append(documents[1].get(term, 0) * idf)

    dot_product = sum(left * right for left, right in zip(vector_a, vector_b, strict=False))
    magnitude_a = math.sqrt(sum(value * value for value in vector_a))
    magnitude_b = math.sqrt(sum(value * value for value in vector_b))
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def top_keywords(text: str, limit: int = 10) -> list[str]:
    counts = term_frequency(tokenize(text))
    return [keyword for keyword, _ in counts.most_common(limit)]


def shared_keywords(text_a: str, text_b: str, limit: int = 10) -> list[str]:
    counts_a = term_frequency(tokenize(text_a))
    counts_b = term_frequency(tokenize(text_b))
    overlap = [
        (keyword, counts_a[keyword] + counts_b[keyword])
        for keyword in set(counts_a) & set(counts_b)
    ]
    overlap.sort(key=lambda item: (-item[1], item[0]))
    return [keyword for keyword, _ in overlap[:limit]]


def extract_contact_info(text: str) -> dict[str, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name = None
    for line in lines[:3]:
        if "@" in line or any(character.isdigit() for character in line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and len(line) <= 40:
            name = line.title()
            break

    email_match = EMAIL_PATTERN.search(text)
    phone_match = PHONE_PATTERN.search(text)

    return {
        "name": name,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0) if phone_match else None,
    }


import re

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "based",
    "by",
    "for",
    "from",
    "in",
    "latest",
    "most",
    "ones",
    "recent",
    "show",
    "the",
    "top",
    "total",
}

def query_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) >= 2 and token not in STOPWORDS:
            tokens.add(token)
    return tokens

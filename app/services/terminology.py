"""Conservative text normalization for registered clinical terminology.

NFKC normalizes typographic variants, and whitespace folding and casefolding
support exact-name comparison. Punctuation, doses, and chemical identifiers
are intentionally preserved; this is not clinical ontology resolution.
"""

import unicodedata


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()

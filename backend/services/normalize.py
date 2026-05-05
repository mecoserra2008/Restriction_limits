"""
Cross-source identifier normalisation.

The limits workbook uses Portuguese-language values (``Portugal``,
``Espanha``, ``Caixa Geral de Depositos``, …) while Bloomberg fields
typically use ISO-2 codes (``PT``, ``ES``) or English names. The
aggregator must compare these consistently, so every match goes through
``canonical_country`` / ``canonical_text``.

The mapping is intentionally conservative: only entries we are
*sure* about (Portugal-centric names, neighbouring sovereigns, common
abbreviations). Unknown values are returned unchanged after lower-case
+ accent strip, which keeps "fuzzy equality" working in 99% of cases.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

# ISO-2, ISO-3 and Portuguese / English names mapped to a canonical token
# (lowercase, accent-free, single-word).
_COUNTRY_ALIASES = {
    # Portugal
    "pt": "portugal", "prt": "portugal", "portugal": "portugal",
    # Spain
    "es": "spain", "esp": "spain", "spain": "spain", "espanha": "spain",
    "espana": "spain",
    # France
    "fr": "france", "fra": "france", "france": "france", "franca": "france",
    # Germany
    "de": "germany", "deu": "germany", "germany": "germany",
    "alemanha": "germany",
    # Italy
    "it": "italy", "ita": "italy", "italy": "italy", "italia": "italy",
    # United Kingdom
    "gb": "united_kingdom", "uk": "united_kingdom", "gbr": "united_kingdom",
    "united kingdom": "united_kingdom", "reino unido": "united_kingdom",
    # Ireland
    "ie": "ireland", "irl": "ireland", "ireland": "ireland",
    "irlanda": "ireland",
    # Netherlands
    "nl": "netherlands", "nld": "netherlands", "netherlands": "netherlands",
    "holanda": "netherlands", "paises baixos": "netherlands",
    # Belgium
    "be": "belgium", "bel": "belgium", "belgium": "belgium",
    "belgica": "belgium",
    # United States
    "us": "united_states", "usa": "united_states", "u.s.": "united_states",
    "u.s.a.": "united_states", "united states": "united_states",
    "estados unidos": "united_states",
    # Switzerland
    "ch": "switzerland", "che": "switzerland", "switzerland": "switzerland",
    "suica": "switzerland",
    # Brazil
    "br": "brazil", "bra": "brazil", "brazil": "brazil", "brasil": "brazil",
    # Luxembourg
    "lu": "luxembourg", "lux": "luxembourg", "luxembourg": "luxembourg",
    "luxemburgo": "luxembourg",
    # Austria
    "at": "austria", "aut": "austria", "austria": "austria",
    # Sweden
    "se": "sweden", "swe": "sweden", "sweden": "sweden", "suecia": "sweden",
    # Finland
    "fi": "finland", "fin": "finland", "finland": "finland",
    "finlandia": "finland",
    # Norway
    "no": "norway", "nor": "norway", "norway": "norway", "noruega": "norway",
    # Denmark
    "dk": "denmark", "dnk": "denmark", "denmark": "denmark",
    "dinamarca": "denmark",
    # Greece
    "gr": "greece", "grc": "greece", "greece": "greece", "grecia": "greece",
    # Poland
    "pl": "poland", "pol": "poland", "poland": "poland", "polonia": "poland",
}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def canonical_text(s: Optional[str]) -> Optional[str]:
    """Lowercase + accent-strip + collapse whitespace."""
    if s is None:
        return None
    out = _strip_accents(str(s)).strip().lower()
    return " ".join(out.split()) or None


def canonical_country(s: Optional[str]) -> Optional[str]:
    """Map ``Portugal`` / ``PT`` / ``PRT`` / ``portugal`` to the same token."""
    base = canonical_text(s)
    if base is None:
        return None
    return _COUNTRY_ALIASES.get(base, base)

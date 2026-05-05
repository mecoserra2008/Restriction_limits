from backend.services.normalize import canonical_country, canonical_text


def test_country_aliases_collapse_to_one_token():
    assert canonical_country("PT") == "portugal"
    assert canonical_country("Portugal") == "portugal"
    assert canonical_country("portugal") == "portugal"
    assert canonical_country("PRT") == "portugal"
    assert canonical_country("Espanha") == "spain"
    assert canonical_country("ES") == "spain"


def test_country_unknown_falls_back_to_canonical_text():
    assert canonical_country("Atlantis") == "atlantis"
    assert canonical_country(None) is None


def test_canonical_text_strips_accents_and_collapses_spaces():
    assert canonical_text("  São  Paulo ") == "sao paulo"
    assert canonical_text("CAIXA  Geral") == "caixa geral"
    assert canonical_text("") is None
    assert canonical_text(None) is None

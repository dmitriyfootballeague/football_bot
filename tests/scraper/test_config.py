from scraper.config import _parse_allowed_tournaments


def test_parse_allowed_tournaments_empty_string_returns_empty_set():
    assert _parse_allowed_tournaments("") == set()


def test_parse_allowed_tournaments_whitespace_only_returns_empty_set():
    assert _parse_allowed_tournaments("   ") == set()


def test_parse_allowed_tournaments_parses_comma_separated_values():
    raw = "Optic, Premier League, Cup"
    expected = {"Optic", "Premier League", "Cup"}

    assert _parse_allowed_tournaments(raw) == expected


def test_parse_allowed_tournaments_ignores_empty_items_and_trims_spaces():
    raw = " Optic , , Premier League ,, Cup  "
    expected = {"Optic", "Premier League", "Cup"}

    assert _parse_allowed_tournaments(raw) == expected

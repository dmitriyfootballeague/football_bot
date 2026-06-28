from scraper.config import DBConfig, _parse_allowed_tournaments


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


def test_scraper_db_config_exposes_shared_pool_settings():
    config = DBConfig()

    assert config.db_echo is False
    assert config.db_pool_size == 5
    assert config.db_max_overflow == 0
    assert config.db_pool_pre_ping is True
    assert config.db_pool_recycle == 1800

import asyncio

from scraper.match_scraper import (
    _collect_match_urls_from_hrefs,
    _scrape_tournament_match_urls_from_page,
    scrape_tournament_match_stats,
)
from scraper.scraped_data import ScrapedMatchPlayerStat, ScrapedTournament


def _make_stat(match_external_id: str, player_external_id: str) -> ScrapedMatchPlayerStat:
    return ScrapedMatchPlayerStat(
        match_external_id=match_external_id,
        match_url=f"https://olesports.ru/match/{match_external_id}",
        tournament="League",
        player_external_id=player_external_id,
        player_name="Ivan Petrov",
        team_name="Club A",
        opponent_name="Club B",
        is_home=True,
        in_roster=True,
        started=True,
        mvp=False,
        team_goals=2,
        opponent_goals=1,
        goals_conceded=1,
        team_won=True,
    )


def test_scrape_tournament_match_stats_flattens_match_rows(monkeypatch):
    calls = []

    async def fake_scrape_tournament_match_urls(_pw, tournament_url):
        assert tournament_url == "https://olesports.ru/tournament/1"
        return [
            "https://olesports.ru/match/m1",
            "https://olesports.ru/match/m2",
        ]

    async def fake_scrape_match_player_stats(_pw, match_url, tournament_name):
        calls.append((match_url, tournament_name))
        match_id = match_url.rsplit("/", 1)[-1]
        return [_make_stat(match_id, f"{match_id}-p1")]

    monkeypatch.setattr(
        "scraper.match_scraper.scrape_tournament_match_urls",
        fake_scrape_tournament_match_urls,
    )
    monkeypatch.setattr(
        "scraper.match_scraper.scrape_match_player_stats",
        fake_scrape_match_player_stats,
    )

    tournament = ScrapedTournament(
        name="League",
        external_id="t1",
        url="https://olesports.ru/tournament/1",
    )

    stats = asyncio.run(scrape_tournament_match_stats(object(), tournament))

    assert [stat.match_external_id for stat in stats] == ["m1", "m2"]
    assert calls == [
        ("https://olesports.ru/match/m1", "League"),
        ("https://olesports.ru/match/m2", "League"),
    ]


def test_scrape_tournament_match_stats_keeps_successful_rows_on_error(monkeypatch):
    async def fake_scrape_tournament_match_urls(_pw, _tournament_url):
        return [
            "https://olesports.ru/match/m1",
            "https://olesports.ru/match/m2",
        ]

    async def fake_scrape_match_player_stats(_pw, match_url, tournament_name):
        assert tournament_name == "League"
        if match_url.endswith("/m2"):
            raise RuntimeError("boom")
        return [_make_stat("m1", "m1-p1")]

    monkeypatch.setattr(
        "scraper.match_scraper.scrape_tournament_match_urls",
        fake_scrape_tournament_match_urls,
    )
    monkeypatch.setattr(
        "scraper.match_scraper.scrape_match_player_stats",
        fake_scrape_match_player_stats,
    )

    tournament = ScrapedTournament(name="League", external_id="t1", url="u1")

    stats = asyncio.run(scrape_tournament_match_stats(object(), tournament))

    assert [stat.match_external_id for stat in stats] == ["m1"]


def test_scrape_tournament_match_stats_keeps_successful_rows_on_empty_match(monkeypatch):
    async def fake_scrape_tournament_match_urls(_pw, _tournament_url):
        return [
            "https://olesports.ru/match/m1",
            "https://olesports.ru/match/m2",
        ]

    async def fake_scrape_match_player_stats(_pw, match_url, tournament_name):
        assert tournament_name == "League"
        if match_url.endswith("/m2"):
            return []
        return [_make_stat("m1", "m1-p1")]

    monkeypatch.setattr(
        "scraper.match_scraper.scrape_tournament_match_urls",
        fake_scrape_tournament_match_urls,
    )
    monkeypatch.setattr(
        "scraper.match_scraper.scrape_match_player_stats",
        fake_scrape_match_player_stats,
    )

    tournament = ScrapedTournament(name="League", external_id="t1", url="u1")

    stats = asyncio.run(scrape_tournament_match_stats(object(), tournament))

    assert [stat.match_external_id for stat in stats] == ["m1"]


def test_collect_match_urls_from_hrefs_deduplicates_and_normalizes_urls():
    urls = _collect_match_urls_from_hrefs(
        [
            "/match/m1",
            "https://olesports.ru/match/m1?tab=roster",
            "/club/c1",
            "/match/m2/",
            "",
        ]
    )

    assert urls == [
        "https://olesports.ru/match/m1",
        "https://olesports.ru/match/m2/",
    ]


class _FakePage:
    def __init__(self, hrefs):
        self.hrefs = hrefs

    async def eval_on_selector_all(self, _selector, _script):
        return self.hrefs


def test_scrape_tournament_match_urls_from_page_prefers_full_results_api(monkeypatch):
    page = _FakePage(
        [
            "/match/m1",
            "/match/m2",
        ]
    )
    calls = []

    async def fake_fetch_result_match_urls(_page, *, tournament_external_id, layout):
        calls.append((tournament_external_id, layout))
        if layout == "bytour":
            return [
                "https://olesports.ru/match/m1",
                "https://olesports.ru/match/m2",
                "https://olesports.ru/match/m3",
            ]
        if layout == "bydate":
            return [
                "https://olesports.ru/match/m3",
                "https://olesports.ru/match/m4",
            ]
        return []

    monkeypatch.setattr(
        "scraper.match_scraper._fetch_result_match_urls",
        fake_fetch_result_match_urls,
    )

    urls = asyncio.run(
        _scrape_tournament_match_urls_from_page(
            page,
            "https://olesports.ru/tournament/t1",
        )
    )

    assert calls == [("t1", "bytour"), ("t1", "bydate")]
    assert urls == [
        "https://olesports.ru/match/m1",
        "https://olesports.ru/match/m2",
        "https://olesports.ru/match/m3",
        "https://olesports.ru/match/m4",
    ]


def test_scrape_tournament_match_urls_from_page_falls_back_to_dom_when_results_api_empty(monkeypatch):
    page = _FakePage(
        [
            "/match/m1",
            "/match/m2",
            "/match/m2?tab=summary",
        ]
    )

    async def fake_fetch_result_match_urls(_page, *, tournament_external_id, layout):
        assert tournament_external_id == "t1"
        return []

    monkeypatch.setattr(
        "scraper.match_scraper._fetch_result_match_urls",
        fake_fetch_result_match_urls,
    )

    urls = asyncio.run(
        _scrape_tournament_match_urls_from_page(
            page,
            "https://olesports.ru/tournament/t1",
        )
    )

    assert urls == [
        "https://olesports.ru/match/m1",
        "https://olesports.ru/match/m2",
    ]

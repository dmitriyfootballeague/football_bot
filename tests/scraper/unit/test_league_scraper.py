import asyncio

from scraper.league_scraper import LeagueScraper, _resolve_player_tournament
from scraper.scraped_data import ScrapedPlayer, ScrapedTeam, ScrapedTournament


class FakeAsyncPlaywrightContext:
    def __init__(self, pw):
        self.pw = pw

    async def __aenter__(self):
        return self.pw

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummyPlaywright:
    pass


def test_scrape_tournaments_passes_allowed_filter(monkeypatch):
    seen = {}

    async def fake_discover_tournaments(pw, base_url, allowed=None):
        seen["pw"] = pw
        seen["base_url"] = base_url
        seen["allowed"] = allowed
        return [ScrapedTournament(name="League", external_id="123", url="u1")]

    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )
    monkeypatch.setattr("scraper.league_scraper.discover_tournaments", fake_discover_tournaments)

    scraper = LeagueScraper("https://example.test", allowed_tournaments={"League"})
    tournaments = asyncio.run(scraper.scrape_tournaments())

    assert len(tournaments) == 1
    assert tournaments[0].name == "League"
    assert seen["base_url"] == "https://example.test"
    assert seen["allowed"] == {"League"}


def test_scrape_teams_aggregates_results_and_skips_failed_tournament(monkeypatch):
    async def fake_scrape_tournament_teams(_pw, tournament):
        if tournament.name == "Broken":
            raise RuntimeError("boom")
        return [
            ScrapedTeam(
                name=f"{tournament.name} FC",
                tournament=tournament.name,
                external_id=f"{tournament.external_id}-club",
                club_url="https://olesports.ru/club/1",
            )
        ]

    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )
    monkeypatch.setattr("scraper.league_scraper.scrape_tournament_teams", fake_scrape_tournament_teams)

    scraper = LeagueScraper("https://example.test")
    tournaments = [
        ScrapedTournament(name="League", external_id="1", url="u1"),
        ScrapedTournament(name="Broken", external_id="2", url="u2"),
    ]

    teams = asyncio.run(scraper.scrape_teams(tournaments))

    assert len(teams) == 1
    assert teams[0].name == "League FC"


def test_scrape_players_for_team_calls_current_and_previous_buckets(monkeypatch):
    calls = []

    async def fake_scrape_team_players(
        _pw,
        club_url,
        team_name,
        tournament,
        season_bucket="current",
        target_tournament=None,
    ):
        calls.append((club_url, team_name, tournament, season_bucket, target_tournament))
        return [
            ScrapedPlayer(
                first_name="Ivan",
                last_name=season_bucket,
                external_id=season_bucket,
                team=team_name,
                tournament=tournament,
            )
        ]

    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )
    monkeypatch.setattr("scraper.league_scraper.scrape_team_players", fake_scrape_team_players)

    scraper = LeagueScraper(
        "https://example.test",
        player_tournament="{division} (Лига 8x8, 2025/2026)",
    )
    team = ScrapedTeam(
        name="League FC",
        tournament="РЖД — Высший",
        external_id="club-1",
        club_url="https://olesports.ru/club/1",
    )

    current_players, previous_players = asyncio.run(scraper.scrape_players_for_team(team))

    assert len(current_players) == 1
    assert len(previous_players) == 1
    assert calls == [
        (
            "https://olesports.ru/club/1",
            "League FC",
            "РЖД — Высший",
            "current",
            "Высший (Лига 8x8, 2025/2026)",
        ),
        ("https://olesports.ru/club/1", "League FC", "РЖД — Высший", "previous", None),
    ]


def test_resolve_player_tournament_uses_team_division_name():
    resolved = _resolve_player_tournament(
        "РЖД — Первый",
        "Высший (Лига 8x8, 2025/2026)",
    )

    assert resolved == "Первый (Лига 8x8, 2025/2026)"


def test_resolve_player_tournament_supports_explicit_placeholder():
    resolved = _resolve_player_tournament(
        "РЖД — Высший",
        "{division} (Лига 8x8, 2025/2026)",
    )

    assert resolved == "Высший (Лига 8x8, 2025/2026)"


def test_resolve_player_tournament_does_not_split_plain_hyphenated_division_name():
    resolved = _resolve_player_tournament(
        "Премьер-Лига",
        "Высший (Лига 8x8, 2025/2026)",
    )

    assert resolved == "Высший (Лига 8x8, 2025/2026)"


def test_scrape_players_for_team_returns_empty_for_team_without_url(monkeypatch):
    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )

    scraper = LeagueScraper("https://example.test")
    team = ScrapedTeam(
        name="League FC",
        tournament="League",
        external_id="club-1",
        club_url=None,
    )

    current_players, previous_players = asyncio.run(scraper.scrape_players_for_team(team))

    assert current_players == []
    assert previous_players == []


def test_scrape_players_for_team_current_failure_does_not_block_previous(monkeypatch):
    async def fake_scrape_team_players(
        _pw,
        _club_url,
        _team_name,
        _tournament,
        season_bucket="current",
        target_tournament=None,
    ):
        if season_bucket == "current":
            raise RuntimeError("current failed")
        return [
            ScrapedPlayer(
                first_name="Petr",
                last_name="previous",
                external_id="prev",
                team="League FC",
                tournament="League",
            )
        ]

    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )
    monkeypatch.setattr("scraper.league_scraper.scrape_team_players", fake_scrape_team_players)

    scraper = LeagueScraper("https://example.test")
    team = ScrapedTeam(
        name="League FC",
        tournament="League",
        external_id="club-1",
        club_url="https://olesports.ru/club/1",
    )

    current_players, previous_players = asyncio.run(scraper.scrape_players_for_team(team))

    assert current_players == []
    assert len(previous_players) == 1
    assert previous_players[0].external_id == "prev"


def test_scrape_players_for_team_previous_failure_does_not_block_current(monkeypatch):
    async def fake_scrape_team_players(
        _pw,
        _club_url,
        _team_name,
        _tournament,
        season_bucket="current",
        target_tournament=None,
    ):
        if season_bucket == "previous":
            raise RuntimeError("previous failed")
        return [
            ScrapedPlayer(
                first_name="Ivan",
                last_name="current",
                external_id="cur",
                team="League FC",
                tournament="League",
            )
        ]

    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )
    monkeypatch.setattr("scraper.league_scraper.scrape_team_players", fake_scrape_team_players)

    scraper = LeagueScraper("https://example.test")
    team = ScrapedTeam(
        name="League FC",
        tournament="League",
        external_id="club-1",
        club_url="https://olesports.ru/club/1",
    )

    current_players, previous_players = asyncio.run(scraper.scrape_players_for_team(team))

    assert len(current_players) == 1
    assert current_players[0].external_id == "cur"
    assert previous_players == []


def test_scrape_players_for_teams_aggregates_all_teams(monkeypatch):
    async def fake_scrape_players_for_team_with_pw(_self, _pw, team):
        return (
            [
                ScrapedPlayer(
                    first_name=team.name,
                    last_name="current",
                    external_id=f"{team.external_id}-c",
                    team=team.name,
                    tournament=team.tournament,
                )
            ],
            [
                ScrapedPlayer(
                    first_name=team.name,
                    last_name="previous",
                    external_id=f"{team.external_id}-p",
                    team=team.name,
                    tournament=team.tournament,
                )
            ],
        )

    monkeypatch.setattr(
        "scraper.league_scraper.async_playwright",
        lambda: FakeAsyncPlaywrightContext(DummyPlaywright()),
    )
    monkeypatch.setattr(
        LeagueScraper,
        "_scrape_players_for_team_with_pw",
        fake_scrape_players_for_team_with_pw,
    )

    scraper = LeagueScraper("https://example.test")
    teams = [
        ScrapedTeam(name="A", tournament="League", external_id="a", club_url="u1"),
        ScrapedTeam(name="B", tournament="League", external_id="b", club_url="u2"),
    ]

    current_players, previous_players = asyncio.run(scraper.scrape_players_for_teams(teams))

    assert [player.first_name for player in current_players] == ["A", "B"]
    assert [player.first_name for player in previous_players] == ["A", "B"]


def test_scrape_all_orchestrates_phase_methods(monkeypatch):
    tournaments = [ScrapedTournament(name="League", external_id="1", url="u1")]
    teams = [ScrapedTeam(name="League FC", tournament="League", external_id="club-1", club_url="u")]
    current_players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="p1",
            team="League FC",
            tournament="League",
        )
    ]
    previous_players = [
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="p2",
            team="League FC",
            tournament="League",
        )
    ]

    async def fake_scrape_tournaments(self):
        return tournaments

    async def fake_scrape_teams(self, incoming_tournaments):
        assert incoming_tournaments == tournaments
        return teams

    async def fake_scrape_players_for_teams(self, incoming_teams):
        assert incoming_teams == teams
        return current_players, previous_players

    monkeypatch.setattr(LeagueScraper, "scrape_tournaments", fake_scrape_tournaments)
    monkeypatch.setattr(LeagueScraper, "scrape_teams", fake_scrape_teams)
    monkeypatch.setattr(LeagueScraper, "scrape_players_for_teams", fake_scrape_players_for_teams)

    scraper = LeagueScraper("https://example.test")
    result_teams, result_current, result_previous = asyncio.run(scraper.scrape_all())

    assert result_teams == teams
    assert result_current == current_players
    assert result_previous == previous_players

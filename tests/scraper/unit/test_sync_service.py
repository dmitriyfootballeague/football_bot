import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from football_bot.models import (
    Club,
    Player,
    PlayerPosition,
    PlayerRole,
    RegistrationStatus,
    Tournament,
)
from scraper.scraped_data import ScrapedPlayer, ScrapedTeam, ScrapedTournament
from scraper.scraped_data import ScrapedMatchPlayerStat
from scraper.sync_service import (
    SyncService,
    _apply_match_stat_aggregates,
    _compute_rankings,
    _compute_total_points,
    _resolve_club_id,
)


def make_player(
    *,
    player_id: int,
    telegram_id: int,
    first_name: str,
    last_name: str,
    position=PlayerPosition.MIDFIELDER,
    registration_status=RegistrationStatus.APPROVED,
):
    return Player(
        id=player_id,
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        position=position,
        description=None,
        birth_date=date(2000, 1, 1),
        photo_file_id="photo",
        role=PlayerRole.PLAYER,
        registration_status=registration_status,
    )


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class FakeSession:
    def __init__(self, execute_results=None, events=None, name="session"):
        self.execute_results = list(execute_results or [])
        self.executed_statements = []
        self.added = []
        self.flush_calls = 0
        self.events = events if events is not None else []
        self.name = name

    async def execute(self, _stmt):
        self.executed_statements.append(_stmt)
        if not self.execute_results:
            return FakeScalarResult(None)
        return FakeScalarResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1
        next_id = 100
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = next_id
                next_id += 1

    async def commit(self):
        self.events.append(f"{self.name}:commit")


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSessionPool:
    def __init__(self, sessions):
        self.sessions = list(sessions)

    def __call__(self):
        if not self.sessions:
            raise AssertionError("No more fake sessions available")
        return FakeSessionContext(self.sessions.pop(0))


class FakeScraper:
    def __init__(self, events):
        self.events = events

    async def scrape_tournaments(self):
        self.events.append("scrape_tournaments")
        return [
            ScrapedTournament(name="League", external_id="t1", url="u1"),
        ]

    async def scrape_teams(self, tournaments):
        self.events.append(("scrape_teams", [t.name for t in tournaments]))
        return [
            ScrapedTeam(name="Club A", tournament="League", external_id="c1", club_url="uA"),
            ScrapedTeam(name="Club B", tournament="League", external_id="c2", club_url="uB"),
        ]

    async def scrape_players_for_team(self, team):
        self.events.append(("scrape_players_for_team", team.name))
        current = [
            ScrapedPlayer(
                first_name=team.name,
                last_name="Cur",
                external_id=f"{team.external_id}-cur",
                team=team.name,
                tournament=team.tournament,
                games_played=1,
                goals=1,
            )
        ]
        previous = [
            ScrapedPlayer(
                first_name=team.name,
                last_name="Prev",
                external_id=f"{team.external_id}-prev",
                team=team.name,
                tournament=team.tournament,
                games_played=1,
                goals=1,
            )
        ]
        return current, previous

    async def scrape_match_stats_for_tournament(self, tournament):
        self.events.append(("scrape_match_stats_for_tournament", tournament.name))
        return [
            ScrapedMatchPlayerStat(
                match_external_id="m1",
                match_url="https://olesports.ru/match/m1",
                tournament=tournament.name,
                player_external_id="cA-cur",
                player_name="Club A Cur",
                team_name="Club A",
                opponent_name="Club B",
                is_home=True,
                in_roster=True,
                started=True,
                mvp=False,
                team_goals=2,
                opponent_goals=0,
                goals_conceded=0,
                team_won=True,
            )
        ]


def test_compute_total_points_ignores_scraped_rating_without_fixed_position():
    player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="p1",
        team="FC Test",
        tournament="Optic",
        games_played=10,
        mvp_count=1,
        goals=2,
        assists=3,
        rating=91.5,
    )

    assert _compute_total_points(player) == 11


def test_compute_total_points_uses_position_specific_scout_formula():
    player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="p1",
        team="FC Test",
        tournament="Optic",
        games_played=10,
        mvp_count=2,
        goals=3,
        assists=4,
        position=PlayerPosition.DEFENSIVE_MIDFIELDER.value,
        wins=5,
        starts=6,
        goals_conceded=12,
    )

    assert _compute_total_points(player) == 69


def test_compute_total_points_clamps_defensive_points_at_zero():
    player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="p1",
        team="FC Test",
        tournament="Optic",
        games_played=1,
        position=PlayerPosition.DEFENDER.value,
        goals_conceded=10,
    )

    assert _compute_total_points(player) == 0


@pytest.mark.parametrize(
    ("position", "goals", "assists", "mvp_count", "wins", "starts", "goals_conceded"),
    [
        (PlayerPosition.FORWARD.value, 3, 2, 1, 2, 3, None),
        (PlayerPosition.DEFENDER.value, 1, 1, 0, 1, 1, 0),
        (PlayerPosition.GOALKEEPER.value, 0, 2, 1, 2, 2, 0),
        (None, 2, 3, 1, None, None, None),
    ],
)
def test_compute_total_points_returns_zero_when_player_has_no_games(
    position,
    goals,
    assists,
    mvp_count,
    wins,
    starts,
    goals_conceded,
):
    player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="p1",
        team="FC Test",
        tournament="Optic",
        games_played=0,
        position=position,
        goals=goals,
        assists=assists,
        mvp_count=mvp_count,
        wins=wins,
        starts=starts,
        goals_conceded=goals_conceded,
        defensive_points=10,
    )

    assert _compute_total_points(player) == 0


def test_apply_match_stat_aggregates_adds_wins_starts_and_defensive_points():
    player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="p1",
        team="FC Test",
        tournament="Optic",
        games_played=2,
        position=PlayerPosition.DEFENDER.value,
    )
    match_stats = [
        ScrapedMatchPlayerStat(
            match_external_id="m1",
            match_url="https://olesports.ru/match/m1",
            tournament="Optic",
            player_external_id="p1",
            player_name="Ivan Petrov",
            team_name="FC Test",
            opponent_name="FC Other",
            is_home=True,
            in_roster=True,
            started=True,
            mvp=False,
            team_goals=2,
            opponent_goals=1,
            goals_conceded=1,
            team_won=True,
        ),
        ScrapedMatchPlayerStat(
            match_external_id="m2",
            match_url="https://olesports.ru/match/m2",
            tournament="Optic",
            player_external_id="p1",
            player_name="Ivan Petrov",
            team_name="FC Test",
            opponent_name="FC Other",
            is_home=False,
            in_roster=True,
            started=False,
            mvp=False,
            team_goals=0,
            opponent_goals=5,
            goals_conceded=5,
            team_won=False,
        ),
    ]

    _apply_match_stat_aggregates([player], match_stats)

    assert player.wins == 1
    assert player.starts == 1
    assert player.goals_conceded == 6
    assert player.defensive_points == 6
    assert _compute_total_points(player) == 8


def test_resolve_club_id_matches_team_name_case_insensitively():
    club_map = {("League", "СБР-А сталь"): 10}

    club_id = _resolve_club_id(club_map, "League", "СБР-А СТАЛЬ")

    assert club_id == 10


def test_compute_rankings_groups_by_division_and_computes_ranks():
    players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="p1",
            team="FC Test",
            tournament="РЖД — Премьер-Лига",
            games_played=2,
            goals=2,
            assists=1,
            mvp_count=1,
        ),
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="p2",
            team="FC Test",
            tournament="Оптик — Премьер-Лига",
            games_played=4,
            goals=1,
            assists=0,
            mvp_count=0,
        ),
        ScrapedPlayer(
            first_name="Sergey",
            last_name="Sidorov",
            external_id="p3",
            team="FC Other",
            tournament="Суперлига — Суперлига",
            games_played=1,
            rating=50,
        ),
    ]

    rankings = _compute_rankings(players)

    assert rankings["p1"] == {
        "current_rating": 9,
        "division_rank": 1,
        "division_total": 2,
        "avg_points_per_game": 4.5,
    }
    assert rankings["p2"] == {
        "current_rating": 3,
        "division_rank": 2,
        "division_total": 2,
        "avg_points_per_game": 0.75,
    }
    assert rankings["p3"] == {
        "current_rating": 0,
        "division_rank": 1,
        "division_total": 1,
        "avg_points_per_game": 0.0,
    }


def test_compute_rankings_zero_game_player_gets_zero_rating_and_average():
    players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="p1",
            team="FC Test",
            tournament="Optic",
            games_played=0,
            goals=1,
            assists=0,
            mvp_count=0,
            position=PlayerPosition.DEFENDER.value,
            defensive_points=8,
        ),
    ]

    rankings = _compute_rankings(players)

    assert rankings["p1"] == {
        "current_rating": 0,
        "division_rank": 1,
        "division_total": 1,
        "avg_points_per_game": 0.0,
    }


def test_compute_rankings_falls_back_to_tournament_name_without_division_suffix():
    players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="p1",
            team="FC Test",
            tournament="Премьер-Лига",
            games_played=1,
            goals=1,
        ),
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="p2",
            team="FC Test",
            tournament="Премьер-Лига",
            games_played=1,
            goals=0,
        ),
    ]

    rankings = _compute_rankings(players)

    assert rankings["p1"]["division_rank"] == 1
    assert rankings["p2"]["division_rank"] == 2


def test_upsert_tournaments_batch_creates_new_and_updates_missing_external_id():
    existing = Tournament(id=7, name="Cup", external_id=None)
    session = FakeSession(execute_results=[[existing]])
    tournaments = [
        ScrapedTournament(name="League", external_id="t1", url="u1"),
        ScrapedTournament(name="Cup", external_id="t2", url="u2"),
    ]

    tournament_map = asyncio.run(SyncService._upsert_tournaments_batch(session, tournaments))

    assert existing.external_id == "t2"
    assert len(session.added) == 1
    assert session.added[0].name == "League"
    assert tournament_map["Cup"] == 7
    assert "League" in tournament_map


def test_upsert_clubs_batch_scopes_same_club_name_by_tournament():
    existing = Club(id=10, name="Spartak", tournament_id=1, external_id=None)
    session = FakeSession(execute_results=[[existing]])
    teams = [
        ScrapedTeam(name="Spartak", tournament="League A", external_id="c1", club_url="u1"),
        ScrapedTeam(name="Spartak", tournament="League B", external_id="c2", club_url="u2"),
    ]
    tournament_map = {"League A": 1, "League B": 2}

    club_map = asyncio.run(SyncService._upsert_clubs_batch(session, teams, tournament_map))

    assert existing.external_id == "c1"
    assert len(session.added) == 1
    assert session.added[0].tournament_id == 2
    assert club_map[("League A", "Spartak")] == 10
    assert ("League B", "Spartak") in club_map


def test_save_scraped_players_batch_uses_tournament_and_club_map(monkeypatch):
    calls = []
    session = FakeSession()
    players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="p1",
            team="Club A",
            tournament="League",
        ),
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="p2",
            team="Club B",
            tournament="League",
        ),
    ]

    async def fake_upsert_scraped_player(_session, player, club_id):
        calls.append((player.external_id, club_id))

    monkeypatch.setattr(SyncService, "_upsert_scraped_player", staticmethod(fake_upsert_scraped_player))

    saved = asyncio.run(
        SyncService._save_scraped_players_batch(
            session,
            players,
            {("League", "Club A"): 1, ("League", "Club B"): 2},
        )
    )

    assert saved == 2
    assert calls == [("p1", 1), ("p2", 2)]
    assert session.flush_calls == 1


def test_save_scraped_player_ratings_batch_persists_computed_fields(monkeypatch):
    calls = []
    session = FakeSession()
    players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="p1",
            team="Club A",
            tournament="League",
        ),
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="p2",
            team="Club B",
            tournament="League",
        ),
    ]
    ranking_map = {
        "p1": {"current_rating": 9, "division_rank": 1, "division_total": 2, "avg_points_per_game": 4.5},
        "p2": {"current_rating": 3, "division_rank": 2, "division_total": 2, "avg_points_per_game": 1.5},
    }

    async def fake_upsert_scraped_player(_session, player, club_id, computed=None):
        calls.append((player.external_id, club_id, computed))

    monkeypatch.setattr(SyncService, "_upsert_scraped_player", staticmethod(fake_upsert_scraped_player))

    saved = asyncio.run(
        SyncService._save_scraped_player_ratings_batch(
            session,
            players,
            {("League", "Club A"): 1, ("League", "Club B"): 2},
            ranking_map,
        )
    )

    assert saved == 2
    assert calls == [
        ("p1", 1, ranking_map["p1"]),
        ("p2", 2, ranking_map["p2"]),
    ]
    assert session.flush_calls == 1


def test_apply_fixed_positions_uses_client_external_id_map():
    players = [
        ScrapedPlayer(
            first_name="Dmitry",
            last_name="Mironov",
            external_id="62ffbb0eaa8c2e49e5f803ba",
            team="Арктик",
            tournament="League",
        ),
        ScrapedPlayer(
            first_name="Unknown",
            last_name="Player",
            external_id="missing",
            team="Арктик",
            tournament="League",
        ),
    ]

    SyncService._apply_fixed_positions(players)

    assert players[0].position == PlayerPosition.ATTACKING_MIDFIELDER.value
    assert players[1].position is None


def test_upsert_scraped_player_uses_postgres_on_conflict_update():
    session = FakeSession()
    scraped_player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="player-1",
        team="Club A",
        tournament="League",
        games_played=5,
        mvp_count=1,
        goals=2,
        assists=3,
        yellow_cards=1,
        red_cards=0,
    )

    asyncio.run(SyncService._upsert_scraped_player(session, scraped_player, club_id=10))

    assert session.added == []
    assert len(session.executed_statements) == 1
    sql = str(
        session.executed_statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql
    assert "scraped_player_stats" in sql
    assert "position" in sql
    assert "current_rating" not in sql


def test_upsert_scraped_player_persists_computed_rating_fields():
    session = FakeSession()
    scraped_player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="player-1",
        team="Club A",
        tournament="League",
        games_played=5,
        mvp_count=1,
        goals=2,
        assists=3,
        yellow_cards=1,
        red_cards=0,
    )

    asyncio.run(
        SyncService._upsert_scraped_player(
            session,
            scraped_player,
            club_id=10,
            computed={
                "current_rating": 18.5,
                "division_rank": 4,
                "division_total": 20,
                "avg_points_per_game": 3.7,
            },
        )
    )

    sql = str(
        session.executed_statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "current_rating" in sql
    assert "division_rank" in sql
    assert "division_total" in sql
    assert "avg_points_per_game" in sql


def test_upsert_match_player_stat_uses_postgres_on_conflict_update():
    session = FakeSession()
    stat = ScrapedMatchPlayerStat(
        match_external_id="match-1",
        match_url="https://olesports.ru/match/match-1",
        tournament="League",
        player_external_id="player-1",
        player_name="Ivan Petrov",
        team_name="Club A",
        opponent_name="Club B",
        is_home=True,
        in_roster=True,
        started=True,
        mvp=True,
        team_goals=2,
        opponent_goals=1,
        goals_conceded=1,
        team_won=True,
        match_date_label="05 апреля 2026",
    )

    asyncio.run(
        SyncService._upsert_match_player_stat(
            session,
            stat,
            tournament_id=7,
            club_id=10,
        )
    )

    assert len(session.executed_statements) == 1
    sql = str(
        session.executed_statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql
    assert "match_stats" in sql
    assert "uq_match_stats_match_player" in sql


def test_find_registered_player_prefers_external_id_match():
    external_match = make_player(
        player_id=1,
        telegram_id=101,
        first_name="Ivan",
        last_name="Petrov",
    )
    session = FakeSession(execute_results=[external_match])
    scraped_player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="player-1",
        team="Club A",
        tournament="League",
    )

    player = asyncio.run(SyncService._find_registered_player(session, scraped_player))

    assert player is external_match
    assert len(session.executed_statements) == 1


def test_find_registered_player_uses_name_and_club_before_name_only():
    club_match = make_player(
        player_id=2,
        telegram_id=102,
        first_name="Ivan",
        last_name="Petrov",
    )
    session = FakeSession(execute_results=[None, [club_match]])
    scraped_player = ScrapedPlayer(
        first_name="Ivan",
        last_name="Petrov",
        external_id="player-2",
        team="Club A",
        tournament="League",
    )

    player = asyncio.run(SyncService._find_registered_player(session, scraped_player))

    assert player is club_match
    assert len(session.executed_statements) == 2


def test_find_registered_player_falls_back_to_unique_name_only_match():
    unique_name_match = make_player(
        player_id=3,
        telegram_id=103,
        first_name="Petr",
        last_name="Ivanov",
    )
    session = FakeSession(execute_results=[None, [], [unique_name_match]])
    scraped_player = ScrapedPlayer(
        first_name="Petr",
        last_name="Ivanov",
        external_id="player-3",
        team="Unknown Club",
        tournament="League",
    )

    player = asyncio.run(SyncService._find_registered_player(session, scraped_player))

    assert player is unique_name_match
    assert len(session.executed_statements) == 3


def test_find_registered_player_returns_none_for_ambiguous_name_only_match():
    first = make_player(
        player_id=4,
        telegram_id=104,
        first_name="Sergey",
        last_name="Sidorov",
    )
    second = make_player(
        player_id=5,
        telegram_id=105,
        first_name="Sergey",
        last_name="Sidorov",
    )
    session = FakeSession(execute_results=[None, [], [first, second]])
    scraped_player = ScrapedPlayer(
        first_name="Sergey",
        last_name="Sidorov",
        external_id="player-4",
        team="Unknown Club",
        tournament="League",
    )

    player = asyncio.run(SyncService._find_registered_player(session, scraped_player))

    assert player is None
    assert len(session.executed_statements) == 3


def test_sync_registered_players_batch_updates_fields_and_position_ranks(monkeypatch):
    now = datetime.now(timezone.utc)
    player_a = make_player(player_id=1, telegram_id=101, first_name="Ivan", last_name="Petrov")
    player_b = make_player(player_id=2, telegram_id=102, first_name="Petr", last_name="Ivanov")
    players_by_external_id = {
        "cur-a": player_a,
        "cur-b": player_b,
        "prev-a": player_a,
        "prev-b": player_b,
    }

    async def fake_find_registered_player(_session, scraped_player):
        return players_by_external_id.get(scraped_player.external_id)

    monkeypatch.setattr(SyncService, "_find_registered_player", staticmethod(fake_find_registered_player))

    current_players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="cur-a",
            team="Club A",
            tournament="League",
            games_played=2,
            goals=2,
            assists=1,
            mvp_count=1,
            position=PlayerPosition.ATTACKING_MIDFIELDER.value,
        ),
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="cur-b",
            team="Club B",
            tournament="League",
            games_played=3,
            goals=1,
            assists=0,
            mvp_count=0,
            position=PlayerPosition.DEFENDER.value,
        ),
    ]
    prev_players = [
        ScrapedPlayer(
            first_name="Ivan",
            last_name="Petrov",
            external_id="prev-a",
            team="Club A",
            tournament="League",
        ),
        ScrapedPlayer(
            first_name="Petr",
            last_name="Ivanov",
            external_id="prev-b",
            team="Club B",
            tournament="League",
        ),
    ]
    ranking_map = {
        "cur-a": {"current_rating": 9, "division_rank": 1, "division_total": 2, "avg_points_per_game": 4.5},
        "cur-b": {"current_rating": 3, "division_rank": 2, "division_total": 2, "avg_points_per_game": 1.0},
    }
    prev_ranking_map = {
        "prev-a": {"current_rating": 11, "division_rank": 1, "division_total": 2, "avg_points_per_game": 5.5},
        "prev-b": {"current_rating": 4, "division_rank": 2, "division_total": 2, "avg_points_per_game": 2.0},
    }
    session = FakeSession()

    matched, prev_matched = asyncio.run(
        SyncService._sync_registered_players_batch(
            session=session,
            current_players=current_players,
            prev_players=prev_players,
            ranking_map=ranking_map,
            prev_ranking_map=prev_ranking_map,
            now=now,
        )
    )

    assert matched == 2
    assert prev_matched == 2
    assert player_a.external_id == "cur-a"
    assert player_a.current_rating == 9
    assert player_b.current_rating == 3
    assert player_a.position == PlayerPosition.ATTACKING_MIDFIELDER
    assert player_b.position == PlayerPosition.DEFENDER
    assert player_a.position_rank == 1
    assert player_b.position_rank == 1
    assert player_a.prev_season_rating == 11
    assert player_b.prev_season_rating == 4
    assert player_a.prev_position_rank == 1
    assert player_b.prev_position_rank == 1
    assert session.flush_calls == 1


def test_run_sync_processes_phases_and_commits_per_club(monkeypatch):
    events = []
    first_session = FakeSession(events=events, name="session1")
    second_session = FakeSession(events=events, name="session2")
    pool = FakeSessionPool([first_session, second_session])

    async def fake_upsert_tournaments_batch(_session, tournaments):
        events.append(("upsert_tournaments_batch", [t.name for t in tournaments]))
        return {"League": 1}

    async def fake_upsert_clubs_batch(_session, teams, tournament_map):
        events.append(("upsert_clubs_batch", [team.name for team in teams], tournament_map))
        return {("League", "Club A"): 10, ("League", "Club B"): 20}

    async def fake_save_scraped_players_batch(session, players, club_map):
        events.append(("save_scraped_players_batch", [player.team for player in players], club_map))
        return len(players)

    async def fake_save_match_stats_batch(session, match_stats, tournament_id, club_map):
        events.append((
            "save_match_stats_batch",
            [stat.match_external_id for stat in match_stats],
            tournament_id,
            club_map,
        ))
        return len(match_stats)

    async def fake_sync_registered_players_batch(
        session, current_players, prev_players, ranking_map, prev_ranking_map, now
    ):
        events.append((
            "sync_registered_players_batch",
            [player.team for player in current_players],
            [player.team for player in prev_players],
        ))
        return len(current_players), len(prev_players)

    async def fake_save_scraped_player_ratings_batch(session, players, club_map, ranking_map):
        events.append((
            "save_scraped_player_ratings_batch",
            [player.team for player in players],
            club_map,
        ))
        return len(players)

    monkeypatch.setattr(SyncService, "_upsert_tournaments_batch", staticmethod(fake_upsert_tournaments_batch))
    monkeypatch.setattr(SyncService, "_upsert_clubs_batch", staticmethod(fake_upsert_clubs_batch))
    monkeypatch.setattr(SyncService, "_save_scraped_players_batch", classmethod(lambda cls, *args, **kwargs: fake_save_scraped_players_batch(*args, **kwargs)))
    monkeypatch.setattr(SyncService, "_save_match_stats_batch", classmethod(lambda cls, *args, **kwargs: fake_save_match_stats_batch(*args, **kwargs)))
    monkeypatch.setattr(SyncService, "_save_scraped_player_ratings_batch", classmethod(lambda cls, *args, **kwargs: fake_save_scraped_player_ratings_batch(*args, **kwargs)))
    monkeypatch.setattr(SyncService, "_sync_registered_players_batch", classmethod(lambda cls, *args, **kwargs: fake_sync_registered_players_batch(*args, **kwargs)))

    service = SyncService(pool, "https://example.test")
    service.scraper = FakeScraper(events)

    asyncio.run(service.run_sync())

    assert events == [
        "scrape_tournaments",
        ("upsert_tournaments_batch", ["League"]),
        "session1:commit",
        ("scrape_teams", ["League"]),
        ("upsert_clubs_batch", ["Club A", "Club B"], {"League": 1}),
        "session2:commit",
        ("scrape_players_for_team", "Club A"),
        ("save_scraped_players_batch", ["Club A"], {("League", "Club A"): 10, ("League", "Club B"): 20}),
        "session2:commit",
        ("scrape_players_for_team", "Club B"),
        ("save_scraped_players_batch", ["Club B"], {("League", "Club A"): 10, ("League", "Club B"): 20}),
        "session2:commit",
        ("scrape_match_stats_for_tournament", "League"),
        ("save_match_stats_batch", ["m1"], 1, {("League", "Club A"): 10, ("League", "Club B"): 20}),
        "session2:commit",
        ("save_scraped_player_ratings_batch", ["Club A", "Club B"], {("League", "Club A"): 10, ("League", "Club B"): 20}),
        "session2:commit",
        ("sync_registered_players_batch", ["Club A", "Club B"], ["Club A", "Club B"]),
        "session2:commit",
    ]

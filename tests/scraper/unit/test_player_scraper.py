import asyncio

from scraper.player_scraper import (
    _extract_stats,
    _normalize_tournament_label,
    _parse_player_row,
    _select_division,
)


class FakeElement:
    def __init__(
        self,
        *,
        text="",
        href=None,
        classes="",
        children=None,
        attr_map=None,
    ):
        self._text = text
        self._href = href
        self._classes = classes
        self._children = children or {}
        self._attr_map = attr_map or {}
        self.clicked = False

    async def query_selector(self, selector):
        return self._children.get(selector)

    async def query_selector_all(self, selector):
        value = self._children.get(selector, [])
        if isinstance(value, list):
            return value
        return [value]

    async def inner_text(self):
        return self._text

    async def get_attribute(self, name):
        if name == "href":
            return self._href
        if name == "class":
            return self._classes
        return self._attr_map.get(name)

    async def evaluate(self, _script):
        return self._text

    async def click(self):
        self.clicked = True


class FakePage:
    def __init__(self, selectors=None):
        self.selectors = selectors or {}
        self.waits = []

    async def query_selector(self, selector):
        return self.selectors.get(selector)

    async def query_selector_all(self, selector):
        return self.selectors.get(selector, [])

    async def wait_for_timeout(self, timeout):
        self.waits.append(timeout)


def test_extract_stats_from_values_div():
    row = FakeElement(
        children={
            "div.values": FakeElement(text="10 2 3 4 7 1 0 91.5"),
        }
    )

    values = asyncio.run(_extract_stats(row))

    assert values == [10, 2, 3, 4, 7, 1, 0, 91]


def test_extract_stats_from_table_cells():
    cells = [
        FakeElement(text="rank"),
        FakeElement(text="name"),
        FakeElement(text="8"),
        FakeElement(text="1"),
        FakeElement(text="2"),
        FakeElement(text="3"),
        FakeElement(text="5"),
        FakeElement(text="0"),
        FakeElement(text="1"),
    ]
    row = FakeElement(children={"td": cells})

    values = asyncio.run(_extract_stats(row))

    assert values == [8, 1, 2, 3, 5, 0, 1]


def test_extract_stats_falls_back_to_row_evaluate():
    row = FakeElement(text="12 0 1 2 3 4 5")

    values = asyncio.run(_extract_stats(row))

    assert values == [12, 0, 1, 2, 3, 4, 5]


def test_parse_player_row_returns_scraped_player():
    name_el = FakeElement(text="Ivan Petrov")
    player_link = FakeElement(
        href="/player/ext-123",
        children={"div.name": name_el},
    )
    row = FakeElement(
        children={
            "a.player": player_link,
            "div.values": FakeElement(text="10 2 3 4 7 1 0 88"),
        }
    )

    player = asyncio.run(
        _parse_player_row(
            row,
            "FC Test",
            "Optic",
            season_bucket="current",
            season_label="Высший (Лига 8x8, 2025/2026)",
        )
    )

    assert player is not None
    assert player.first_name == "Ivan"
    assert player.last_name == "Petrov"
    assert player.external_id == "ext-123"
    assert player.team == "FC Test"
    assert player.tournament == "Optic"
    assert player.season_bucket == "current"
    assert player.season_label == "Высший (Лига 8x8, 2025/2026)"
    assert player.season_key == "2025/2026"
    assert player.games_played == 10
    assert player.mvp_count == 2
    assert player.goals == 3
    assert player.assists == 4
    assert player.yellow_cards == 1
    assert player.red_cards == 0
    assert player.rating == 88.0


def test_parse_player_row_returns_none_without_player_link():
    row = FakeElement(children={"div.values": FakeElement(text="1 2 3")})

    player = asyncio.run(_parse_player_row(row, "FC Test", "Optic"))

    assert player is None


def test_parse_player_row_returns_none_without_external_id():
    row = FakeElement(children={"a.player": FakeElement(href="/club/123")})

    player = asyncio.run(_parse_player_row(row, "FC Test", "Optic"))

    assert player is None


def test_select_division_prefers_matching_group():
    dropdown = FakeElement()
    current_group = FakeElement(text="Текущие", classes="p-dropdown-item-group")
    current_item = FakeElement(text="Season 2025", classes="p-dropdown-item")
    previous_group = FakeElement(text="Прошедшие", classes="p-dropdown-item-group")
    previous_item = FakeElement(text="Season 2024", classes="p-dropdown-item")
    page = FakePage(
        selectors={
            "div.p-dropdown": dropdown,
            "ul.p-dropdown-items li": [
                current_group,
                current_item,
                previous_group,
                previous_item,
            ],
        }
    )

    selected = asyncio.run(_select_division(page, "previous"))

    assert selected == "Season 2024"
    assert previous_item.clicked is True
    assert current_item.clicked is False


def test_select_division_uses_fallback_index_when_no_groups():
    dropdown = FakeElement()
    first_item = FakeElement(text="Season 2025", classes="p-dropdown-item")
    second_item = FakeElement(text="Season 2024", classes="p-dropdown-item")
    page = FakePage(
        selectors={
            "div.p-dropdown": dropdown,
            "ul.p-dropdown-items li": [first_item, second_item],
        }
    )

    selected = asyncio.run(_select_division(page, "previous"))

    assert selected == "Season 2024"
    assert second_item.clicked is True
    assert first_item.clicked is False


def test_select_division_returns_when_dropdown_missing():
    page = FakePage(selectors={})

    selected = asyncio.run(_select_division(page, "current"))

    assert selected is None
    assert page.waits == []


def test_normalize_tournament_label_matches_html_variant():
    configured = "Высший (Лига 8x8, 2025/2026)"
    html_value = "Высший (Лига 8х8, 2025/26)"

    assert _normalize_tournament_label(configured) == _normalize_tournament_label(html_value)


def test_select_division_prefers_exact_configured_tournament():
    dropdown = FakeElement()
    unrelated = FakeElement(text="Первая (Лига 8х8, 2025/26)", classes="p-dropdown-item")
    target = FakeElement(text="Высший (Лига 8х8, 2025/26)", classes="p-dropdown-item p-highlight")
    page = FakePage(
        selectors={
            "div.p-dropdown": dropdown,
            "ul.p-dropdown-items li": [unrelated, target],
        }
    )

    selected = asyncio.run(
        _select_division(
            page,
            "current",
            target_tournament="Высший (Лига 8x8, 2025/2026)",
        )
    )

    assert selected == "Высший (Лига 8х8, 2025/26)"
    assert target.clicked is True
    assert unrelated.clicked is False


def test_select_division_returns_false_when_exact_configured_tournament_missing():
    dropdown = FakeElement()
    first_item = FakeElement(text="Первая (Лига 8х8, 2025/26)", classes="p-dropdown-item")
    second_item = FakeElement(text="Вторая (Лига 8х8, 2025/26)", classes="p-dropdown-item")
    page = FakePage(
        selectors={
            "div.p-dropdown": dropdown,
            "ul.p-dropdown-items li": [first_item, second_item],
        }
    )

    selected = asyncio.run(
        _select_division(
            page,
            "current",
            target_tournament="Высший (Лига 8x8, 2025/2026)",
        )
    )

    assert selected is None
    assert first_item.clicked is False
    assert second_item.clicked is False

import asyncio

from scraper.discovery import (
    _click_division,
    _click_tournament_button,
    discover_tournaments,
)


class FakeTooltip:
    def __init__(self, text):
        self._text = text

    async def inner_text(self):
        return self._text


class FakeTab:
    def __init__(self, page, index):
        self.page = page
        self.index = index

    async def hover(self):
        self.page.hovered_index = self.index

    async def inner_text(self):
        return self.page.tournament_names[self.index]


class FakeMouse:
    def __init__(self):
        self.moves = []

    async def move(self, x, y):
        self.moves.append((x, y))


class FakePage:
    def __init__(self, tournament_names, selector_to_match, tooltips_by_index, title="Test Page"):
        self.tournament_names = tournament_names
        self.selector_to_match = selector_to_match
        self.tooltips_by_index = tooltips_by_index
        self.hovered_index = None
        self.mouse = FakeMouse()
        self._title = title

    async def goto(self, *args, **kwargs):
        return None

    async def wait_for_timeout(self, _timeout):
        return None

    async def title(self):
        return self._title

    async def query_selector_all(self, selector):
        if selector == self.selector_to_match:
            return [FakeTab(self, idx) for idx, _ in enumerate(self.tournament_names)]
        return []

    async def eval_on_selector_all(self, selector, _script):
        if selector == self.selector_to_match:
            return self.tournament_names
        return []

    async def query_selector(self, selector):
        if selector in {
            "div.p-tooltip.p-tooltip-active",
            "div.p-tooltip",
            ".tournament-tooltip",
        }:
            return self.tooltips_by_index.get(self.hovered_index)
        return None


class FakeClickTab:
    def __init__(self, page, text, target_url):
        self.page = page
        self._text = text
        self.target_url = target_url
        self.hovered = False

    async def inner_text(self):
        return self._text

    async def click(self):
        self.page.url = self.target_url

    async def hover(self):
        self.hovered = True


class FakeDivisionClicker:
    def __init__(self, page, target_url):
        self.page = page
        self.target_url = target_url

    def get_by_text(self, _text, exact=True):
        return self

    @property
    def first(self):
        return self

    async def click(self):
        self.page.url = self.target_url


class FakeClickPage:
    def __init__(self, tabs, target_division_url="https://olesports.ru/tournament/division"):
        self.tabs = tabs
        self.url = "https://olesports.ru/start"
        self.target_division_url = target_division_url

    async def goto(self, *args, **kwargs):
        return None

    async def wait_for_selector(self, *args, **kwargs):
        return None

    async def wait_for_timeout(self, *args, **kwargs):
        return None

    async def query_selector_all(self, _selector):
        return self.tabs

    def locator(self, _selector):
        return FakeDivisionClicker(self, self.target_division_url)


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, page):
        self.page = page

    async def launch(self, **_kwargs):
        return FakeBrowser(self.page)


class FakePlaywright:
    def __init__(self, page):
        self.chromium = FakeChromium(page)


def test_discover_tournaments_builds_division_and_plain_tournament_urls(monkeypatch):
    page = FakePage(
        tournament_names=["League", "Cup"],
        selector_to_match="div.navi-group span.app-link",
        tooltips_by_index={
            0: FakeTooltip("Div A\nDiv B"),
            1: None,
        },
    )
    pw = FakePlaywright(page)

    async def fake_click_division(_pw, _base_url, tourn_name, div_name, _selector):
        return f"https://olesports.ru/tournament/{tourn_name}-{div_name}".replace(" ", "_")

    async def fake_click_tournament(_pw, _base_url, tourn_name, _selector):
        return f"https://olesports.ru/tournament/{tourn_name}".replace(" ", "_")

    monkeypatch.setattr("scraper.discovery._click_division", fake_click_division)
    monkeypatch.setattr("scraper.discovery._click_tournament_button", fake_click_tournament)

    tournaments = asyncio.run(discover_tournaments(pw, "https://example.test"))

    assert [t.name for t in tournaments] == [
        "League — Div A",
        "League — Div B",
        "Cup",
    ]
    assert [t.external_id for t in tournaments] == [
        "League-Div_A",
        "League-Div_B",
        "Cup",
    ]


def test_discover_tournaments_respects_allowed_filter(monkeypatch):
    page = FakePage(
        tournament_names=["League", "Cup"],
        selector_to_match="div.navi-group span.app-link",
        tooltips_by_index={
            0: FakeTooltip("Div A"),
            1: None,
        },
    )
    pw = FakePlaywright(page)

    async def fake_click_division(_pw, _base_url, tourn_name, div_name, _selector):
        return f"https://olesports.ru/tournament/{tourn_name}-{div_name}"

    async def fake_click_tournament(_pw, _base_url, tourn_name, _selector):
        return f"https://olesports.ru/tournament/{tourn_name}"

    monkeypatch.setattr("scraper.discovery._click_division", fake_click_division)
    monkeypatch.setattr("scraper.discovery._click_tournament_button", fake_click_tournament)

    tournaments = asyncio.run(
        discover_tournaments(pw, "https://example.test", allowed={"Cup"})
    )

    assert [t.name for t in tournaments] == ["Cup"]


def test_discover_tournaments_returns_empty_when_no_nav_selector_found():
    page = FakePage(
        tournament_names=["League"],
        selector_to_match="missing-selector",
        tooltips_by_index={},
    )
    pw = FakePlaywright(page)

    tournaments = asyncio.run(discover_tournaments(pw, "https://example.test"))

    assert tournaments == []


def test_click_tournament_button_returns_clicked_page_url():
    page = FakeClickPage([
        FakeClickTab(None, "League", "https://olesports.ru/tournament/league"),
        FakeClickTab(None, "Cup", "https://olesports.ru/tournament/cup"),
    ])
    for tab in page.tabs:
        tab.page = page
    pw = FakePlaywright(page)

    url = asyncio.run(
        _click_tournament_button(
            pw,
            "https://example.test",
            "Cup",
            "div.navi-group span.app-link",
        )
    )

    assert url == "https://olesports.ru/tournament/cup"


def test_click_division_returns_clicked_division_url():
    league_tab = FakeClickTab(None, "League", "https://olesports.ru/tournament/league")
    other_tab = FakeClickTab(None, "Cup", "https://olesports.ru/tournament/cup")
    page = FakeClickPage(
        [league_tab, other_tab],
        target_division_url="https://olesports.ru/tournament/league-division",
    )
    league_tab.page = page
    other_tab.page = page
    pw = FakePlaywright(page)

    url = asyncio.run(
        _click_division(
            pw,
            "https://example.test",
            "League",
            "Division A",
            "div.navi-group span.app-link",
        )
    )

    assert url == "https://olesports.ru/tournament/league-division"
    assert league_tab.hovered is True

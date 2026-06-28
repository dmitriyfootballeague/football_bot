import asyncio

from scraper.team_scraper import _click_stage_tab, _scrape_teams


class FakeLink:
    def __init__(self, text, href):
        self._text = text
        self._href = href

    async def inner_text(self):
        return self._text

    async def get_attribute(self, name):
        if name == "href":
            return self._href
        return None


class FakeTab:
    def __init__(self, text):
        self._text = text
        self.clicked = False

    async def inner_text(self):
        return self._text

    async def click(self):
        self.clicked = True


class FakePage:
    def __init__(self, selectors=None):
        self.selectors = selectors or {}
        self.waited_for = []

    async def query_selector_all(self, selector):
        return self.selectors.get(selector, [])

    async def wait_for_selector(self, selector, timeout):
        self.waited_for.append((selector, timeout))

    async def wait_for_timeout(self, timeout):
        self.waited_for.append(("timeout", timeout))


def test_click_stage_tab_clicks_target_tab():
    target = FakeTab("Круговой турнир")
    other = FakeTab("Плей-офф")
    page = FakePage(
        selectors={"div.stages-nav span.p-tag.p-component": [other, target]}
    )

    asyncio.run(_click_stage_tab(page))

    assert target.clicked is True
    assert other.clicked is False


def test_scrape_teams_returns_unique_clubs_with_absolute_urls():
    links = [
        FakeLink("FC One", "/club/1"),
        FakeLink("FC One Duplicate", "/club/1"),
        FakeLink("FC Two", "https://olesports.ru/club/2"),
        FakeLink("", "/club/3"),
        FakeLink("Not A Club", "/player/10"),
    ]
    page = FakePage(selectors={'a[href*="/club/"]': links})

    teams = asyncio.run(_scrape_teams(page, "Optic", "t-1"))

    assert len(teams) == 2
    assert teams[0].name == "FC One"
    assert teams[0].external_id == "1"
    assert teams[0].club_url == "https://olesports.ru/club/1"
    assert teams[1].name == "FC Two"
    assert teams[1].external_id == "2"
    assert teams[1].club_url == "https://olesports.ru/club/2"

from playwright.async_api import Page

from scraper.logging import logger
from scraper.scraped_data import BROWSER_ARGS, ScrapedTeam, ScrapedTournament

BASE_SITE = "https://olesports.ru"


async def scrape_tournament_teams(pw, tournament: ScrapedTournament) -> list[ScrapedTeam]:
    """Open a tournament's page and extract all team links."""
    teams: list[ScrapedTeam] = []
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)

    try:
        page = await browser.new_page()
        await page.goto(tournament.url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # Click "Круговой турнир" stage tab before scraping teams
        await _click_stage_tab(page)

        teams = await _scrape_teams(page, tournament.name, tournament.external_id)
        logger.info(f"  Tournament '{tournament.name}': found {len(teams)} teams")
    except Exception as e:
        logger.error(f"  Failed to scrape teams for '{tournament.name}': {e}")
    finally:
        await browser.close()

    return teams


async def _click_stage_tab(page: Page) -> None:
    """Click the 'Круговой турнир' stage tab in div.stages-nav."""
    tabs = await page.query_selector_all("div.stages-nav span.p-tag.p-component")
    for tab in tabs:
        text = (await tab.inner_text()).strip()
        if text == "Круговой турнир":
            await tab.click()
            await page.wait_for_timeout(5000)
            logger.info("  Clicked 'Круговой турнир' stage tab")
            return
    logger.warning("  'Круговой турнир' tab not found, using default stage")


async def _scrape_teams(
    page: Page, tournament_name: str, tournament_external_id: str,
) -> list[ScrapedTeam]:
    """Extract teams from the current page by finding club links."""
    teams: list[ScrapedTeam] = []
    seen_ids: set[str] = set()

    try:
        # Wait for club links to appear
        try:
            await page.wait_for_selector('a[href*="/club/"]', timeout=15000)
        except Exception:
            logger.warning(f"  No club links found on {tournament_name} page")

        links = await page.query_selector_all('a[href*="/club/"]')
        for link in links:
            href = await link.get_attribute("href")
            if not href or "/club/" not in href:
                continue

            external_id = href.rstrip("/").split("/club/")[-1]
            if not external_id or external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            name = (await link.inner_text()).strip()
            if not name:
                continue

            club_url = href if href.startswith("http") else f"{BASE_SITE}{href}"

            teams.append(ScrapedTeam(
                name=name,
                tournament=tournament_name,
                tournament_external_id=tournament_external_id,
                external_id=external_id,
                club_url=club_url,
            ))

    except Exception as e:
        logger.error(f"Team scraping error: {e}")

    return teams

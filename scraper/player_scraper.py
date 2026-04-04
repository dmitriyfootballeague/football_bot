import re

from playwright.async_api import Page

from scraper.logging import logger
from scraper.scraped_data import BROWSER_ARGS, ScrapedPlayer

BASE_SITE = "https://olesports.ru"

# Candidate selectors for player rows in the rankings table
ROW_SELECTORS = [
    "div.team-players div.rankings-table div.row:not(.head)",
    "div.rankings-table div.row:not(.head)",
    "table.rankings-table tr:not(.head):not(:first-child)",
    "div.team-players .player-row",
    "div.players-list .row:not(.head)",
]

# Candidate selectors for the division dropdown
DROPDOWN_SELECTORS = [
    "div.p-dropdown",
    "select.division-select",
    ".season-dropdown",
]

CURRENT_GROUP_LABELS = {"текущие", "текущий", "current"}
PREVIOUS_GROUP_LABELS = {"прошедшие", "предыдущие", "архив", "previous"}


async def scrape_team_players(
    pw,
    club_url: str,
    team_name: str,
    tournament: str,
    season_bucket: str = "current",
    target_tournament: str | None = None,
) -> list[ScrapedPlayer]:
    """Launch a fresh browser, visit a club page, parse stats, close browser."""
    players: list[ScrapedPlayer] = []
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)

    try:
        page = await browser.new_page()
        await page.goto(club_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        selected = await _select_division(
            page,
            season_bucket,
            target_tournament=target_tournament,
        )
        if target_tournament and not selected:
            logger.warning(
                f"  {team_name}: target tournament '{target_tournament}' was not found in dropdown"
            )
            return []

        # Try each row selector until one finds rows
        rows = []
        for sel in ROW_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=10000)
                rows = await page.query_selector_all(sel)
                if rows:
                    logger.info(f"  {team_name}: selector '{sel}' found {len(rows)} rows")
                    break
            except Exception:
                continue

        if not rows:
            # Last-resort JS extraction
            players = await _js_extract_players(page, team_name, tournament)
            logger.info(f"  {team_name}: JS fallback extracted {len(players)} players")
            return players

        # Extra pause for all rows to finish rendering
        await page.wait_for_timeout(3000)

        for row in rows:
            player = await _parse_player_row(row, team_name, tournament)
            if player:
                players.append(player)

    except Exception as e:
        logger.error(f"  Failed to scrape {team_name} ({club_url}): {e}")
    finally:
        await browser.close()

    return players


def _normalize_tournament_label(text: str) -> str:
    normalized = text.strip().casefold().replace("х", "x")
    normalized = re.sub(r"\s+", " ", normalized)

    def _expand_short_year(match: re.Match[str]) -> str:
        start_year = int(match.group(1))
        end_suffix = match.group(2)
        full_end_year = int(f"{str(start_year)[:2]}{end_suffix}")
        return f"{start_year}/{full_end_year}"

    normalized = re.sub(r"(\d{4})\s*/\s*(\d{2})(?!\d)", _expand_short_year, normalized)
    return normalized


async def _select_division(
    page: Page,
    season_bucket: str,
    target_tournament: str | None = None,
) -> bool:
    """Select current/previous season or an exact configured tournament in the dropdown."""
    dropdown = None
    for sel in DROPDOWN_SELECTORS:
        dropdown = await page.query_selector(sel)
        if dropdown:
            break

    if not dropdown:
        logger.debug("  Division dropdown not found, using default")
        return False

    await dropdown.click()
    await page.wait_for_timeout(1000)

    items = await page.query_selector_all("ul.p-dropdown-items li")
    if not items:
        items = await page.query_selector_all("option")

    if target_tournament:
        normalized_target = _normalize_tournament_label(target_tournament)
        for item in items:
            text = (await item.inner_text()).strip()
            if not text:
                continue
            if _normalize_tournament_label(text) == normalized_target:
                await item.click()
                await page.wait_for_timeout(5000)
                logger.info(f"  Selected exact tournament: '{text}'")
                return True
        logger.warning(
            f"  Exact tournament '{target_tournament}' not found in dropdown options"
        )
        return False

    target_groups = (
        CURRENT_GROUP_LABELS if season_bucket == "current" else PREVIOUS_GROUP_LABELS
    )
    fallback_values: list[tuple[str, object]] = []
    pick_next = False

    for item in items:
        css = await item.get_attribute("class") or ""
        text = (await item.inner_text()).strip()
        normalized = text.casefold()

        is_group = "p-dropdown-item-group" in css
        is_item = not is_group

        if is_group and normalized in target_groups:
            pick_next = True
            continue

        if is_group:
            pick_next = False
            continue

        if text:
            fallback_values.append((text, item))

        if pick_next and is_item:
            await item.click()
            await page.wait_for_timeout(5000)
            logger.info(f"  Selected {season_bucket} division: '{text}'")
            return True

    if fallback_values:
        fallback_idx = 0 if season_bucket == "current" else min(1, len(fallback_values) - 1)
        text, item = fallback_values[fallback_idx]
        await item.click()
        await page.wait_for_timeout(5000)
        logger.info(f"  Selected fallback {season_bucket} division: '{text}'")
        return True

    logger.warning(f"  No {season_bucket} division found in dropdown")
    return False


async def _parse_player_row(row, team_name: str, tournament: str) -> ScrapedPlayer | None:
    """Parse a single player row from the rankings table."""
    player_link = (
        await row.query_selector("a.player")
        or await row.query_selector("a[href*='/player/']")
        or await row.query_selector("td a")
    )
    if not player_link:
        return None

    href = await player_link.get_attribute("href")
    external_id = ""
    if href and "/player/" in href:
        external_id = href.rstrip("/").split("/player/")[-1]
    if not external_id:
        return None

    name_el = (
        await player_link.query_selector("div.name")
        or await player_link.query_selector("span.name")
        or await player_link.query_selector(".player-name")
        or player_link
    )
    full_name = (await name_el.inner_text()).strip()
    if not full_name:
        return None

    # Amateum uses "Имя Фамилия" order on team pages
    parts = full_name.split(maxsplit=1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    values = await _extract_stats(row)

    # Default column map: И(0) MVP(1) Г(2) П(3) Г+П(4,skip) ЖК(5) КК(6) [Рейт(7)]
    games   = values[0] if len(values) > 0 else 0
    mvp     = values[1] if len(values) > 1 else 0
    goals   = values[2] if len(values) > 2 else 0
    assists = values[3] if len(values) > 3 else 0
    yellow  = values[5] if len(values) > 5 else 0
    red     = values[6] if len(values) > 6 else 0
    # If an 8th column exists it may be a rating value
    rating_raw = values[7] if len(values) > 7 else 0

    return ScrapedPlayer(
        first_name=first_name,
        last_name=last_name,
        external_id=external_id,
        team=team_name,
        tournament=tournament,
        games_played=games,
        mvp_count=mvp,
        goals=goals,
        assists=assists,
        yellow_cards=yellow,
        red_cards=red,
        rating=float(rating_raw),
    )


async def _extract_stats(row) -> list[int]:
    """Extract numeric stat values from a table row."""
    # Try div.values (Amateum standard)
    values_div = await row.query_selector("div.values")
    if values_div:
        text = (await values_div.inner_text()).strip()
    else:
        # Try individual stat cells (skip first 2: rank + name columns)
        cells = await row.query_selector_all("td")
        if len(cells) > 2:
            texts = [(await cell.inner_text()).strip() for cell in cells[2:]]
            text = " ".join(texts)
        else:
            # Last resort: JS collect all value-like elements
            text = await row.evaluate(
                "el => [...el.querySelectorAll('div.value, span.value, td')].map(e => e.innerText.trim()).join(' ')"
            )

    values = []
    for v in text.split():
        try:
            values.append(int(v))
        except (ValueError, TypeError):
            try:
                values.append(int(float(v)))
            except (ValueError, TypeError):
                values.append(0)
    return values


async def _js_extract_players(
    page: Page, team_name: str, tournament: str,
) -> list[ScrapedPlayer]:
    """JS-based extraction as a last resort when CSS selectors fail."""
    try:
        raw: list[dict] = await page.evaluate("""() => {
            const results = [];
            const links = document.querySelectorAll('a[href*="/player/"]');
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const parts = href.split('/player/');
                const ext_id = parts.length > 1 ? parts[1].replace(/\\/+$/, '') : '';
                if (!ext_id) continue;
                const nameEl = link.querySelector('.name, span, div') || link;
                const full_name = nameEl.innerText.trim();
                if (!full_name) continue;
                const row = link.closest('.row, tr');
                let stats = [];
                if (row) {
                    const vals = row.querySelector('.values');
                    const statText = vals ? vals.innerText : row.innerText;
                    stats = statText.replace(full_name, '').trim().split(/\\s+/)
                              .map(v => parseInt(v) || 0);
                }
                results.push({ ext_id, full_name, stats });
            }
            return results;
        }""")

        players = []
        seen: set[str] = set()
        for item in raw:
            ext_id = item.get("ext_id", "")
            if not ext_id or ext_id in seen:
                continue
            seen.add(ext_id)
            full_name = item.get("full_name", "")
            name_parts = full_name.split(maxsplit=1)
            stats = item.get("stats", [])
            players.append(ScrapedPlayer(
                first_name=name_parts[0] if name_parts else "",
                last_name=name_parts[1] if len(name_parts) > 1 else "",
                external_id=ext_id,
                team=team_name,
                tournament=tournament,
                games_played=stats[0] if len(stats) > 0 else 0,
                mvp_count=stats[1] if len(stats) > 1 else 0,
                goals=stats[2] if len(stats) > 2 else 0,
                assists=stats[3] if len(stats) > 3 else 0,
                yellow_cards=stats[5] if len(stats) > 5 else 0,
                red_cards=stats[6] if len(stats) > 6 else 0,
            ))
        return players
    except Exception as e:
        logger.error(f"  JS extraction failed: {e}")
        return []

from __future__ import annotations

import re

from playwright.async_api import Page

from scraper.logging import logger
from scraper.scraped_data import BROWSER_ARGS, ScrapedMatchPlayerStat, ScrapedTournament

BASE_SITE = "https://olesports.ru"


def _external_id_from_href(href: str, marker: str) -> str:
    return href.rstrip("/").split(marker, 1)[-1].split("?", 1)[0]


def _absolute_url(href: str) -> str:
    return href if href.startswith("http") else f"{BASE_SITE}{href}"


def _parse_int(text: str) -> int | None:
    text = text.strip()
    return int(text) if re.fullmatch(r"\d+", text) else None


async def scrape_tournament_match_stats(
    pw,
    tournament: ScrapedTournament,
) -> list[ScrapedMatchPlayerStat]:
    match_urls = await scrape_tournament_match_urls(pw, tournament.url)
    stats: list[ScrapedMatchPlayerStat] = []
    incomplete_matches = 0

    for match_url in match_urls:
        try:
            match_rows = await scrape_match_player_stats(
                pw,
                match_url=match_url,
                tournament_name=tournament.name,
            )
            if not match_rows:
                incomplete_matches += 1
                logger.warning(
                    f"  Match '{match_url}' produced no roster rows; "
                    "skipping only this match"
                )
                continue
            stats.extend(match_rows)
        except Exception as exc:
            incomplete_matches += 1
            logger.error(f"  Failed to scrape match '{match_url}': {exc}")

    if incomplete_matches:
        logger.warning(
            f"  Tournament '{tournament.name}': skipped {incomplete_matches} incomplete "
            f"matches and kept {len(stats)} scraped player rows"
        )

    logger.info(
        f"  Tournament '{tournament.name}': scraped {len(stats)} match player rows "
        f"from {len(match_urls)} match links"
    )
    return stats


async def scrape_tournament_match_urls(pw, tournament_url: str) -> list[str]:
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
    try:
        page = await browser.new_page()
        await page.goto(tournament_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(7000)

        hrefs: list[str] = await page.eval_on_selector_all(
            'a[href*="/match/"]',
            "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
        )
        seen: set[str] = set()
        urls: list[str] = []
        for href in hrefs:
            url = _absolute_url(href)
            match_id = _external_id_from_href(url, "/match/")
            if not match_id or match_id in seen:
                continue
            seen.add(match_id)
            urls.append(url)
        return urls
    finally:
        await browser.close()


async def scrape_match_player_stats(
    pw,
    match_url: str,
    tournament_name: str,
) -> list[ScrapedMatchPlayerStat]:
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
    try:
        page = await browser.new_page()
        await page.goto(match_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(7000)

        match = await _extract_match_header(page)
        if match is None:
            return []

        home_name, away_name, home_goals, away_goals, match_date_label = match
        match_external_id = _external_id_from_href(match_url, "/match/")

        await _click_match_tab(page, "Составы")
        return await _extract_roster_stats(
            page=page,
            match_external_id=match_external_id,
            match_url=match_url,
            tournament_name=tournament_name,
            home_name=home_name,
            away_name=away_name,
            home_goals=home_goals,
            away_goals=away_goals,
            match_date_label=match_date_label,
        )
    finally:
        await browser.close()


async def _click_match_tab(page: Page, label: str) -> None:
    button = page.get_by_role("button", name=label)
    if await button.count() == 0:
        button = page.get_by_text(label, exact=True)
    await button.first.click()
    await page.wait_for_timeout(2500)


async def _extract_match_header(page: Page) -> tuple[str, str, int, int, str | None] | None:
    team_names = await page.eval_on_selector_all(
        ".match-main_team .match-team_name",
        "els => els.map(e => e.innerText.trim()).filter(Boolean)",
    )
    score_texts = await page.eval_on_selector_all(
        ".match-main_score_cell",
        "els => els.map(e => e.innerText.trim()).filter(Boolean)",
    )
    if len(team_names) < 2 or len(score_texts) < 2:
        return None

    home_goals = _parse_int(score_texts[0])
    away_goals = _parse_int(score_texts[1])
    if home_goals is None or away_goals is None:
        return None

    date_label = None
    try:
        date_label = await page.locator(".match-general_info .mean").nth(1).inner_text(
            timeout=1000
        )
    except Exception:
        pass

    return team_names[0], team_names[1], home_goals, away_goals, date_label


async def _extract_roster_stats(
    page: Page,
    match_external_id: str,
    match_url: str,
    tournament_name: str,
    home_name: str,
    away_name: str,
    home_goals: int,
    away_goals: int,
    match_date_label: str | None,
) -> list[ScrapedMatchPlayerStat]:
    rows = await page.eval_on_selector_all(
        ".roster-cell",
        """cells => cells.map(cell => {
            const isHome = cell.classList.contains('__home');
            const starters = new Set(
                [...cell.querySelectorAll('.lineup a[href*="/player/"]')]
                    .map(a => a.getAttribute('href'))
                    .filter(Boolean)
                    .map(h => h.replace(/\\/+$/, '').split('/player/').pop().split('?')[0])
            );
            let rosterItems = [...cell.querySelectorAll('.roster-list a[href*="/player/"]')];
            if (!rosterItems.length) {
                rosterItems = [...cell.querySelectorAll('a[href*="/player/"]')];
            }
            const seen = new Set();
            return rosterItems.map(a => {
                const href = a.getAttribute('href') || '';
                const externalId = href.replace(/\\/+$/, '').split('/player/').pop().split('?')[0];
                if (!externalId || seen.has(externalId)) return null;
                seen.add(externalId);
                const nameEl = a.querySelector('div:last-child') || a;
                return {
                    isHome,
                    externalId,
                    playerName: nameEl.innerText.trim(),
                    started: starters.has(externalId),
                    mvp: /MVP/i.test(a.innerText) || !!a.querySelector('.pi-star'),
                };
            }).filter(Boolean);
        })""",
    )

    stats: list[ScrapedMatchPlayerStat] = []
    for cell_rows in rows:
        for row in cell_rows:
            is_home = bool(row["isHome"])
            team_name = home_name if is_home else away_name
            opponent_name = away_name if is_home else home_name
            team_goals = home_goals if is_home else away_goals
            opponent_goals = away_goals if is_home else home_goals

            stats.append(
                ScrapedMatchPlayerStat(
                    match_external_id=match_external_id,
                    match_url=match_url,
                    tournament=tournament_name,
                    player_external_id=row["externalId"],
                    player_name=row["playerName"],
                    team_name=team_name,
                    opponent_name=opponent_name,
                    is_home=is_home,
                    in_roster=True,
                    started=bool(row["started"]),
                    mvp=bool(row["mvp"]),
                    team_goals=team_goals,
                    opponent_goals=opponent_goals,
                    goals_conceded=opponent_goals,
                    team_won=team_goals > opponent_goals,
                    match_date_label=match_date_label,
                )
            )
    return stats

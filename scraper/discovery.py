from scraper.logging import logger
from scraper.scraped_data import BROWSER_ARGS, ScrapedTournament


async def discover_tournaments(
    pw, base_url: str, allowed: set[str] | None = None
) -> list[ScrapedTournament]:
    """Visit the homepage, collect tournament/division tabs, return their URLs.

    allowed: set of allowed tournament names; None or empty = accept all.
    """
    tournaments: list[ScrapedTournament] = []
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)

    # Multiple candidate selectors for the nav buttons (Amateum can vary by version)
    BTN_SELECTORS = [
        "div.navi-group span.app-link",
        "div.navi-group a",
        "nav.tournament-nav a",
        ".top-nav a",
    ]
    btn_selector = None
    tourn_divisions: list[tuple[str, list[str]]] = []

    try:
        page = await browser.new_page()
        await page.goto(base_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(4000)

        # Find which selector actually exists
        for sel in BTN_SELECTORS:
            els = await page.query_selector_all(sel)
            if els:
                btn_selector = sel
                logger.info(f"  Nav selector matched: '{sel}' ({len(els)} buttons)")
                break

        if not btn_selector:
            # Last resort: dump page title and return empty
            title = await page.title()
            logger.error(f"  No nav buttons found on page '{title}'; check selectors")
            return []

        tourn_names: list[str] = await page.eval_on_selector_all(
            btn_selector, "els => els.map(e => e.innerText.trim())",
        )
        tourn_names = [n for n in tourn_names if n]
        logger.info(f"  Found {len(tourn_names)} tournament buttons: {tourn_names}")

        for idx, tourn_name in enumerate(tourn_names):
            if allowed and tourn_name not in allowed:
                logger.debug(f"  Skipping '{tourn_name}' (not in allowed list)")
                continue

            tabs = await page.query_selector_all(btn_selector)
            if idx >= len(tabs):
                break

            await tabs[idx].hover()
            await page.wait_for_timeout(1500)

            # Try multiple tooltip selectors
            tooltip = (
                await page.query_selector("div.p-tooltip.p-tooltip-active")
                or await page.query_selector("div.p-tooltip")
                or await page.query_selector(".tournament-tooltip")
            )
            if not tooltip:
                tourn_divisions.append((tourn_name, []))
                logger.info(f"  '{tourn_name}': no divisions tooltip")
                continue

            tooltip_text = (await tooltip.inner_text()).strip()
            div_names = [n.strip() for n in tooltip_text.split("\n") if n.strip()]
            tourn_divisions.append((tourn_name, div_names))
            logger.info(f"  '{tourn_name}': divisions {div_names}")

            await page.mouse.move(0, 0)
            await page.wait_for_timeout(500)

    except Exception as e:
        logger.error(f"Failed to discover tournaments: {e}")
    finally:
        await browser.close()

    for tourn_name, div_names in tourn_divisions:
        if not div_names:
            url = await _click_tournament_button(pw, base_url, tourn_name, btn_selector)
            if url:
                ext_id = url.rstrip("/").split("/")[-1]
                tournaments.append(ScrapedTournament(
                    name=tourn_name, external_id=ext_id, url=url,
                ))
                logger.info(f"  Tournament '{tourn_name}' -> {ext_id}")
            continue

        for div_name in div_names:
            url = await _click_division(pw, base_url, tourn_name, div_name, btn_selector)
            if url:
                ext_id = url.rstrip("/").split("/")[-1]
                full_name = f"{tourn_name} — {div_name}"
                tournaments.append(ScrapedTournament(
                    name=full_name, external_id=ext_id, url=url,
                ))
                logger.info(f"  Tournament '{full_name}' -> {ext_id}")

    return tournaments


async def _click_tournament_button(
    pw, base_url: str, tourn_name: str, btn_selector: str | None,
) -> str | None:
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
    try:
        page = await browser.new_page()
        sel = btn_selector or "div.navi-group span.app-link"
        await page.goto(base_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_selector(sel, timeout=30000)
        await page.wait_for_timeout(3000)

        tabs = await page.query_selector_all(sel)
        for tab in tabs:
            text = (await tab.inner_text()).strip()
            if text == tourn_name:
                await tab.click()
                await page.wait_for_timeout(3000)
                return page.url
    except Exception as e:
        logger.error(f"  Failed to click tournament '{tourn_name}': {e}")
    finally:
        await browser.close()
    return None


async def _click_division(
    pw, base_url: str, tourn_name: str, div_name: str, btn_selector: str | None,
) -> str | None:
    browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
    try:
        page = await browser.new_page()
        sel = btn_selector or "div.navi-group span.app-link"
        await page.goto(base_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_selector(sel, timeout=30000)
        await page.wait_for_timeout(3000)

        tabs = await page.query_selector_all(sel)
        for tab in tabs:
            text = (await tab.inner_text()).strip()
            if text == tourn_name:
                await tab.hover()
                await page.wait_for_timeout(1500)
                break

        div_locator = page.locator(
            "div.p-tooltip.p-tooltip-active, div.p-tooltip, .tournament-tooltip"
        ).get_by_text(div_name, exact=True)
        await div_locator.first.click()
        await page.wait_for_timeout(3000)
        return page.url
    except Exception as e:
        logger.error(f"  Failed to click division '{tourn_name} — {div_name}': {e}")
    finally:
        await browser.close()
    return None

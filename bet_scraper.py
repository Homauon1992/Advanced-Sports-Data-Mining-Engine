import argparse
import csv
import os
import random
import re
import time
from typing import Dict, Iterable, List, Optional

import undetected_chromedriver as uc
from colorama import Fore, Style, init as colorama_init
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_LEAGUE_URLS = [
    "https://www.betexplorer.com/football/england/premier-league/",
    "https://www.betexplorer.com/football/spain/la-liga/",
    "https://www.betexplorer.com/football/italy/serie-a/",
]

MATCH_SELECTORS = [
    ".table-main__tt",
    ".fixtures-bet-name",
    ".event-name",
    ".bet-name",
    ".eventRow__name",
    "[data-testid='event-row-participants']",
    ".participants",
    "a[href*='/match/']",
]

TIME_SELECTORS = [
    ".table-main__time",
    ".fixture__date",
    ".event-time",
    ".eventRow__time",
    "[data-testid='event-row-time']",
    ".date",
    ".time",
]

ODDS_SELECTORS = [
    "td.table-main__odds",
    "td.odds",
    "td.best-odds",
    "td[data-odds]",
    "button[data-odds]",
    ".odds__odd",
    ".odds__value",
    ".odds",
]

ROW_SELECTORS = [
    "tr.match-on",
    "tr[data-event-id]",
    "table tr",
    "tbody tr",
    "div.eventRow",
    "div[data-testid='event-row']",
    "div[class*='eventRow']",
]


def build_driver(stealth: bool, headless: bool) -> uc.Chrome:
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1366,768")

    # Set a standard Windows Chrome user-agent.
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )

    if stealth:
        options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, use_subprocess=True)
    driver.set_page_load_timeout(45)
    return driver


def normalize_match_name(raw_name: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw_name).strip()
    if " vs " in cleaned.lower():
        parts = re.split(r"\s+vs\.?\s+", cleaned, flags=re.IGNORECASE)
        if len(parts) == 2:
            return f"{parts[0]} vs {parts[1]}"
    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        if len(parts) == 2:
            return f"{parts[0]} vs {parts[1]}"
    return cleaned


def find_text_in_row(row, selectors: Iterable[str]) -> Optional[str]:
    for selector in selectors:
        elements = row.find_elements(By.CSS_SELECTOR, selector)
        for el in elements:
            text = el.text.strip()
            if text:
                return text
    return None


def find_rows(driver: uc.Chrome) -> List:
    for selector in ROW_SELECTORS:
        rows = driver.find_elements(By.CSS_SELECTOR, selector)
        if rows:
            return rows
    return []


def extract_odds_from_row(row) -> Optional[List[str]]:
    odds_values: List[str] = []
    for selector in ODDS_SELECTORS:
        elements = row.find_elements(By.CSS_SELECTOR, selector)
        odds_values = [el.text.strip() for el in elements if el.text.strip()]
        if len(odds_values) >= 3:
            return odds_values[:3]
    text = row.text.strip()
    if text:
        odds_values = re.findall(r"\b\d+(?:\.\d+)?\b", text)
        if len(odds_values) >= 3:
            return odds_values[:3]
    return None


def extract_time_from_text(text: str) -> Optional[str]:
    match = re.search(r"\b\d{1,2}:\d{2}\b", text)
    if match:
        return match.group(0)
    return None


def extract_match_from_text(text: str) -> Optional[str]:
    match = re.search(r"([A-Za-z][A-Za-z\s\.\-']+)\s+[-–]\s+([A-Za-z][A-Za-z\s\.\-']+)", text)
    if match:
        return f"{match.group(1).strip()} vs {match.group(2).strip()}"
    match = re.search(r"([A-Za-z][A-Za-z\s\.\-']+)\s+vs\.?\s+([A-Za-z][A-Za-z\s\.\-']+)", text, re.IGNORECASE)
    if match:
        return f"{match.group(1).strip()} vs {match.group(2).strip()}"
    return None


def scrape_league(url: str, stealth: bool, headless: bool) -> List[Dict[str, str]]:
    driver = build_driver(stealth=stealth, headless=headless)
    results: List[Dict[str, str]] = []
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ",".join(ROW_SELECTORS)))
            )
        except TimeoutException:
            return results

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(5, 10))

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ",".join(ODDS_SELECTORS))
                )
            )
        except TimeoutException:
            return results

        rows = find_rows(driver)
        print("Scanning for matches...")
        for row in rows:
            time.sleep(random.uniform(3, 7))
            match_name = find_text_in_row(row, MATCH_SELECTORS)
            if not match_name:
                match_name = extract_match_from_text(row.text)
            start_time = find_text_in_row(row, TIME_SELECTORS)
            if not start_time:
                start_time = extract_time_from_text(row.text)
            odds = extract_odds_from_row(row)
            if not (match_name and start_time and odds):
                continue

            results.append(
                {
                    "League": url.rstrip("/").split("/")[-1].replace("-", " ").title(),
                    "Start Time": start_time,
                    "Match": normalize_match_name(match_name),
                    "Home": odds[0],
                    "Draw": odds[1],
                    "Away": odds[2],
                }
            )
    finally:
        driver.quit()

    return results


def print_table(rows: List[Dict[str, str]]) -> None:
    if not rows:
        print("No odds found.")
        return

    headers = ["League", "Start Time", "Match", "Home", "Draw", "Away"]
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(str(row.get(header, ""))))

    line = " | ".join(header.ljust(widths[header]) for header in headers)
    print(Fore.CYAN + line + Style.RESET_ALL)
    print("-" * len(line))

    for row in rows:
        league = str(row["League"]).ljust(widths["League"])
        start = str(row["Start Time"]).ljust(widths["Start Time"])
        match = str(row["Match"]).ljust(widths["Match"])
        home = Fore.GREEN + str(row["Home"]).ljust(widths["Home"]) + Style.RESET_ALL
        draw = Fore.YELLOW + str(row["Draw"]).ljust(widths["Draw"]) + Style.RESET_ALL
        away = Fore.RED + str(row["Away"]).ljust(widths["Away"]) + Style.RESET_ALL
        print(f"{league} | {start} | {match} | {home} | {draw} | {away}")


def save_csv(rows: List[Dict[str, str]], output_path: str) -> None:
    if not rows:
        return
    fieldnames = ["League", "Start Time", "Match", "Home", "Draw", "Away"]
    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape live 1X2 football odds.")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=bool(int(os.getenv("HEADLESS", "0"))),
        help="Run Chrome in headless mode.",
    )
    parser.add_argument(
        "--no-stealth",
        action="store_true",
        help="Disable stealth mode adjustments.",
    )
    parser.add_argument(
        "--output",
        default="live_odds.csv",
        help="Output CSV file name.",
    )
    return parser.parse_args()


def main() -> None:
    colorama_init(autoreset=True)
    args = parse_args()

    league_urls = DEFAULT_LEAGUE_URLS
    if not league_urls:
        print("No league URLs configured.")
        return

    start = time.time()
    all_rows: List[Dict[str, str]] = []
    stealth = not args.no_stealth

    for url in league_urls:
        try:
            rows = scrape_league(url, stealth, args.headless)
            all_rows.extend(rows)
        except WebDriverException as exc:
            print(f"Failed to scrape {url}: {exc}")

    if all_rows:
        print_table(all_rows)
        save_csv(all_rows, args.output)
        elapsed = time.time() - start
        print(f"\nSaved {len(all_rows)} rows to {args.output} in {elapsed:.1f}s.")
    else:
        print("No odds were collected. The site layout may have changed.")


if __name__ == "__main__":
    main()
import time
import csv
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.ourlads.com"
INDEX_URL = "https://www.ourlads.com/ncaa-football-depth-charts/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def get_soup(url: str) -> BeautifulSoup:
    """Download a page and return a BeautifulSoup object."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def get_team_depth_chart_urls():
    """
    From the main NCAAF depth chart index page, collect all 'Depth Chart' links.
    No limit now, we will scrape every team.
    """
    soup = get_soup(INDEX_URL)

    links = []
    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        href = a.get("href")
        if not href:
            continue
        if text == "Depth Chart":
            full_url = urljoin(INDEX_URL, href)
            links.append(full_url)

    links = sorted(set(links))
    print(f"Found {len(links)} team depth chart pages on index")
    return links


def to_canonical_depth_url(team_url: str) -> str:
    """
    Convert 'depth-chart.aspx?s=air-force&id=89877' into
    '.../ncaa-football-depth-charts/depth-chart/air-force/89877'
    so we always hit the main depth chart page.
    """
    parsed = urlparse(team_url)
    path = parsed.path
    query = parsed.query

    if "depth-chart.aspx" in path:
        qs = parse_qs(query)
        tid = qs.get("id", [""])[0]
        slug = qs.get("s", [""])[0]
        if slug and tid:
            return f"{BASE_URL}/ncaa-football-depth-charts/depth-chart/{slug}/{tid}"

    return team_url


def get_team_name(soup: BeautifulSoup) -> str:
    """
    Get team name from the main heading that contains 'Depth Chart',
    for example 'Air Force Falcons Depth Chart' -> 'Air Force Falcons'.
    """
    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text(strip=True)
        if "Depth Chart" in text:
            return text.replace("Depth Chart", "").strip()

    if soup.title and soup.title.string:
        text = soup.title.string
        if "Depth Chart" in text:
            return text.replace("Depth Chart", "").strip()
        return text.strip()

    return "Unknown"


def find_section_for_table(table: BeautifulSoup) -> str:
    """
    Walk backwards from the table to find the nearest header that names the section.

    We look for heading tags with text containing 'Offense', 'Defense', or 'Special Teams'.
    """
    section = "Unknown"
    for el in table.find_all_previous():
        if el.name in ("h1", "h2", "h3", "h4"):
            text = el.get_text(strip=True).lower()
            if "offense" in text:
                section = "Offense"
                break
            if "defense" in text:
                section = "Defense"
                break
            if "special teams" in text or "special team" in text:
                section = "Special Teams"
                break
    return section


def is_depth_chart_table(table: BeautifulSoup) -> bool:
    """
    Heuristic: a depth chart table has header cells with 'Pos' and 'Player 1'.
    """
    header_row = table.find("tr")
    if not header_row:
        return False

    header_text = " ".join(th.get_text(strip=True) for th in header_row.find_all(["th", "td"]))
    header_text_low = header_text.lower()
    return ("pos" in header_text_low) and ("player 1" in header_text_low)


def parse_depth_table(table: BeautifulSoup, team_name: str, unit_type: str):
    """
    Parse a single depth chart table and return starter records.

    We assume columns roughly like:
      Pos | No. | Player 1 | No | Player 2 | ...

    We only grab:
      position = col 0
      jersey   = col 1
      player   = col 2
    """
    records = []

    rows = table.find_all("tr")
    if not rows or len(rows) < 2:
        return records

    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue

        pos = cells[0].get_text(strip=True)
        if not pos or pos.lower() == "pos":
            continue

        if len(cells) < 3:
            continue

        jersey = cells[1].get_text(strip=True)
        player = cells[2].get_text(strip=True)

        if not jersey and not player:
            continue

        records.append(
            {
                "team": team_name,
                "unit_type": unit_type,
                "position": pos,
                "depth": 1,
                "jersey": jersey,
                "player": player,
            }
        )

    return records


def parse_team_depth_chart(team_url: str):
    """
    For a given team, go to the main depth chart page and parse the
    Offense / Defense / Special Teams tables, starters only.
    """
    print(f"\nScraping team index URL: {team_url}")
    depth_url = to_canonical_depth_url(team_url)
    print(f"  canonical depth chart URL: {depth_url}")

    soup = get_soup(depth_url)
    team_name = get_team_name(soup)
    print(f"  detected team name: {team_name}")

    all_records = []

    tables = soup.find_all("table")
    print(f"  found {len(tables)} tables on page")

    for idx, table in enumerate(tables):
        if not is_depth_chart_table(table):
            continue

        unit_type = find_section_for_table(table)
        print(f"  parsing table {idx} as {unit_type}")

        table_records = parse_depth_table(table, team_name, unit_type)
        print(f"    parsed {len(table_records)} starter records from this table")
        all_records.extend(table_records)

    print(f"  total {len(all_records)} starter records for this team")
    return all_records


def main():
    team_urls = get_team_depth_chart_urls()

    all_records = []

    for idx, url in enumerate(team_urls, start=1):
        print(f"\n=== Team {idx} of {len(team_urls)} ===")
        try:
            team_records = parse_team_depth_chart(url)
            all_records.extend(team_records)
        except Exception as e:
            print(f"ERROR on {url}: {e}")
        time.sleep(1)  # be polite to the site

    output_file = "ncaaf_depth_charts_starters_only_tables.csv"
    fieldnames = ["team", "unit_type", "position", "depth", "jersey", "player"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_records:
            writer.writerow(rec)

    print(f"\nDone. Saved {len(all_records)} rows to {output_file}")


if __name__ == "__main__":
    main()









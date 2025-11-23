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
    Limit to the first 10 teams while we debug.
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

    limited_links = links[:10]
    print("Limiting scrape to these team URLs:")
    for u in limited_links:
        print("  ", u)

    return limited_links


def make_pf_url(team_url: str) -> str:
    """
    Build the printer friendly URL from a team depth chart URL.

    Example:
      https://www.ourlads.com/ncaa-football-depth-charts/depth-chart.aspx?s=army&id=90038
    ->
      https://www.ourlads.com/ncaa-football-depth-charts/pfdepthchart/army/90038
    """
    parsed = urlparse(team_url)
    path = parsed.path
    query = parsed.query

    if "depth-chart.aspx" in path:
        qs = parse_qs(query)
        tid = qs.get("id", [""])[0]
        slug = qs.get("s", [""])[0]
        if slug and tid:
            return f"{BASE_URL}/ncaa-football-depth-charts/pfdepthchart/{slug}/{tid}"

    parts = path.strip("/").split("/")
    if "depth-chart" in parts:
        i = parts.index("depth-chart")
        try:
            slug = parts[i + 1]
            tid = parts[i + 2]
            return f"{BASE_URL}/ncaa-football-depth-charts/pfdepthchart/{slug}/{tid}"
        except IndexError:
            pass

    return team_url.replace("depth-chart", "pfdepthchart")


def clean_name_token(token: str) -> str:
    """Convert a slug like 'brady-anderson' into 'Brady Anderson'."""
    return token.replace("-", " ").title()


def is_position_token(token: str) -> bool:
    """
    Decide if a token is a position code (WR, LT, LDE, FS, PK, etc.)
    vs a player slug ('brady-anderson').
    Heuristic: all letters, all uppercase, no hyphen.
    """
    return token.isalpha() and token.upper() == token and "-" not in token


def parse_pf_page(pf_url: str):
    """
    Parse a printer-friendly depth chart page into records using the
    one-token-per-line format you showed.
    """
    print(f"    downloading PF page: {pf_url}")
    soup = get_soup(pf_url)
    text = soup.get_text("\n")

    # One token per non-empty line
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    print(f"    got {len(lines)} text lines from PF page")

    # Team name: first line with 'Depth Chart' that isn't the generic heading
    team_name = "Unknown"
    for line in lines:
        if "Depth Chart" in line and "Printer-Friendly" not in line:
            team_name = line.replace("Depth Chart", "").strip().strip("#").strip()
            break
    print(f"    team name from PF page: {team_name}")

    records = []
    current_unit = None   # Offense / Defense / Special Teams
    current_pos = None
    i = 0
    n = len(lines)

    header_tokens = {
        "Pos", "No", "Player", "Player 1", "Player 2",
        "Player 3", "Player 4", "Player 5"
    }

    while i < n:
        t = lines[i]
        low = t.lower()

        # Section headers
        if low == "offense":
            current_unit = "Offense"
            current_pos = None
            i += 1
            continue
        if low == "defense":
            current_unit = "Defense"
            current_pos = None
            i += 1
            continue
        if low == "special teams":
            current_unit = "Special Teams"
            current_pos = None
            i += 1
            continue

        # Ignore until we are inside a section
        if current_unit is None:
            i += 1
            continue

        # Skip headers / 'Updated' lines
        if t in header_tokens or low.startswith("updated"):
            i += 1
            continue

        # Detect a new position: uppercase alpha token whose next token is a jersey number
        if is_position_token(t) and i + 1 < n and lines[i + 1].isdigit():
            current_pos = t
            depth = 1
            i += 2  # move to first jersey after position

            # Consume jersey/name pairs for this position
            while i < n:
                if i >= n:
                    break

                low2 = lines[i].lower()

                # New section => stop this position
                if low2 in ("offense", "defense", "special teams"):
                    break

                # Potential start of a new position => stop this position
                if is_position_token(lines[i]) and i + 1 < n and lines[i + 1].isdigit():
                    break

                # Expect a jersey number
                if not lines[i].isdigit():
                    i += 1
                    continue

                jersey = lines[i]
                i += 1
                if i >= n:
                    break

                name_token = lines[i]
                i += 1

                if name_token in header_tokens or name_token.lower() in ("offense", "defense", "special teams"):
                    break

                player_name = clean_name_token(name_token)

                records.append(
                    {
                        "team": team_name,
                        "unit_type": current_unit,
                        "position": current_pos,
                        "depth": depth,
                        "jersey": jersey,
                        "player": player_name,
                    }
                )
                depth += 1

            continue  # don't i += 1 here; we already advanced inside the loop

        # Anything else, just advance
        i += 1

    print(f"    parsed {len(records)} records from PF page")
    return records


def parse_team(team_url: str):
    """Get PF URL for a team and parse its PF depth chart."""
    print(f"\nScraping team index URL: {team_url}")
    pf_url = make_pf_url(team_url)
    print(f"  printer-friendly URL: {pf_url}")
    team_records = parse_pf_page(pf_url)
    print(f"  Parsed {len(team_records)} records for this team")
    return team_records


def main():
    team_urls = get_team_depth_chart_urls()

    all_records = []

    for url in team_urls:
        try:
            team_records = parse_team(url)
            all_records.extend(team_records)
        except Exception as e:
            print(f"ERROR on {url}: {e}")
        time.sleep(1)  # be polite

    output_file = "ncaaf_depth_charts_ourlads.csv"
    fieldnames = ["team", "unit_type", "position", "depth", "jersey", "player"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_records:
            writer.writerow(rec)

    print(f"\nDone. Saved {len(all_records)} rows to {output_file}")


if __name__ == "__main__":
    main()





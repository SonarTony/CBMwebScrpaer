import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.ourlads.com"
PF_URL = "https://www.ourlads.com/ncaa-football-depth-charts/pfdepthchart/army/90038"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

def main():
    resp = requests.get(PF_URL, headers=HEADERS, timeout=20)
    # Force UTF-8 just in case
    resp.encoding = "utf-8"

    print("HTTP status:", resp.status_code)
    print("First 500 chars of raw HTML:\n")
    print(resp.text[:500])
    print("\n----------------------------------------\n")

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    print(f"Total text lines: {len(lines)}\n")
    print("First 40 lines (repr so we see weird chars):\n")
    for i, line in enumerate(lines[:40]):
        print(i, repr(line))

if __name__ == "__main__":
    main()

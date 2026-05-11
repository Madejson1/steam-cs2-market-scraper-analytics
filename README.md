# Steam Community Market CS2 Scraper App

This Streamlit app scrapes CS2 Steam Community Market data.

## What it does

### Indistinguishable items
For items such as cases, the app uses `requests`, `BeautifulSoup`, and regex to collect:

- item overview,
- historical median price,
- trading volume,
- buy/sell order histogram,
- simple market features such as price change, volume change, and spread.

Example input:

```text
Revolution Case
```

### Distinguishable items
For skins, the app uses Selenium to load rendered Steam Market pages and extract listing-level data:

- listing ID,
- asset ID,
- price,
- float value,
- pattern template,
- inspect link,
- sticker codes from listing HTML.

Example input:

```text
AK-47 | Redline (Field-Tested)
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

Selenium uses Selenium Manager, so in most setups it will automatically find or download the correct ChromeDriver. Google Chrome must be installed.

## Run

```bash
streamlit run app.py
```

## Notes

- The app does not log into Steam.
- It does not buy, sell, bid, or interact with marketplace transactions.
- Request delays are kept short but non-zero to avoid excessive load.
- Sticker values are stored as sticker codes extracted from image URLs because full sticker market names are not consistently available in rendered Steam listing HTML.

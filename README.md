# Steam CS2 Market Scraper & Deal Finder

I built a CS2 Steam Market analytics tool that combines web scraping, browser automation, structured data extraction and interactive visualization to identify potentially undervalued market listings. I included a Streamlit dashboard for scraping and analyzing CS2 Steam Market listings, including float values, pattern templates, stickers, price history and configurable deal detection.

## Overview
This project analyzes CS2 items listed on the Steam Community Market.

It supports two item types:
- indistinguishable items, such as cases, where listings are interchangeable (e.g. Revolution Case);
- distinguishable items, such as skins, where individual listings differ by float value, pattern template, stickers and price (e.g. AK-47 | Redline)

The project includes:
- a Jupyter Notebook version for detailed analysis,
- a Streamlit app for interactive use,
- a Scrapy spider for scaling the workflow to multiple items.

## Features
- scrape Steam Community Market listing data;
- extract price, listing ID, asset ID and inspect links;
- extract float value and pattern template from Steam asset data;
- extract sticker identifiers from listing HTML;
- filter skins by maximum float value;
- calculate ranking features for listings;
- analyze case price history and order book data;
- visualize price history, volume changes and listing distributions;
- configure what counts as a potential deal.

## Deal detection logic
A listing can be marked as a potential deal using configurable parameters, for example:
- maximum float value;
- price below the median listing price;
- price rank percentile;
- float rank percentile;
- sticker presence;
- custom threshold selected in the Streamlit sidebar.

Example:
A listing is marked as a potential deal when:
- its price is below the median price for the scraped listings;
- its float value is below the selected float threshold.

A “potential steal” is not treated as a guaranteed profitable trade. It is a rule-based signal based on price and item attributes. By default, the app highlights listings that are cheaper than the median and have a float value below the selected threshold.

The app allows the user to configure:
- item name;
- item type;
- number of pages to scrape;
- listings per page;
- maximum float threshold;
- request delay;
- price threshold for deal detection;
- whether stickers should be included in deal logic;
- whether lower float or lower price should be prioritized.

## Technologies
- Python
- pandas
- requests
- BeautifulSoup
- Selenium
- Scrapy
- Streamlit
- Plotly

## How to run

-pip install -r requirements.txt
-streamlit run app.py

## Example item names

Revolution Case
AK-47 | Redline (Field-Tested)
M4A1-S | Cyrex (Field-Tested)
AWP | Asiimov (Field-Tested)

## Notes
The scraper does not log into Steam, does not perform purchases, does not place buy orders and does not automate marketplace transactions. It only collects publicly visible market data for analytical purposes.

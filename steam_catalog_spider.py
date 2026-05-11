import re
import scrapy
from urllib.parse import quote


APP_ID = 730


class SteamCatalogSpider(scrapy.Spider):
    name = "steam_catalog"

    custom_settings = {
        "DOWNLOAD_DELAY": 0.7,
        "CONCURRENT_REQUESTS": 2,
        "USER_AGENT": "Mozilla/5.0",
        "FEEDS": {
            "data/scrapy_catalog.json": {
                "format": "json",
                "overwrite": True
            }
        }
    }

    def __init__(self, items=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = items or ""

    def start_requests(self):
        for raw in self.items.split("||"):
            if not raw.strip():
                continue

            market_hash_name, item_type = raw.split("::")
            url = f"https://steamcommunity.com/market/listings/{APP_ID}/{quote(market_hash_name)}"

            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "market_hash_name": market_hash_name,
                    "item_type": item_type,
                    "listing_url": url
                }
            )

    def parse(self, response):
        html = response.text
        match = re.search(r"Market_LoadOrderSpread\(\s*(\d+)\s*\)", html)
        item_nameid = int(match.group(1)) if match else None

        yield {
            "market_hash_name": response.meta["market_hash_name"],
            "item_type": response.meta["item_type"],
            "listing_url": response.meta["listing_url"],
            "page_title": response.css("title::text").get(),
            "item_nameid": item_nameid
        }

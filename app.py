import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


APP_ID = 730
COUNTRY = "PL"
LANGUAGE = "english"
CURRENCY = 1
REQUEST_DELAY_SECONDS = 0.6
SELENIUM_PAGE_DELAY_SECONDS = 0.8


st.set_page_config(
    page_title="Steam Market CS2 Scraper",
    page_icon="🎯",
    layout="wide"
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def build_listing_url(market_hash_name: str, app_id: int = APP_ID) -> str:
    return f"https://steamcommunity.com/market/listings/{app_id}/{quote(market_hash_name)}"


def make_request(url: str, params: Optional[dict] = None) -> requests.Response:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return response


def clean_price(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"[0-9]+(?:[.,][0-9]+)?", value.replace(",", ""))
    return float(match.group(0)) if match else None


def parse_steam_history_date(date_text: str):
    clean = re.sub(r":\s*\+0$", ":00 +0000", date_text)
    return pd.to_datetime(clean, errors="coerce")


def extract_item_nameid(html: str) -> Optional[int]:
    match = re.search(r"Market_LoadOrderSpread\(\s*(\d+)\s*\)", html)
    return int(match.group(1)) if match else None


def extract_balanced_json_object(text: str, variable_name: str) -> Optional[dict]:
    prefix = f"var {variable_name} ="
    start = text.find(prefix)
    if start == -1:
        return None

    brace_start = text.find("{", start)
    if brace_start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(brace_start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[brace_start:i + 1]
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return None
    return None


def slugify_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def dataframe_download_button(df: pd.DataFrame, label: str, filename: str):
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv"
    )

def scrape_distinguishable_item_render(market_hash_name, pages=5, count=100):
    all_rows = []

    for page in range(pages):
        start = page * count

        url = f"https://steamcommunity.com/market/listings/{APP_ID}/{quote(market_hash_name)}/render/"
        params = {
            "query": "",
            "start": start,
            "count": count,
            "country": COUNTRY,
            "language": "english",
            "currency": CURRENCY
        }

        response = make_request(url, params=params)
        data = response.json()

        html = data.get("results_html", "")
        assets = data.get("assets", {})

        parsed = parse_steam_listing_page(
            html=html,
            market_hash_name=market_hash_name,
            assets=assets
        )

        all_rows.append(parsed)

        if len(parsed) == 0:
            break

        total_count = data.get("total_count")
        if total_count is not None and start + count >= total_count:
            break

    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()


# -----------------------------------------------------------------------------
# Indistinguishable items: requests + BeautifulSoup
# -----------------------------------------------------------------------------

def get_market_page_html(market_hash_name: str) -> str:
    return make_request(build_listing_url(market_hash_name)).text


def scrape_item_overview(market_hash_name: str) -> pd.DataFrame:
    html = get_market_page_html(market_hash_name)
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title").get_text(strip=True) if soup.find("title") else None
    return pd.DataFrame([{
        "market_hash_name": market_hash_name,
        "listing_url": build_listing_url(market_hash_name),
        "page_title": title,
        "item_nameid": extract_item_nameid(html),
        "scraped_at": datetime.now()
    }])


def scrape_price_history(market_hash_name: str) -> pd.DataFrame:
    html = get_market_page_html(market_hash_name)
    match = re.search(r"var\s+line1\s*=\s*(\[.*?\]);", html, flags=re.DOTALL)
    if not match:
        return pd.DataFrame(columns=["market_hash_name", "date", "median_price", "volume"])

    raw_prices = json.loads(match.group(1))
    rows = []
    for point in raw_prices:
        rows.append({
            "market_hash_name": market_hash_name,
            "date": parse_steam_history_date(point[0]),
            "median_price": float(point[1]),
            "volume": int(str(point[2]).replace(",", ""))
        })
    return pd.DataFrame(rows).dropna(subset=["date"])


def scrape_order_histogram(item_nameid: int, market_hash_name: str) -> pd.DataFrame:
    url = "https://steamcommunity.com/market/itemordershistogram"
    params = {
        "country": COUNTRY,
        "language": LANGUAGE,
        "currency": CURRENCY,
        "item_nameid": item_nameid,
        "two_factor": 0
    }
    data = make_request(url, params=params).json()
    rows = []
    for side, graph_key in [("buy", "buy_order_graph"), ("sell", "sell_order_graph")]:
        for point in data.get(graph_key, []):
            rows.append({
                "market_hash_name": market_hash_name,
                "side": side,
                "price": float(point[0]),
                "quantity": int(point[1]),
                "description": point[2] if len(point) > 2 else None,
                "scraped_at": datetime.now()
            })
    return pd.DataFrame(rows)


def scrape_indistinguishable_item(market_hash_name: str) -> dict:
    overview_df = scrape_item_overview(market_hash_name)
    item_nameid = overview_df.loc[0, "item_nameid"]
    history_df = scrape_price_history(market_hash_name)
    orders_df = scrape_order_histogram(int(item_nameid), market_hash_name) if pd.notna(item_nameid) else pd.DataFrame()
    return {"overview": overview_df, "history": history_df, "orders": orders_df}


def engineer_case_features(price_history_df: pd.DataFrame, order_histogram_df: pd.DataFrame) -> dict:
    history = price_history_df.copy()
    if not history.empty:
        history = history.sort_values("date")
        history["median_price_change_pct"] = history["median_price"].pct_change()
        history["volume_change_pct"] = history["volume"].pct_change()
        history["rolling_7d_median_price"] = history["median_price"].rolling(7, min_periods=1).mean()
        history["rolling_7d_volume"] = history["volume"].rolling(7, min_periods=1).mean()

    orders = order_histogram_df.copy()
    if not orders.empty:
        best_buy = orders.loc[orders["side"].eq("buy"), "price"].max()
        best_sell = orders.loc[orders["side"].eq("sell"), "price"].min()
        spread = best_sell - best_buy if pd.notna(best_buy) and pd.notna(best_sell) else np.nan
        orders["best_buy_price"] = best_buy
        orders["best_sell_price"] = best_sell
        orders["buy_sell_spread"] = spread
        orders["spread_pct_vs_best_sell"] = spread / best_sell if pd.notna(best_sell) and best_sell else np.nan

    return {"history": history, "orders": orders}


# -----------------------------------------------------------------------------
# Distinguishable items: Selenium + Steam page source
# -----------------------------------------------------------------------------

def create_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1500,1000")
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def get_total_listings_from_html(html: str) -> Optional[int]:
    soup = BeautifulSoup(html, "html.parser")
    total = soup.select_one("#searchResults_total")
    if total:
        text = total.get_text(strip=True).replace(",", "")
        if text.isdigit():
            return int(text)
    match = re.search(r'"total_count"\s*:\s*(\d+)', html)
    return int(match.group(1)) if match else None


def parse_asset_properties(asset: dict) -> dict:
    output = {"pattern_template": None, "float_value": None, "inspect_data": None}
    for prop in asset.get("asset_properties", []):
        property_id = str(prop.get("propertyid"))
        if property_id == "1":
            output["pattern_template"] = int(prop["int_value"]) if prop.get("int_value") is not None else None
        elif property_id == "2":
            output["float_value"] = float(prop["float_value"]) if prop.get("float_value") is not None else None
        elif property_id == "6":
            output["inspect_data"] = prop.get("string_value")
    return output


def build_inspect_link(asset: dict, inspect_data: Optional[str]) -> Optional[str]:
    actions = asset.get("market_actions") or asset.get("actions") or []
    if not actions or not inspect_data:
        return None
    link_template = actions[0].get("link")
    return link_template.replace("%propid:6%", inspect_data) if link_template else None


def parse_sticker_code_from_src(src: Optional[str]) -> Optional[str]:
    if not src:
        return None
    filename = src.split("/")[-1]
    code = filename.split(".")[0]
    return code.replace("_", " ")


def extract_sticker_codes_from_row(row) -> list:
    stickers = [parse_sticker_code_from_src(img.get("src")) for img in row.select(".sticker_info img")]
    stickers = stickers[:4]
    while len(stickers) < 4:
        stickers.append(None)
    return stickers

def build_listing_url(market_hash_name):
    return f"https://steamcommunity.com/market/listings/{APP_ID}/{quote(market_hash_name)}"


def build_listing_anchor_url(market_hash_name, listing_id):
    return f"{build_listing_url(market_hash_name)}#listing_{listing_id}"

def parse_steam_listing_page(html, market_hash_name, assets=None):
    soup = BeautifulSoup(html, "html.parser")

    if assets is None:
        assets = extract_balanced_json_object(html, "g_rgAssets") or {}

    rows = []

    for row in soup.select(".market_recent_listing_row"):
        row_id = row.get("id", "")
        listing_match = re.search(r"listing_(\d+)", row_id)
        listing_id = listing_match.group(1) if listing_match else None

        row_html = str(row)
        asset_match = re.search(
            r"BuyMarketListing\('listing',\s*'(\d+)',\s*\d+,\s*'2',\s*'(\d+)'\)",
            row_html
        )
        asset_id = asset_match.group(2) if asset_match else None
        asset = assets.get(str(APP_ID), {}).get("2", {}).get(str(asset_id), {})
        props = parse_asset_properties(asset)

        with_fee = row.select_one(".market_listing_price_with_fee")
        without_fee = row.select_one(".market_listing_price_without_fee")
        price_with_fee = clean_price(with_fee.get_text(" ", strip=True)) if with_fee else None
        price_without_fee = clean_price(without_fee.get_text(" ", strip=True)) if without_fee else None

        inspect_a = row.select_one(".market_listing_row_action a")
        inspect_link_html = inspect_a.get("href") if inspect_a else None
        inspect_link_asset = build_inspect_link(asset, props["inspect_data"])
        sticker_codes = extract_sticker_codes_from_row(row)

        rows.append({
            "market_hash_name": market_hash_name,
            "listing_id": listing_id,
            "asset_id": asset_id,
            "listing_url": build_listing_anchor_url(market_hash_name, listing_id),
            "price_with_fee": price_with_fee,
            "price_without_fee": price_without_fee,
            "total_price": price_with_fee,
            "float_value": props["float_value"],
            "pattern_template": props["pattern_template"],
            "inspect_link": inspect_link_asset or inspect_link_html,
            "sticker_code_1": sticker_codes[0],
            "sticker_code_2": sticker_codes[1],
            "sticker_code_3": sticker_codes[2],
            "sticker_code_4": sticker_codes[3],
            "scraped_at": datetime.now()
        })

    return pd.DataFrame(rows)


def scrape_distinguishable_item_with_selenium(
    market_hash_name: str,
    pages: Union[int, str] = 3,
    count: int = 100,
    headless: bool = True
) -> pd.DataFrame:
    driver = create_chrome_driver(headless=headless)
    all_rows = []

    try:
        base_url = build_listing_url(market_hash_name)
        first_url = f"{base_url}?start=0&count={count}"
        driver.get(first_url)

        WebDriverWait(driver, 30).until(
            lambda d: d.find_elements(By.ID, "searchResultsRows") or "There are no listings" in d.page_source
        )
        time.sleep(SELENIUM_PAGE_DELAY_SECONDS)

        first_html = driver.page_source
        total_listings = get_total_listings_from_html(first_html)

        if pages == "max" and total_listings:
            page_count = math.ceil(total_listings / count)
        elif pages == "max":
            page_count = 1
        else:
            page_count = int(pages)

        all_rows.append(parse_steam_listing_page(first_html, market_hash_name))

        for page in range(1, page_count):
            start = page * count
            driver.get(f"{base_url}?start={start}&count={count}")
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: d.find_elements(By.ID, "searchResultsRows") or "There are no listings" in d.page_source
                )
                time.sleep(SELENIUM_PAGE_DELAY_SECONDS)
                all_rows.append(parse_steam_listing_page(driver.page_source, market_hash_name))
            except TimeoutException:
                st.warning(f"Timeout on page {page + 1}. This page was skipped.")
                continue

    finally:
        driver.quit()

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True).drop_duplicates("listing_id")


def engineer_listing_features(listings_df: pd.DataFrame, float_threshold: float) -> pd.DataFrame:
    out = listings_df.copy()
    if out.empty:
        return out

    out["price_rank_pct"] = out["total_price"].rank(pct=True, ascending=True)
    out["is_cheaper_than_median"] = out["total_price"] < out["total_price"].median()
    out["is_low_float"] = out["float_value"].notna() & (out["float_value"] <= float_threshold)
    out["float_rank_pct"] = out["float_value"].rank(pct=True, ascending=True)
    out["has_stickers"] = out[["sticker_code_1", "sticker_code_2", "sticker_code_3", "sticker_code_4"]].notna().any(axis=1)
    out["sticker_count"] = out[["sticker_code_1", "sticker_code_2", "sticker_code_3", "sticker_code_4"]].notna().sum(axis=1)
    out["is_potential_deal"] = out["is_cheaper_than_median"] & out["is_low_float"]
    return out


# -----------------------------------------------------------------------------
# Interface
# -----------------------------------------------------------------------------

st.title("Steam Community Market CS2 Scraper")
st.caption("Static market data is collected with requests and BeautifulSoup. Listing-level skin data is collected with Selenium from rendered Steam Market pages.")

with st.sidebar:
    st.header("Scraping settings")
    item_type = st.radio("Item type", ["Distinguishable skin", "Indistinguishable item"])

    if item_type == "Distinguishable skin":
        default_item = "AK-47 | Redline (Field-Tested)"
        st.caption("Example format: AK-47 | Redline (Field-Tested)")
    else:
        default_item = "Revolution Case"
        st.caption("Example format: Revolution Case")

    market_hash_name = st.text_input("Steam market hash name", value=default_item)

    if item_type == "Distinguishable skin":
        max_float = st.number_input("Show listings with float <=", min_value=0.0, max_value=1.0, value=0.15, step=0.01, format="%.4f")
        pages_mode = st.selectbox("Pages to scrape", ["1", "3", "5", "10", "max"], index=1)
        pages = "max" if pages_mode == "max" else int(pages_mode)
        count = st.selectbox("Results per page", [10, 20, 50, 100], index=3)
        headless = st.checkbox("Run browser in headless mode", value=True)
    else:
        max_float = None
        pages = 1
        count = 100
        headless = True

    run_button = st.button("Run scraper", type="primary")


if not run_button:
    st.info("Enter a market hash name in the sidebar and run the scraper.")
    st.stop()

if not market_hash_name.strip():
    st.error("Please enter a Steam market hash name.")
    st.stop()


# -----------------------------------------------------------------------------
# Indistinguishable page
# -----------------------------------------------------------------------------

if item_type == "Indistinguishable item":
    with st.spinner("Scraping market overview, price history and order book..."):
        result = scrape_indistinguishable_item(market_hash_name.strip())
        overview_df = result["overview"]
        history_df = result["history"]
        orders_df = result["orders"]
        features = engineer_case_features(history_df, orders_df)
        history_features_df = features["history"]
        orders_features_df = features["orders"]

    st.subheader("Overview")
    st.dataframe(overview_df, use_container_width=True)

    if not history_features_df.empty:
        latest = history_features_df.sort_values("date").tail(1).iloc[0]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Latest median price", f"${latest['median_price']:.2f}")
        col2.metric("Latest volume", f"{int(latest['volume']):,}")
        col3.metric("Price change pct", f"{latest['median_price_change_pct']:.2%}" if pd.notna(latest["median_price_change_pct"]) else "n/a")
        col4.metric("Volume change pct", f"{latest['volume_change_pct']:.2%}" if pd.notna(latest["volume_change_pct"]) else "n/a")

        st.subheader("Recent price history")
        st.dataframe(history_features_df.tail(5), use_container_width=True)

        fig_price = px.line(history_features_df, x="date", y=["median_price", "rolling_7d_median_price"], title="Median price history")
        st.plotly_chart(fig_price, use_container_width=True)

        fig_volume = px.line(history_features_df, x="date", y=["volume", "rolling_7d_volume"], title="Trading volume history")
        st.plotly_chart(fig_volume, use_container_width=True)

    if not orders_features_df.empty:
        st.subheader("Buy and sell order book")
        best_buy = orders_features_df["best_buy_price"].dropna().iloc[0] if orders_features_df["best_buy_price"].notna().any() else np.nan
        best_sell = orders_features_df["best_sell_price"].dropna().iloc[0] if orders_features_df["best_sell_price"].notna().any() else np.nan
        spread = orders_features_df["buy_sell_spread"].dropna().iloc[0] if orders_features_df["buy_sell_spread"].notna().any() else np.nan
        c1, c2, c3 = st.columns(3)
        c1.metric("Best buy price", f"${best_buy:.2f}" if pd.notna(best_buy) else "n/a")
        c2.metric("Best sell price", f"${best_sell:.2f}" if pd.notna(best_sell) else "n/a")
        c3.metric("Buy-sell spread", f"${spread:.2f}" if pd.notna(spread) else "n/a")

        fig_orders = px.line(orders_features_df, x="price", y="quantity", color="side", title="Order histogram")
        st.plotly_chart(fig_orders, use_container_width=True)
        st.dataframe(orders_features_df.head(20), use_container_width=True)

    st.subheader("Downloads")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        dataframe_download_button(overview_df, "Download overview", f"indistinguishable_{slugify_name(market_hash_name)}_overview.csv")
    with col_b:
        dataframe_download_button(history_features_df, "Download history features", f"indistinguishable_{slugify_name(market_hash_name)}_history_features.csv")
    with col_c:
        dataframe_download_button(orders_features_df, "Download order features", f"indistinguishable_{slugify_name(market_hash_name)}_orders_features.csv")


# -----------------------------------------------------------------------------
# Distinguishable page
# -----------------------------------------------------------------------------

else:
    with st.spinner("Opening Steam Market with Selenium and collecting listing data..."):
        raw_listings_df = scrape_distinguishable_item_render(
            market_hash_name.strip(),
            pages=pages,
            count=count
        )
        features_df = engineer_listing_features(raw_listings_df, max_float)

        st.subheader("Listings")
        st.dataframe(
            features_df,
            column_config={
                "listing_url": st.column_config.LinkColumn("Steam listing"),
                "inspect_link": st.column_config.LinkColumn("Inspect link"),
            },
            use_container_width=True
        )

        filtered_df = features_df[features_df["float_value"].notna() & (features_df["float_value"] <= max_float)].copy()

    if features_df.empty:
        st.warning("No listings were parsed. Try fewer pages, a different item name, or a non-headless browser run.")
        st.stop()

    st.subheader("Listing summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Parsed listings", f"{len(features_df):,}")
    col2.metric("Listings under float threshold", f"{len(filtered_df):,}")
    col3.metric("Median price", f"${features_df['total_price'].median():.2f}")
    col4.metric("Median float", f"{features_df['float_value'].median():.4f}")

    st.subheader("Listings under selected float threshold")
    display_cols = [
        "market_hash_name", "listing_id", "price_with_fee", "price_without_fee",
        "float_value", "pattern_template", "sticker_code_1", "sticker_code_2",
        "sticker_code_3", "sticker_code_4", "is_potential_deal", "inspect_link"
    ]
    st.dataframe(filtered_df[display_cols].sort_values(["float_value", "price_with_fee"]).head(50), use_container_width=True)

    st.subheader("Last five parsed listings")
    st.dataframe(features_df[display_cols].tail(5), use_container_width=True)

    st.subheader("Visual analysis")
    c1, c2 = st.columns(2)
    with c1:
        fig_float = px.histogram(features_df.dropna(subset=["float_value"]), x="float_value", nbins=30, title="Float distribution")
        st.plotly_chart(fig_float, use_container_width=True)
    with c2:
        fig_scatter = px.scatter(
            features_df.dropna(subset=["float_value", "total_price"]),
            x="float_value",
            y="total_price",
            color="is_potential_deal",
            hover_data=["listing_id", "pattern_template", "sticker_count"],
            title="Float vs price"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    fig_rank = px.scatter(
        features_df.dropna(subset=["float_rank_pct", "price_rank_pct"]),
        x="float_rank_pct",
        y="price_rank_pct",
        color="is_potential_deal",
        hover_data=["listing_id", "float_value", "total_price", "pattern_template"],
        title="Float percentile vs price percentile"
    )
    st.plotly_chart(fig_rank, use_container_width=True)

    st.subheader("Download")
    dataframe_download_button(features_df, "Download all listing features", f"distinguishable_{slugify_name(market_hash_name)}_listing_features.csv")
    dataframe_download_button(filtered_df, "Download filtered low-float listings", f"distinguishable_{slugify_name(market_hash_name)}_low_float.csv")

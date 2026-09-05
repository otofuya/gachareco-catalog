#!/usr/bin/env python3
"""
ガチャカタログ自動更新スクリプト
GitHub Actionsで週1回実行し、各サイトから新商品情報を取得して
docs/gacha-catalog.json を更新する。

対象サイト:
  1. ガチャガチャアイランド: https://gacha-island.jp/  (全メーカー横断)
  2. バンダイ ガシャポン: https://gashapon.jp/products/result.php

Playwright使用（JS描画サイト対応）
実行: python scripts/scrape_catalog.py
"""

import hashlib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
except ImportError:
    print("依存パッケージをインストール: pip install playwright && playwright install chromium")
    sys.exit(1)

from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CATALOG_PATH = Path(__file__).parent.parent / "docs" / "gacha-catalog.json"

DEFAULT_COLORS = [
    ("#ef4444", "#fca5a5"),
    ("#f97316", "#fdba74"),
    ("#eab308", "#fde047"),
    ("#22c55e", "#86efac"),
    ("#3b82f6", "#93c5fd"),
    ("#8b5cf6", "#c4b5fd"),
    ("#ec4899", "#f9a8d4"),
    ("#06b6d4", "#67e8f9"),
]

KNOWN_SERIES = {
    "ポケモン": ("pokemon", "ポケモン", "#f59e0b"),
    "ポケットモンスター": ("pokemon", "ポケモン", "#f59e0b"),
    "ちいかわ": ("chiikawa", "ちいかわ", "#f472b6"),
    "mofusand": ("mofusand", "mofusand", "#fb923c"),
    "モフサンド": ("mofusand", "mofusand", "#fb923c"),
    "たまごっち": ("tamagotchi", "たまごっち", "#a78bfa"),
    "ドラゴンボール": ("dragonball", "ドラゴンボール", "#f97316"),
    "ワンピース": ("onepiece", "ワンピース", "#ef4444"),
    "ONE PIECE": ("onepiece", "ワンピース", "#ef4444"),
    "鬼滅の刃": ("kimetsu", "鬼滅の刃", "#22c55e"),
    "呪術廻戦": ("jujutsu", "呪術廻戦", "#6366f1"),
    "すみっコぐらし": ("sumikko", "すみっコぐらし", "#86efac"),
    "サンリオ": ("sanrio", "サンリオ", "#f9a8d4"),
    "ディズニー": ("disney", "ディズニー", "#60a5fa"),
    "スプラトゥーン": ("splatoon", "スプラトゥーン", "#4ade80"),
    "スーパーマリオ": ("mario", "スーパーマリオ", "#ef4444"),
    "マリオ": ("mario", "スーパーマリオ", "#ef4444"),
    "星のカービィ": ("kirby", "星のカービィ", "#f472b6"),
    "カービィ": ("kirby", "星のカービィ", "#f472b6"),
    "クレヨンしんちゃん": ("shinchan", "クレヨンしんちゃん", "#fbbf24"),
    "SPY×FAMILY": ("spyfamily", "SPY×FAMILY", "#ef4444"),
    "スパイファミリー": ("spyfamily", "SPY×FAMILY", "#ef4444"),
    "推しの子": ("oshinoko", "推しの子", "#c084fc"),
    "シンカリオン": ("shinkalion", "シンカリオン", "#3b82f6"),
    "仮面ライダー": ("kamenrider", "仮面ライダー", "#22c55e"),
    "ウルトラマン": ("ultraman", "ウルトラマン", "#ef4444"),
    "ガンダム": ("gundam", "ガンダム", "#6366f1"),
    "プリキュア": ("precure", "プリキュア", "#f472b6"),
    "トイ・ストーリー": ("toystory", "トイ・ストーリー", "#60a5fa"),
    "ミニオン": ("minions", "ミニオン", "#fbbf24"),
    "どうぶつの森": ("animalcrossing", "どうぶつの森", "#4ade80"),
    "ハイキュー": ("haikyu", "ハイキュー!!", "#f97316"),
    "チェンソーマン": ("chainsawman", "チェンソーマン", "#ef4444"),
    "僕のヒーローアカデミア": ("heroaca", "僕のヒーローアカデミア", "#22c55e"),
    "ヒロアカ": ("heroaca", "僕のヒーローアカデミア", "#22c55e"),
    "名探偵コナン": ("conan", "名探偵コナン", "#3b82f6"),
    "コナン": ("conan", "名探偵コナン", "#3b82f6"),
    "アンパンマン": ("anpanman", "アンパンマン", "#f97316"),
    "ドラえもん": ("doraemon", "ドラえもん", "#3b82f6"),
    "クロミ": ("sanrio", "サンリオ", "#f9a8d4"),
    "シナモロール": ("sanrio", "サンリオ", "#f9a8d4"),
    "マイメロディ": ("sanrio", "サンリオ", "#f9a8d4"),
    "リラックマ": ("rilakkuma", "リラックマ", "#fbbf24"),
    "ミッフィー": ("miffy", "ミッフィー", "#f97316"),
    "スヌーピー": ("snoopy", "スヌーピー", "#fbbf24"),
    "PEANUTS": ("snoopy", "スヌーピー", "#fbbf24"),
    "トムとジェリー": ("tomandjerry", "トムとジェリー", "#8b5cf6"),
    "ムーミン": ("moomin", "ムーミン", "#06b6d4"),
    "コウペンちゃん": ("koupen", "コウペンちゃん", "#86efac"),
    "にゃんこ大戦争": ("nyanko", "にゃんこ大戦争", "#ef4444"),
    "ブルーロック": ("bluelock", "ブルーロック", "#3b82f6"),
    "東京リベンジャーズ": ("tokyorev", "東京リベンジャーズ", "#6366f1"),
    "葬送のフリーレン": ("frieren", "葬送のフリーレン", "#8b5cf6"),
    "フリーレン": ("frieren", "葬送のフリーレン", "#8b5cf6"),
    "進撃の巨人": ("aot", "進撃の巨人", "#22c55e"),
    "ヒプノシスマイク": ("hypmic", "ヒプノシスマイク", "#6366f1"),
    "ツイステ": ("twisted", "ツイステッドワンダーランド", "#6366f1"),
    "ピクミン": ("pikmin", "ピクミン", "#ef4444"),
    "あつまれ": ("animalcrossing", "どうぶつの森", "#4ade80"),
    "NieR": ("nier", "NieR", "#6366f1"),
    "BEYBLADE": ("beyblade", "ベイブレード", "#3b82f6"),
    "ベイブレード": ("beyblade", "ベイブレード", "#3b82f6"),
    "トミカ": ("tomica", "トミカ", "#ef4444"),
    "プラレール": ("plarail", "プラレール", "#3b82f6"),
    "パンダの穴": ("pandanoana", "パンダの穴", "#22c55e"),
    "コップのフチ子": ("fuchiko", "コップのフチ子", "#f472b6"),
}


def load_catalog() -> dict:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog: dict) -> None:
    catalog["updatedAt"] = date.today().isoformat()
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"カタログ保存完了: version={catalog['version']}")


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def extract_price(text: str) -> int:
    nums = re.findall(r"\d+", text.replace(",", ""))
    for n in nums:
        val = int(n)
        if 100 <= val <= 3000:
            return val
    return 300


def extract_release(text: str) -> str:
    m = re.search(r"(\d{4})[年./\-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}.{m.group(2).zfill(2)}"
    return f"{date.today().year}.{date.today().month:02d}"


def detect_series(title: str, category_hint: str = "") -> tuple:
    for text in [category_hint, title]:
        for keyword, (sid, sname, color) in KNOWN_SERIES.items():
            if keyword in text:
                return sid, sname, color
    if category_hint and len(category_hint) >= 2:
        slug = re.sub(r"[^a-zA-Z0-9぀-鿿]", "", category_hint).lower()
        sid = stable_hash(category_hint)
        return sid, category_hint, "#6366f1"
    return "other", "その他", "#6366f1"


def default_items(gacha_id: str, count: int = 4) -> list[dict]:
    items = []
    for i in range(min(count, 8)):
        top, bottom = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        items.append({
            "id": f"{gacha_id}-{i}",
            "name": f"アイテム{i+1}",
            "topColor": top,
            "bottomColor": bottom,
            "charColor": top,
        })
    return items


def fetch_page_pw(page, url: str, wait_selector: str | None = None) -> BeautifulSoup | None:
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=10000)
            except PwTimeout:
                pass
        page.wait_for_timeout(2000)
        html = page.content()
        return BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(f"  ページ取得失敗 ({url}): {e}")
        return None


def scrape_gacha_island(page) -> list[dict]:
    """ガチャガチャアイランド（全メーカー横断サイト）からガチャ情報を取得

    構造: li.p-postList__item > a.p-postList__link
      - h3.p-postList__title → 商品名
      - figure img → 画像URL
      - span.c-postThumb__cat → シリーズ/カテゴリ名
      - table.gacha-info-table: 発売, 価格・種類, メーカー
    """
    print("ガチャガチャアイランド: スクレイピング開始")
    results = []
    base_url = "https://gacha-island.jp"

    for page_num in range(1, 6):
        url = base_url if page_num == 1 else f"{base_url}/page/{page_num}/"
        soup = fetch_page_pw(page, url, wait_selector=".p-postList__item")
        if not soup:
            continue

        cards = soup.select("li.p-postList__item")
        print(f"  ページ{page_num}: {len(cards)} 件検出")

        for card in cards:
            try:
                title_el = card.select_one("h3.p-postList__title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                cat_el = card.select_one("span.c-postThumb__cat")
                category_hint = cat_el.get_text(strip=True) if cat_el else ""

                gacha_id = f"gi-{stable_hash(title)}"
                sid, sname, scolor = detect_series(title, category_hint)

                img_el = card.select_one("img.c-postThumb__img")
                image_url = None
                if img_el:
                    image_url = img_el.get("src") or ""
                    if image_url.startswith("data:") or not image_url:
                        image_url = None

                price = 300
                release = extract_release("")
                maker = ""
                item_count = 4

                info_table = card.select_one("table.gacha-info-table")
                if info_table:
                    for row in info_table.select("tr"):
                        th = row.select_one("th")
                        td = row.select_one("td")
                        if not th or not td:
                            continue
                        label = th.get_text(strip=True)
                        value = td.get_text(strip=True)
                        if label == "発売":
                            release = extract_release(value)
                        elif "価格" in label:
                            price = extract_price(value)
                            m = re.search(r"全(\d+)種", value)
                            if m:
                                item_count = int(m.group(1))
                        elif label == "メーカー":
                            maker = value

                if not maker:
                    maker = "不明"

                results.append({
                    "id": gacha_id,
                    "seriesId": sid,
                    "seriesName": sname,
                    "title": title,
                    "maker": maker,
                    "price": price,
                    "category": "gacha",
                    "release": release,
                    "imageUrl": image_url,
                    "items": default_items(gacha_id, count=item_count),
                })
            except Exception as e:
                print(f"  スキップ: {e}")
                continue

        time.sleep(1)

    print(f"  取得件数: {len(results)}")
    return results


def scrape_bandai(page) -> list[dict]:
    """バンダイ ガシャポン商品検索ページからガチャ情報を取得

    構造: div.c-card__list.pg-result__list
      - p.c-card__name → 商品名
      - span.c-card__price--main → 価格
      - p.c-card__thumb img → 画像URL (bandai-a.akamaihd.net)
    """
    print("バンダイ: スクレイピング開始")
    results = []
    base_url = "https://gashapon.jp"

    url = f"{base_url}/products/result.php"
    soup = fetch_page_pw(page, url, wait_selector=".c-card__name")
    if not soup:
        return results

    cards = soup.select("div.c-card__list.pg-result__list")
    print(f"  {len(cards)} 件検出")

    for card in cards:
        try:
            name_el = card.select_one("p.c-card__name")
            if not name_el:
                continue
            title = name_el.get_text(strip=True)
            if len(title) < 3:
                continue

            gacha_id = f"bd-{stable_hash(title)}"
            sid, sname, scolor = detect_series(title)

            price_el = card.select_one("span.c-card__price--main")
            price = extract_price(price_el.get_text(strip=True)) if price_el else 300

            img_el = card.select_one("p.c-card__thumb img")
            image_url = img_el["src"] if img_el and img_el.get("src") else None
            if image_url and image_url.startswith("data:"):
                image_url = None

            results.append({
                "id": gacha_id,
                "seriesId": sid,
                "seriesName": sname,
                "title": title,
                "maker": "バンダイ",
                "price": price,
                "category": "gashapon",
                "release": extract_release(""),
                "imageUrl": image_url,
                "items": default_items(gacha_id),
            })
        except Exception as e:
            print(f"  スキップ: {e}")
            continue

    print(f"  取得件数: {len(results)}")
    return results


def merge_new_gachas(catalog: dict, new_gachas: list[dict]) -> bool:
    """新しいガチャデータをカタログにマージ。変更があればTrueを返す"""
    existing = {g["id"]: g for g in catalog["gachas"]}
    changed = False

    for gacha in new_gachas:
        gid = gacha.get("id")
        if not gid:
            continue
        if gid not in existing:
            catalog["gachas"].append(gacha)
            existing[gid] = gacha
            changed = True
            print(f"    新規追加: {gacha['title']}")
        else:
            if gacha.get("imageUrl") and not existing[gid].get("imageUrl"):
                existing[gid]["imageUrl"] = gacha["imageUrl"]
                changed = True

    existing_series_ids = {s["id"] for s in catalog["series"]}
    for gacha in new_gachas:
        sid = gacha.get("seriesId")
        if sid and sid not in existing_series_ids:
            scolor = "#6366f1"
            for _, (ks, _, kc) in KNOWN_SERIES.items():
                if ks == sid:
                    scolor = kc
                    break
            catalog["series"].append({
                "id": sid,
                "name": gacha.get("seriesName", sid),
                "accentColor": scolor,
            })
            existing_series_ids.add(sid)

    if not changed:
        print("  新規なし")
    return changed


def main():
    print("=== ガチャカタログ自動更新 (Playwright) ===")
    catalog = load_catalog()
    print(f"現在のカタログ: version={catalog['version']}, "
          f"シリーズ={len(catalog['series'])}, ガチャ={len(catalog['gachas'])}")

    changed = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        pg = ctx.new_page()

        for scraper_name, scraper_fn in [
            ("ガチャガチャアイランド", scrape_gacha_island),
            ("バンダイ", scrape_bandai),
        ]:
            try:
                new_gachas = scraper_fn(pg)
                if merge_new_gachas(catalog, new_gachas):
                    changed = True
            except Exception as e:
                print(f"  エラー ({scraper_name}): {e}")

        browser.close()

    if changed:
        catalog["version"] += 1

    catalog["lastChecked"] = date.today().isoformat()
    save_catalog(catalog)

    if changed:
        print(f"更新完了: version={catalog['version']}, "
              f"シリーズ={len(catalog['series'])}, ガチャ={len(catalog['gachas'])}")
    else:
        print(f"新規なし（lastChecked更新のみ）: version={catalog['version']}")


if __name__ == "__main__":
    main()

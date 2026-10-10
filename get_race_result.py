import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from upload_to_gcs import upload_to_gcs

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

JST = timezone(timedelta(hours=9))

# 払戻表のtrクラス名 -> 内部の券種キー
PAYOUT_ROWS = {
    "Tansho": "tansho",
    "Fukusho": "fukusho",
    "Wakuren": "wakuren",
    "Umaren": "umaren",
    "Wide": "wide",
    "Umatan": "umatan",
    "Fuku3": "sanrenpuku",
    "Tan3": "sanrentan",
}


def _span_texts(parent):
    return [s.get_text(strip=True) for s in parent.find_all("span")]


# 払戻表の1行(1券種)から、的中した組み合わせと払戻額(100円あたり)を抽出する
# 単勝・複勝は div>span、馬連などの組み合わせ券種は 1組=1つの ul>li>span で、
# どちらも空のspanは表示上のスペーサーなので除外する
# 同着があると組み合わせが複数になり、払戻額も <br> 区切りで複数入る
def parse_payout_row(tr):
    result_td = tr.find("td", class_="Result")
    payout_td = tr.find("td", class_="Payout")
    if result_td is None or payout_td is None:
        return []

    uls = result_td.find_all("ul")
    if uls:
        combos = [[int(t) for t in _span_texts(ul) if t.isdigit()] for ul in uls]
    else:
        numbers = [int(t) for t in _span_texts(result_td) if t.isdigit()]
        combos = [[n] for n in numbers]
    combos = [c for c in combos if c]

    payouts = [
        int(re.sub(r"[^\d]", "", text))
        for text in payout_td.stripped_strings
        if re.search(r"\d", text)
    ]

    return [
        {"numbers": numbers, "payout": payout}
        for numbers, payout in zip(combos, payouts)
    ]


def _horse_id(href):
    return href.rstrip("/").split("/")[-1] if href else None


# 結果ページの全着順表から、各馬の馬番・着順・人気・単勝オッズを抽出する
# 着順が数字でない馬(取消・除外・中止・失格など)は finishing_order=None とし、
# 取消・除外は started=False(=出走していない)として区別する
def parse_results(soup):
    table = soup.select_one("table#All_Result_Table") or soup.select_one("table.RaceTable01")
    if table is None:
        return []

    horses = []
    for tr in table.select("tr.HorseList"):
        rank_text = tr.select_one(".Result_Num")
        rank_text = rank_text.get_text(strip=True) if rank_text else ""
        num_tds = tr.find_all("td", class_="Num")
        horse_number = num_tds[1].get_text(strip=True) if len(num_tds) > 1 else ""
        horse_a = tr.select_one(".Horse_Name a")
        popularity = tr.select_one(".OddsPeople")
        odds = tr.select_one("td.Odds.Txt_R")

        if not horse_number.isdigit() or horse_a is None:
            continue

        horses.append({
            "horse_id": _horse_id(horse_a.get("href")),
            "horse_number": int(horse_number),
            "finishing_order": int(rank_text) if rank_text.isdigit() else None,
            "started": rank_text not in ("取", "除"),
            "popularity": int(popularity.get_text(strip=True)) if popularity and popularity.get_text(strip=True).isdigit() else None,
            "odds": float(odds.get_text(strip=True)) if odds and re.fullmatch(r"[\d.]+", odds.get_text(strip=True)) else None,
        })
    return horses


# レース結果と払戻を取得する。結果が未確定(払戻表がまだ無い)の場合は None を返す
def fetch_race_result(race_id):
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    payouts = {}
    for tr in soup.select("table.Payout_Detail_Table tr"):
        for class_name, key in PAYOUT_ROWS.items():
            if class_name in (tr.get("class") or []):
                payouts[key] = parse_payout_row(tr)

    results = parse_results(soup)
    if not payouts.get("tansho") or not results:
        return None

    return {
        "race_id": race_id,
        "fetched_at": datetime.now(JST).isoformat(),
        "results": results,
        "payouts": payouts,
    }


# 結果を取得してjsonに保存し、GCSへアップロードする(結果未確定ならNone)
def get_race_result(race_id, bucket_name="keibaps-data"):
    race_result = fetch_race_result(race_id)
    if race_result is None:
        return None

    output_dir = "raceresult"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{race_id}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(race_result, f, ensure_ascii=False, indent=4)

    upload_to_gcs(bucket_name, output_file, f"raceresult/{race_id}.json")
    return race_result

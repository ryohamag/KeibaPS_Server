import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from get_past_results import get_past_results
from upload_to_gcs import upload_to_gcs

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

JST = timezone(timedelta(hours=9))


# "10:00発走 / ダ1000m (右) / 天候:晴 / 馬場:良" のようなテキストから "ダ1000" を抽出
def extract_race_type(race_data_text):
    for part in race_data_text.split("/"):
        part = part.strip()
        match = re.search(r"(芝|ダ)\d+", part)
        if match:
            return match.group(0)
    return None


def _text_or_none(el):
    if el is None:
        return None
    text = el.get_text(strip=True)
    return text or None


# 出馬表の1行(1頭分)から、当該レースの予定情報を抽出する
# 取消(除外)馬は tr に "Cancel" クラスが付き、列構成が一部変わるため
# クラス名の前方一致・部分一致と「HorseInfoの次の次が斤量」という位置関係で吸収する
def parse_entry(tr):
    classes = tr.get("class") or []
    is_scratched = "Cancel" in classes

    waku_td = tr.find("td", class_=lambda c: c and c.startswith("Waku"))
    umaban_td = tr.find("td", class_=lambda c: c and c.startswith("Umaban"))

    horse_name_a = tr.select_one(".HorseName a")
    if horse_name_a is None:
        return None
    horse_url = horse_name_a.get("href")
    horse_name = horse_name_a.get("title") or horse_name_a.get_text(strip=True)

    jockey_td = tr.find("td", class_=lambda c: c and "Jockey" in c)
    jockey_a = jockey_td.find("a") if jockey_td else None
    scheduled_jockey = _text_or_none(jockey_a) or _text_or_none(jockey_td)

    trainer_td = tr.find("td", class_=lambda c: c and "Trainer" in c)
    trainer_a = trainer_td.find("a") if trainer_td else None
    trainer = _text_or_none(trainer_a)

    horse_info_td = tr.find("td", class_="HorseInfo")
    scheduled_weight = None
    if horse_info_td is not None:
        barei_td = horse_info_td.find_next_sibling("td")
        weight_td = barei_td.find_next_sibling("td") if barei_td is not None else None
        scheduled_weight = _text_or_none(weight_td)

    frame_number = _text_or_none(waku_td)
    horse_number = _text_or_none(umaban_td)

    return {
        "horse_url": horse_url,
        "horse_name": horse_name,
        "frame_number": int(frame_number) if frame_number and frame_number.isdigit() else None,
        "horse_number": int(horse_number) if horse_number and horse_number.isdigit() else None,
        "scheduled_jockey": scheduled_jockey,
        "scheduled_weight": scheduled_weight,
        "trainer": trainer,
        "is_scratched": is_scratched,
    }


# 出馬表ページから、レースタイトル・レース種別(芝/ダ+距離)・出走馬一覧を取得
def fetch_race_card(race_id):
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    race_name_el = soup.select_one(".RaceList_Item02 .RaceName")
    race_title = _text_or_none(race_name_el) or "タイトルなし"

    race_data01 = soup.select_one(".RaceData01")
    race_type = extract_race_type(race_data01.get_text(" ", strip=True)) if race_data01 else None

    entries = []
    for tr in soup.select("tr.HorseList"):
        entry = parse_entry(tr)
        if entry is not None:
            entries.append(entry)

    return race_title, race_type, entries


# 出走馬のデータ(出走情報+過去成績)を取得し、jsonに保存してGCSへアップロードする
# is_final=True の場合、前日確定版として racedata/final/ にも同じ内容を保存する
# (当日朝の差分チェックはこの final 版と当日取得分を比較する)
def get_race_data(race_id, is_final=False):
    race_title, race_type, entries = fetch_race_card(race_id)

    all_horses_results = []
    for entry in entries:
        horse_url = entry["horse_url"]
        horse_results = get_past_results(horse_url) if horse_url else []

        if horse_results:
            matching_times = [
                (result["タイム"], result["開催"], result["馬場"], result["斤量"], result["通過"], result["ペース"])
                for result in horse_results
                if result["距離"] == race_type
            ]
            matched = bool(matching_times)
            if not matching_times:
                sample = horse_results[:3] if len(horse_results) >= 3 else horse_results
                matching_times = [
                    (result["タイム"], result["開催"], result["馬場"], result["斤量"], result["通過"], result["ペース"])
                    for result in sample
                ]
        else:
            matching_times = [("初出走", "初出走", "初出走", "初出走", "初出走", "初出走")]
            matched = False

        all_horses_results.append({
            **entry,
            "results": horse_results,
            "matching_times": matching_times,
            "matched": matched,
        })

    race_card = {
        "race_id": race_id,
        "race_title": race_title,
        "race_type": race_type,
        "generated_at": datetime.now(JST).isoformat(),
        "entries": all_horses_results,
    }

    # 結果をJSONファイルに保存
    output_dir = "racedata"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{race_id}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(race_card, f, ensure_ascii=False, indent=4)

    print(f"結果をJSONファイルに保存しました: {os.path.abspath(output_file)}")

    # GCSへアップロード
    bucket_name = "keibaps-data"
    destination_blob_name = f"racedata/{race_id}.json"
    upload_to_gcs(bucket_name, output_file, destination_blob_name)

    if is_final:
        final_blob_name = f"racedata/final/{race_id}.json"
        upload_to_gcs(bucket_name, output_file, final_blob_name)

    return race_card

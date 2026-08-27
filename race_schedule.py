import json
import os
from datetime import datetime, timedelta, timezone

import re

import requests

from upload_to_gcs import upload_to_gcs

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

JST = timezone(timedelta(hours=9))


# 指定日(YYYYMMDD)に開催される全レースのrace_idを取得する
# netkeibaのレース一覧ページが内部で使っているAjaxエンドポイントを直接叩くため、
# 月間カレンダーの巡回や開催回・日目のパースが不要になる
def get_race_ids_for_date(kaisai_date):
    url = "https://race.netkeiba.com/top/race_list_sub.html"
    params = {"kaisai_date": kaisai_date, "current_group": kaisai_date}
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    race_ids = sorted(set(re.findall(r"race_id=(\d{12})", response.text)))
    return race_ids


# アプリ側が「開催日を選ぶだけ」でその日の全レースを一覧取得できるように、
# 開催日 -> race_id一覧のインデックスをGCSへ保存する
# is_final=True の場合、事前ダウンロード対象となる確定版インデックスにも保存する
def upload_race_index(kaisai_date, race_ids, is_final=False, bucket_name="keibaps-data"):
    index_data = {
        "kaisai_date": kaisai_date,
        "race_ids": race_ids,
        "updated_at": datetime.now(JST).isoformat(),
    }

    output_dir = "raceindex"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{kaisai_date}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=4)

    upload_to_gcs(bucket_name, output_file, f"racedata/index/{kaisai_date}.json")
    if is_final:
        upload_to_gcs(bucket_name, output_file, f"racedata/final/index/{kaisai_date}.json")

    return index_data

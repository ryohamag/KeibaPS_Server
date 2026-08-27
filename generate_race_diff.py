import json
import os
from datetime import datetime, timedelta, timezone

from google.cloud import storage

from upload_to_gcs import upload_to_gcs

JST = timezone(timedelta(hours=9))

# この2項目に変化があった場合だけ「当日変更」として差分に含める
# (取消・騎手変更以外の項目は前日データのままアプリ側に表示させる想定)
WATCHED_FIELDS = ["is_scratched", "scheduled_jockey"]


def _entries_by_key(race_card):
    return {e["horse_url"]: e for e in race_card["entries"] if e.get("horse_url")}


# 前日版(before)と当日版(after)のレースカードを比較し、
# 取消・騎手変更などの差分だけを抽出する
def diff_race_cards(before, after):
    before_entries = _entries_by_key(before)
    after_entries = _entries_by_key(after)

    changes = []
    for horse_url, after_entry in after_entries.items():
        before_entry = before_entries.get(horse_url)
        if before_entry is None:
            continue

        for field in WATCHED_FIELDS:
            before_value = before_entry.get(field)
            after_value = after_entry.get(field)
            if before_value != after_value:
                changes.append({
                    "horse_url": horse_url,
                    "horse_number": after_entry.get("horse_number"),
                    "horse_name": after_entry.get("horse_name"),
                    "field": field,
                    "before": before_value,
                    "after": after_value,
                })

    return changes


def _download_json(bucket_name, blob_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_bytes())


# 前日の確定版(final)と当日朝の最新版を比較し、変更があれば差分JSONを生成してGCSへアップロードする
# 変更がなければ何もアップロードしない
# (アプリ側は差分ファイルが存在しない = 前日から変更なし、と判定できる)
def generate_and_upload_diff(race_id, bucket_name="keibaps-data"):
    final_blob = f"racedata/final/{race_id}.json"
    latest_blob = f"racedata/{race_id}.json"
    diff_blob = f"racediff/{race_id}.json"

    before = _download_json(bucket_name, final_blob)
    after = _download_json(bucket_name, latest_blob)

    if before is None or after is None:
        print(f"比較対象が揃っていないためスキップします: race_id={race_id}")
        return None

    changes = diff_race_cards(before, after)
    if not changes:
        print(f"変更なし: race_id={race_id}")
        return None

    diff_data = {
        "race_id": race_id,
        "checked_at": datetime.now(JST).isoformat(),
        "changes": changes,
    }

    output_dir = "racediff"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{race_id}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(diff_data, f, ensure_ascii=False, indent=4)

    print(f"差分を検出しました({len(changes)}件): {output_file}")
    upload_to_gcs(bucket_name, output_file, diff_blob)
    return diff_data

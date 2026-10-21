import os
import time
from datetime import datetime

import requests

from ranking_logic import RANKINGS

# race_id (YYYY + 競馬場コード2桁 + 開催回2桁 + 開催日目2桁 + レース番号2桁) の競馬場コード
# iOSアプリ側 RacecourseCode.swift と同じ対応
COURSE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}

# 各ランキングで何頭まで表示するか
TOP_N = 3

# 取得失敗のレースIDを要約に載せる最大件数(多いと読みづらいため)
MAX_FAILED_SHOWN = 10

COLOR_OK = 0x2E8B57
COLOR_WARN = 0xE67E22
COLOR_DRAFT = 0x7F8C8D


def _course_name(race_id):
    return COURSE_NAMES.get(race_id[4:6], "不明")


def _race_number(race_id):
    return int(race_id[-2:])


def _date_label(kaisai_date):
    date = datetime.strptime(kaisai_date, "%Y%m%d")
    return f"{date.month}/{date.day}({'月火水木金土日'[date.weekday()]})"


# 取消馬を除いた出走予定馬で、ランキングごとの上位馬を求める
def top_picks(race_card):
    entries = [e for e in race_card["entries"] if not e.get("is_scratched")]
    picks = {}
    for name, rank_fn in RANKINGS.items():
        ranks = rank_fn(entries)
        by_url = {e["horse_url"]: e for e in entries}
        ordered = sorted(ranks, key=ranks.get)[:TOP_N]
        picks[name] = [by_url[url] for url in ordered]
    return picks


def _format_picks(horses):
    return "・".join(f"{h.get('horse_number') or '-'} {h['horse_name']}" for h in horses)


def _race_field(race_card):
    race_id = race_card["race_id"]
    entry_count = sum(1 for e in race_card["entries"] if not e.get("is_scratched"))
    race_type = race_card.get("race_type") or ""
    start_time = race_card.get("start_time")
    start_label = f" {start_time}発走" if start_time else ""
    name = f"{_race_number(race_id)}R{start_label} {race_card['race_title']} {race_type}({entry_count}頭)"
    picks = top_picks(race_card)
    value = "\n".join(f"**{ranking}** {_format_picks(picks[ranking])}" for ranking in RANKINGS)
    return {"name": name[:256], "value": value[:1024], "inline": False}


def build_summary_embed(kaisai_date, race_cards, failed_race_ids, is_final):
    kind = "確定版" if is_final else "下書き"
    description = f"{len(race_cards)}レースを取得しました(失敗 {len(failed_race_ids)}件)"
    if failed_race_ids:
        shown = failed_race_ids[:MAX_FAILED_SHOWN]
        description += "\n失敗したレース: " + ", ".join(shown)
        if len(failed_race_ids) > MAX_FAILED_SHOWN:
            description += f" ほか{len(failed_race_ids) - MAX_FAILED_SHOWN}件"

    if failed_race_ids:
        color = COLOR_WARN
    else:
        color = COLOR_OK if is_final else COLOR_DRAFT

    return {
        "title": f"📥 {_date_label(kaisai_date)} のデータ取得が完了しました({kind})",
        "description": description,
        "color": color,
    }


# 競馬場ごとに1メッセージにまとめる
# (1メッセージ中のembed全体の文字数上限6000字に収めるため、競馬場単位で分ける)
def build_course_embeds(kaisai_date, race_cards):
    by_course = {}
    for race_card in sorted(race_cards, key=lambda c: c["race_id"]):
        by_course.setdefault(_course_name(race_card["race_id"]), []).append(race_card)

    embeds = []
    for course, cards in by_course.items():
        embeds.append({
            "title": f"{_date_label(kaisai_date)} {course} — 各ランキング上位{TOP_N}頭",
            "color": COLOR_OK,
            "fields": [_race_field(card) for card in cards],
        })
    return embeds


def build_payloads(kaisai_date, race_cards, failed_race_ids, is_final=True):
    payloads = [{"embeds": [build_summary_embed(kaisai_date, race_cards, failed_race_ids, is_final)]}]
    for embed in build_course_embeds(kaisai_date, race_cards):
        payloads.append({"embeds": [embed]})
    return payloads


def send_collection_report(kaisai_date, race_cards, failed_race_ids, is_final=True, webhook_url=None):
    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("環境変数 DISCORD_WEBHOOK_URL が設定されていません")

    for payload in build_payloads(kaisai_date, race_cards, failed_race_ids, is_final):
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        # Webhookのレート制限(短時間の連投制限)に引っかからないよう間隔を空ける
        time.sleep(1)

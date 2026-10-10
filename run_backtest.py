import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from backtest import (
    fetch_json,
    is_clean_snapshot,
    list_kaisai_dates,
    list_stored_result_ids,
    load_race_ids_by_date,
    run_backtest,
)
from get_race_result import fetch_race_result, get_race_result
from notify_discord import build_embed, send_embed


def _print_summary(embed):
    print(embed["title"])
    print(embed["description"])
    for field in embed["fields"]:
        print(f"\n{field['name']}")
        print(field["value"].replace("**", ""))


def main():
    parser = argparse.ArgumentParser(
        description="前日確定版の予想ランキングを実際の結果・払戻と突き合わせ、回収率を集計する"
    )
    parser.add_argument(
        "--since",
        metavar="YYYYMMDD",
        help="この開催日以降のレースだけを集計する(省略時は蓄積済みの全期間)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="未取得のレース結果をGCSへ保存せず、メモリ上だけで集計する(ローカル確認用。認証情報が不要)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="集計結果をDiscord Webhook(環境変数 DISCORD_WEBHOOK_URL)へ投稿する",
    )
    args = parser.parse_args()

    kaisai_dates = list_kaisai_dates(since=args.since)
    race_ids_by_date = load_race_ids_by_date(kaisai_dates)
    race_targets = [
        (date, race_id)
        for date, race_ids in race_ids_by_date.items()
        for race_id in race_ids
    ]
    print(f"対象: {len(race_ids_by_date)}開催日 / {len(race_targets)}レース")

    with ThreadPoolExecutor(max_workers=8) as pool:
        snapshots = list(pool.map(lambda t: fetch_json(f"racedata/final/{t[1]}.json"), race_targets))

    # レース結果が混入していないスナップショットだけを検証対象にする
    clean_targets = []
    excluded_snapshots = 0
    for (date, race_id), snapshot in zip(race_targets, snapshots):
        if snapshot is None:
            continue
        if not is_clean_snapshot(snapshot, date):
            excluded_snapshots += 1
            continue
        clean_targets.append((date, race_id, snapshot))

    # 結果が未保存のレースはnetkeibaから取得する(確定前のレースはスキップ)
    stored_ids = list_stored_result_ids()
    fetched_results = {}
    for _, race_id, _ in clean_targets:
        if race_id in stored_ids:
            continue
        try:
            fetch = fetch_race_result if args.no_upload else get_race_result
            result = fetch(race_id)
        except Exception as e:
            print(f"結果の取得に失敗しました race_id={race_id}: {e}")
            continue
        if result is not None:
            fetched_results[race_id] = result
        time.sleep(1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        stored_results = dict(zip(
            [r for _, r, _ in clean_targets if r in stored_ids],
            pool.map(
                lambda race_id: fetch_json(f"raceresult/{race_id}.json"),
                [r for _, r, _ in clean_targets if r in stored_ids],
            ),
        ))

    results = {**stored_results, **fetched_results}
    records = [
        {"kaisai_date": date, "snapshot": snapshot, "result": results[race_id]}
        for date, race_id, snapshot in clean_targets
        if results.get(race_id)
    ]
    if not records:
        print("検証できるレースがありません")
        return

    summary = run_backtest(records)
    dates = sorted({r["kaisai_date"] for r in records})
    meta = {
        "first_date": f"{dates[0][:4]}/{dates[0][4:6]}/{dates[0][6:]}",
        "last_date": f"{dates[-1][:4]}/{dates[-1][4:6]}/{dates[-1][6:]}",
        "date_count": len(dates),
        "excluded_snapshots": excluded_snapshots,
    }
    embed = build_embed(summary, meta)
    _print_summary(embed)

    if args.notify:
        send_embed(embed)
        print("Discordへ投稿しました")


if __name__ == "__main__":
    main()

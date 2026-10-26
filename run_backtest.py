import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from backtest import (
    fetch_json,
    is_clean_snapshot,
    list_kaisai_dates,
    list_stored_result_ids,
    load_race_ids_by_date,
    records_before_latest_week,
    run_backtest,
)
from get_race_result import fetch_race_result, get_race_result
from notify_discord import build_embed, send_embed, send_images


def _format_date(kaisai_date):
    return f"{kaisai_date[:4]}/{kaisai_date[4:6]}/{kaisai_date[6:]}"


def _print_summary(embed):
    print(embed["title"])
    print(embed["description"])
    for field in embed["fields"]:
        print(f"\n{field['name']}")
        print(field["value"].replace("**", ""))


# 検証対象のレース(前日確定版のスナップショット+結果)を読み込む
# 戻り値: (開催日順に並んだ records, 結果混入で除外したレース数)
def load_records(since=None, upload=True):
    kaisai_dates = list_kaisai_dates(since=since)
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
            fetch = get_race_result if upload else fetch_race_result
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
    return records, excluded_snapshots


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
    parser.add_argument(
        "--chart",
        action="store_true",
        help="累計回収率の推移グラフを必ず付ける(省略時は、月が変わって最初の通知のときだけ付ける)",
    )
    args = parser.parse_args()

    records, excluded_snapshots = load_records(since=args.since, upload=not args.no_upload)
    if not records:
        print("検証できるレースがありません")
        return

    summary = run_backtest(records)
    dates = sorted({r["kaisai_date"] for r in records})

    # 先週の通知時点の累計(=最新の開催週を除いた集計)。前週比の表示に使う
    previous_records = records_before_latest_week(records)
    previous_summary = run_backtest(previous_records) if previous_records else None
    previous_last_date = max(r["kaisai_date"] for r in previous_records) if previous_records else None

    meta = {
        "first_date": _format_date(dates[0]),
        "last_date": _format_date(dates[-1]),
        "date_count": len(dates),
        "excluded_snapshots": excluded_snapshots,
        "previous_last_date": _format_date(previous_last_date) if previous_last_date else None,
    }
    embed = build_embed(summary, meta)
    _print_summary(embed)

    # 月に1回(最新の開催日の月が、先週分の最新開催日の月と変わったとき)推移グラフを付ける
    # 実行日ではなくデータで判定するので、cronの遅延で日付がずれても送り漏れ・二重送信がない
    is_new_month = previous_last_date is None or previous_last_date[:6] != dates[-1][:6]
    trend_png = None
    if args.chart or is_new_month:
        try:
            from report_chart import render_trend_chart
            trend_png = render_trend_chart(records, meta)
            print("推移グラフを作成しました")
        except Exception as e:
            print(f"推移グラフの作成に失敗しました: {e}")

    if args.notify:
        try:
            send_images(summary, meta, previous_summary=previous_summary, trend_png=trend_png)
            print("Discordへ画像で投稿しました")
        except Exception as e:
            print(f"画像での投稿に失敗したため、テキストで投稿します: {e}")
            send_embed(embed)
            print("Discordへテキストで投稿しました")


if __name__ == "__main__":
    main()

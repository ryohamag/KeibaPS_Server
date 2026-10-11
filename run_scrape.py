import argparse
import time
from datetime import datetime, timedelta, timezone

from generate_race_diff import generate_and_upload_diff
from get_race_data import get_race_data
from notify_picks import send_collection_report
from race_schedule import get_race_ids_for_date, upload_race_index

JST = timezone(timedelta(hours=9))


# --target の指定から、対象となる開催日(YYYYMMDD)のリストを求める
#
# GitHub Actionsのscheduled workflowは実行時刻が数時間単位で遅延することがあり、
# 遅延が深夜0時をまたぐと「今日」「明日」のような相対日付は指す日がズレてしまう
# (例: 金曜21:00の予定が土曜7:00にずれ込むと、「明日」が土曜ではなく日曜になる)。
# これを避けるため、実行時刻に関わらず常に同じ日を指す「直近の土曜/日曜」という
# 絶対計算に統一している。実行が多少遅れても対象日はブレない。
#
# 「直近の土曜」は、月〜土曜なら今日を含む次の土曜、日曜なら昨日の土曜とする。
# 日曜に実行された場合に「来週の土曜」を指してしまうと、土曜夜21:00のジョブが
# 遅延して日曜0時をまたいだとき、1週間先の開催日を対象にしてしまう
# (日曜朝7:00の差分チェックも同様に来週を指していた)。
#
# saturday: 直近の土曜
# sunday: 直近の土曜の翌日(=直近の日曜)
# weekend: 上記2日分
# monday: 直近(今日を含む)の月曜。祝日開催の月曜用。日曜夜に実行すると翌日が対象になる
def resolve_target_dates(target):
    now = datetime.now(JST)

    if target == "monday":
        days_until_mon = (0 - now.weekday()) % 7
        return [(now + timedelta(days=days_until_mon)).strftime("%Y%m%d")]

    if now.weekday() == 6:
        saturday = now - timedelta(days=1)
    else:
        saturday = now + timedelta(days=(5 - now.weekday()) % 7)
    sunday = saturday + timedelta(days=1)

    if target == "saturday":
        return [saturday.strftime("%Y%m%d")]

    if target == "sunday":
        return [sunday.strftime("%Y%m%d")]

    if target == "weekend":
        return [saturday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d")]

    raise ValueError(f"unknown target: {target}")


def main():
    parser = argparse.ArgumentParser(description="netkeibaから出馬表データを取得しGCSへ保存する")
    parser.add_argument(
        "--target",
        choices=["saturday", "sunday", "weekend", "monday"],
        help="saturday=直近の土曜 / sunday=直近の日曜 / weekend=直近の土日2日分 / monday=直近の月曜(祝日開催用)",
    )
    parser.add_argument(
        "--date",
        metavar="YYYYMMDD",
        help="対象日を直接指定する(--targetの代わりに使う。動作確認や過去データの再取得用)",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="前日確定版として racedata/final/ にも保存する(事前ダウンロード対象になる版)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="取得後、final版との差分を計算してGCSへアップロードする(当日朝ジョブ用)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="取得完了後、結果の要約と各レースの予想上位をDiscord(環境変数 DISCORD_WEBHOOK_URL)へ投稿する",
    )
    args = parser.parse_args()

    if not args.target and not args.date:
        parser.error("--target または --date のいずれかを指定してください")

    target_dates = [args.date] if args.date else resolve_target_dates(args.target)
    print(f"対象日: {target_dates}")

    for kaisai_date in target_dates:
        race_ids = get_race_ids_for_date(kaisai_date)
        print(f"{kaisai_date}: {len(race_ids)}レース")
        # 開催がない日や、レース一覧がまだ公開されていない日に、空のインデックスで
        # 既存のデータを上書きしてしまわないよう、何も保存せずスキップする
        if not race_ids:
            print(f"{kaisai_date}はレースがないためスキップします")
            continue
        upload_race_index(kaisai_date, race_ids, is_final=args.final)

        race_cards = []
        failed_race_ids = []
        for race_id in race_ids:
            try:
                race_cards.append(get_race_data(race_id, is_final=args.final))
            except Exception as e:
                print(f"取得に失敗しました race_id={race_id}: {e}")
                failed_race_ids.append(race_id)
                continue

            if args.diff:
                try:
                    generate_and_upload_diff(race_id)
                except Exception as e:
                    print(f"差分生成に失敗しました race_id={race_id}: {e}")

            # netkeibaへの連続アクセスを避けるための待機
            time.sleep(1)

        if args.notify:
            # 通知の失敗でスクレイプ自体を失敗扱いにしない(データは保存済みのため)
            try:
                send_collection_report(kaisai_date, race_cards, failed_race_ids, is_final=args.final)
            except Exception as e:
                print(f"Discordへの通知に失敗しました: {e}")


if __name__ == "__main__":
    main()

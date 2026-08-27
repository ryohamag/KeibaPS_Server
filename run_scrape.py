import argparse
import time
from datetime import datetime, timedelta, timezone

from generate_race_diff import generate_and_upload_diff
from get_race_data import get_race_data
from race_schedule import get_race_ids_for_date

JST = timezone(timedelta(hours=9))


# --target の指定から、対象となる開催日(YYYYMMDD)のリストを求める
# weekend: 直近(今日を含む)の土曜・日曜の2日分
# tomorrow: 明日の1日分
# today: 今日の1日分
def resolve_target_dates(target):
    now = datetime.now(JST)

    if target == "today":
        return [now.strftime("%Y%m%d")]

    if target == "tomorrow":
        return [(now + timedelta(days=1)).strftime("%Y%m%d")]

    if target == "day_after_tomorrow":
        return [(now + timedelta(days=2)).strftime("%Y%m%d")]

    if target == "weekend":
        days_until_sat = (5 - now.weekday()) % 7
        saturday = now + timedelta(days=days_until_sat)
        sunday = saturday + timedelta(days=1)
        return [saturday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d")]

    raise ValueError(f"unknown target: {target}")


def main():
    parser = argparse.ArgumentParser(description="netkeibaから出馬表データを取得しGCSへ保存する")
    parser.add_argument(
        "--target",
        choices=["today", "tomorrow", "day_after_tomorrow", "weekend"],
        required=True,
        help="today=当日 / tomorrow=翌日 / day_after_tomorrow=翌々日 / weekend=直近の土日2日分",
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
    args = parser.parse_args()

    target_dates = resolve_target_dates(args.target)
    print(f"対象日: {target_dates}")

    for kaisai_date in target_dates:
        race_ids = get_race_ids_for_date(kaisai_date)
        print(f"{kaisai_date}: {len(race_ids)}レース")

        for race_id in race_ids:
            try:
                get_race_data(race_id, is_final=args.final)
            except Exception as e:
                print(f"取得に失敗しました race_id={race_id}: {e}")
                continue

            if args.diff:
                try:
                    generate_and_upload_diff(race_id)
                except Exception as e:
                    print(f"差分生成に失敗しました race_id={race_id}: {e}")

            # netkeibaへの連続アクセスを避けるための待機
            time.sleep(1)


if __name__ == "__main__":
    main()

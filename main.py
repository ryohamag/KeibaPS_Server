import schedule
import time
import threading
from get_race_schedule import job
from get_race_json import get_race_json
from datetime import datetime

# # スケジュール設定
# schedule.every().monday.at("12:13").do(job) # 開催スケジュールの取得
# schedule.every().friday.at("18:00").do(get_race_json)
# schedule.every().saturday.at("18:00").do(get_race_json)
# schedule.every().sunday.at("18:00").do(get_race_json)

# def run_scheduler():
#     while True:
#         schedule.run_pending()
#         time.sleep(1)

if __name__ == "__main__":
    job()  # 初回実行
    # run_scheduler()

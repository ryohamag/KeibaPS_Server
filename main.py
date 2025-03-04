import schedule
import time
import threading
from get_race_schedule import get_race_schedule
from get_race_json import get_race_json

# スケジュール設定
schedule.every().wednesday.at("13:00").do(get_race_schedule)
schedule.every().friday.at("18:00").do(get_race_json)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# スケジューラーを別スレッドで実行
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# メインスレッドを保持
scheduler_thread.join()

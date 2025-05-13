import schedule
import time
import threading
from get_race_schedule import job
from get_race_json import get_race_json
from datetime import datetime

# スケジュール設定(UTC)
# schedule.every().wednesday.at("09:00").do(job)
schedule.every().tuesday.at("06:22").do(job)
schedule.every().friday.at("14:00").do(get_race_json)
schedule.every().saturday.at("09:00").do(get_race_json)
schedule.every().sunday.at("09:00").do(get_race_json)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_scheduler()

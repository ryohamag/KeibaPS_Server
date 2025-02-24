from selenium import webdriver
from get_race_data import get_race_data
from datetime import datetime
import schedule
import time

def job():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # ヘッドレスモードを有効にする
    options.add_argument('--disable-gpu')  # GPUを無効にする（ヘッドレスモードでのレンダリングを改善）
    options.add_argument('--window-size=1920x1080')  # ウィンドウサイズを設定
    options.add_argument('--ignore-certificate-errors')  # 証明書の検証を無効にする

    driver = webdriver.Chrome(options=options)

    #現在の日付と時刻を取得
    now = datetime.now()

    #年を取得
    year = now.year

    #明日の日付を取得
    tomorrow = now + timedelta(days=1)
    tomorrow_date = tomorrow.strftime("%d")

    #明後日の日付を取得
    day_after_tomorrow = now + timedelta(days=2)
    day_after_tomorrow_date = day_after_tomorrow.strftime("%d")
    
    # 第6引数を01から12までループさせる
    for race_num in range(3, 4):
        race_num_str = f"{race_num:02d}"  # 01, 02, ..., 12 の形式に変換
        get_race_data(driver, "2025", "京都", "01", "06", race_num_str)

    driver.quit()

# 毎週金曜日の18:00にjob関数を実行するスケジュールを設定
schedule.every().friday.at("18:00").do(job)

while True:
    schedule.run_pending()
    time.sleep(1)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from get_race_data import get_race_data
from datetime import datetime, timedelta
import time
import json
import os

def get_race_json():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # ヘッドレスモードを有効にする
    options.add_argument('--disable-gpu')  # GPUを無効にする（ヘッドレスモードでのレンダリングを改善）
    options.add_argument('--window-size=1920x1080')  # ウィンドウサイズを設定
    options.add_argument('--ignore-certificate-errors')  # 証明書の検証を無効にする

    driver = webdriver.Chrome(executable_path='/usr/bin/chromedriver', options=options)

    #現在の日付と時刻を取得
    now = datetime.now()

    #年を取得
    year = now.year

    #月を取得
    month = now.month

    #明日の日付を取得
    tomorrow = now + timedelta(days=1)
    tomorrow_date = tomorrow.strftime("%d")

    #明後日の日付を取得
    day_after_tomorrow = now + timedelta(days=2)
    day_after_tomorrow_date = day_after_tomorrow.strftime("%d")

    #明々後日の日付を取得
    three_days_later = now + timedelta(days=3)
    three_days_later_date = three_days_later.strftime("%d")

    #スクリプトのディレクトリを取得
    script_dir = os.path.dirname(__file__)

    #JSONファイルの相対パス
    relative_path = f"raceschedule/{year}{month:02d}.json"

    #JSONファイルの絶対パスを取得
    json_file_path = os.path.join(script_dir, relative_path)

    #JSONファイルを読み込む
    with open(json_file_path, "r", encoding="utf-8") as f:
        race_data = json.load(f)

    #指定した年月日
    target_date1 = f"{year}{month:02d}{tomorrow_date}"

    #指定した年月日のrace_titlesを取得
    race_titles1 = []
    for entry in race_data:
        if entry["date"] == target_date1:
            race_titles1 = entry["race_titles"]
            break
    
    #翌日分のデータを取得
    for title in race_titles1:
        parts = title.split()
        if len(parts) == 3:
            times, course, day = parts
            times = times.replace("回", "").zfill(2)
            day = day.replace("日目", "").zfill(2)
            for race_num in range(1, 13):
                race_num_str = f"{race_num:02d}"  # 01, 02, ..., 12 の形式に変換
                get_race_data(driver, year, course, times, day, race_num_str)

    target_date2 = f"{year}{month:02d}{day_after_tomorrow_date}"

    #指定した年月日のrace_titlesを取得
    race_titles2 = []
    for entry in race_data:
        if entry["date"] == target_date2:
            race_titles2 = entry["race_titles"]
            break

    #明後日分のデータを取得
    for title in race_titles2:
        parts = title.split()
        if len(parts) == 3:
            times, course, day = parts
            times = times.replace("回", "").zfill(2)
            day = day.replace("日目", "").zfill(2)
            for race_num in range(1, 13):
                race_num_str = f"{race_num:02d}"  # 01, 02, ..., 12 の形式に変換
                get_race_data(driver, year, course, times, day, race_num_str)

    target_date3 = f"{year}{month:02d}{three_days_later_date}"

    race_titles3 = []
    for entry in race_data:
        if entry["date"] == target_date3:
            race_titles3 = entry["race_titles"]
            break

    #明々後日分のデータを取得
    if race_titles3:
        for title in race_titles3:
            parts = title.split()
            if len(parts) == 3:
                times, course, day = parts
                times = times.replace("回", "").zfill(2)
                day = day.replace("日目", "").zfill(2)
                for race_num in range(1, 13):
                    race_num_str = f"{race_num:02d}"  # 01, 02, ..., 12 の形式に変換
                    get_race_data(driver, year, course, times, day, race_num_str)
    

    driver.quit()
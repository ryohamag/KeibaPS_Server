from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from urllib import parse
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import schedule
import time

def parse_url(url, search_s):
    """URLから指定されたクエリパラメータを抽出"""
    parsed_url = parse.urlparse(url)
    params = parse.parse_qs(parsed_url.query)
    return params.get(search_s, [None])[0]

def get_race_schedule(driver, year, month):
    """指定された年月の開催日と開催コースを取得"""
    url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"  # 実際のURLに置き換え
    driver.get(url)

    all_race_data = []

    # ページの読み込みが完了するのを待つ
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceCellBox"))
    )

    # 各日に対して開催日とコースを取得
    race_cells = driver.find_elements(By.CLASS_NAME, "RaceCellBox")
    print(f"Found {len(race_cells)} race cells")  # デバッグ用出力

    for i in range(len(race_cells)):
        try:
            # ページの読み込みが完了するのを待つ
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceCellBox"))
            )

            # 各レースセルを再取得
            race_cells = driver.find_elements(By.CLASS_NAME, "RaceCellBox")
            race_cell = race_cells[i]

            # <a>タグが存在するか確認
            a_tag = race_cell.find_element(By.TAG_NAME, "a")
            if a_tag:
                # リンクのURLから開催日を取得
                kaisai_url = a_tag.get_attribute("href")
                kaisai_date = parse_url(kaisai_url, "kaisai_date")
                print(f"Kaisai date: {kaisai_date}")  # デバッグ用出力

                # 開催コース名を取得
                race_kai_box = race_cell.find_element(By.CLASS_NAME, "RaceKaisaiBox")
                course_elements = race_kai_box.find_elements(By.CLASS_NAME, "JyoName")
                courses = [course.text for course in course_elements if course.text]
                print(f"Courses: {courses}")  # デバッグ用出力

                # レース情報を取得
                driver.get(kaisai_url)
                
                # 明示的な待機を使用して、レースタイトルが読み込まれるのを待つ
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceList_DataTitle"))
                )
                
                race_info_elements = driver.find_elements(By.CLASS_NAME, "RaceList_DataTitle")

                # レースタイトルをリストとして格納
                race_titles = [race_info.text for race_info in race_info_elements]
                print(f"Race titles: {race_titles}")  # デバッグ用出力

                # 開催日、コース、レースタイトルを追加
                all_race_data.append({
                    "date": kaisai_date,
                    "courses": courses,
                    "race_titles": race_titles,
                })

                # 元のカレンダーページに戻る
                driver.get(url)
                
        except Exception as e:
            print(f"開催日ではありません")
            continue

    return all_race_data

def job():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # ヘッドレスモードを有効にする
    options.add_argument('--disable-gpu')  # GPUを無効にする（ヘッドレスモードでのレンダリングを改善）
    options.add_argument('--window-size=1920x1080')  # ウィンドウサイズを設定
    options.add_argument('--ignore-certificate-errors')  # 証明書の検証を無効にする

    driver = webdriver.Chrome(executable_path='/usr/bin/chromedriver', options=options)

    try:
        # 翌月の年と月を取得
        now = datetime.now()
        next_month = now + relativedelta(months=1)
        year = next_month.year
        month = next_month.month

        # 週末の日付を計算
        weekend = now + timedelta(days=(5 - now.weekday()) % 7)
        weekend_month = weekend.month

        # 週末が同一月か翌月かを判定
        if weekend_month == now.month:
            race_data = get_race_schedule(driver, now.year, now.month)
            # 結果をJSONファイルに保存
            output_dir = "raceschedule"
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{year}{now.month:02}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(race_data, f, ensure_ascii=False, indent=4)
            print(f"結果をJSONファイルに保存しました: {output_file}")
        else:
            race_data = get_race_schedule(driver, next_month.year, next_month.month)
            # 結果をJSONファイルに保存
            output_dir = "raceschedule"
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{year}{next_month.month:02}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(race_data, f, ensure_ascii=False, indent=4)
            print(f"結果をJSONファイルに保存しました: {output_file}")
    
    finally:
        driver.quit()
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib import parse
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import schedule
import time
from google.cloud import storage
from upload_to_gcs import upload_to_gcs
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


def parse_url(url, search_s):
    """URLから指定されたクエリパラメータを抽出"""
    parsed_url = parse.urlparse(url)
    params = parse.parse_qs(parsed_url.query)
    return params.get(search_s, [None])[0]

def safe_driver_get(driver, url, max_retries=3, wait=10):
    """driver.get() を安全に実行し、失敗時にリトライ"""
    for attempt in range(max_retries):
        try:
            print(f"Trying to load URL (attempt {attempt + 1}): {url}")
            driver.get(url)
            return True
        except (TimeoutException, WebDriverException) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(wait)
    print(f"Failed to load URL after {max_retries} attempts.")
    return False

def get_race_schedule(driver, year, month):
    print("start scraping")
    url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"
    print(f"URL: {url}")
    
    # まずトップページを開いて（必要なら）
    if not safe_driver_get(driver, "https://race.netkeiba.com"):
        print("ネットケイバにアクセスできませんでした")
        return []

    print("proxy web")
    time.sleep(40)

    # メインURLへ移動
    if not safe_driver_get(driver, url):
        print("カレンダーURLにアクセスできませんでした")
        return []

    time.sleep(5)
    print("nyaaa")

    all_race_data = []

    # ページの読み込みが完了するのを待つ
    try:
        print("ページの読み込みをstart...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceCellBox"))
        )
    except:
        print("ページの読み込みに失敗しました")
        return []
    # ページのタイトルを取得


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
    # options = webdriver.ChromeOptions()
    # # options.add_argument('--headless')  # ヘッドレスモードを有効にする
    # options.add_argument('--disable-gpu')  # GPUを無効にする（ヘッドレスモードでのレンダリングを改善）
    # options.add_argument('--window-size=1920x1080')  # ウィンドウサイズを設定
    # # options.add_argument('--ignore-certificate-errors')  # 証明書の検証を無効にする
    # options.binary_location = "/usr/bin/google-chrome"
    # # chrome_driver_path = "/usr/local/bin/chromedriver"

    # # service = Service(chrome_driver_path)

    # print("kidou")

    # driver = webdriver.Chrome(options=options)

    options = Options()
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")   
    options.binary_location = "/usr/bin/google-chrome"
    driver = webdriver.Chrome(options=options)
    # url = f"https://race.netkeiba.com/top/calendar.html?year=2025&month=4"  
    # driver.get(url)
    # driver.get("https://race.netkeiba.com/top/calendar.html?year=2024&month=12")
    # driver.get("https://race.netkeiba.com")
    # wait = WebDriverWait(driver, 10)  # 最大10秒間待機
    # print(driver.title)
    # for entry in driver.get_log('browser'):
    #     print(entry)


    # try:
    #     driver.get("https://www.google.com")
    #     print(driver.title)
    # except Exception as e:
    #     print("Error:", e)


    try:
        # 翌月の年と月を取得
        now = datetime.now()
        next_month = now + relativedelta(months=1)
        year = next_month.year
        month = next_month.month
        print(f"year: {year}, month: {month}")  # デバッグ用出力


        # 週末の日付を計算
        weekend = now + timedelta(days=(5 - now.weekday()) % 7)
        weekend_month = weekend.month

        # 週末が同一月か翌月かを判定
        if weekend_month == now.month:
            print("同一月の週末です")
            race_data = get_race_schedule(driver, now.year, now.month)
            # 結果をJSONファイルに保存
            output_dir = "raceschedule"
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{year}{now.month:02}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(race_data, f, ensure_ascii=False, indent=4)
            print(f"結果をJSONファイルに保存しました: {output_file}")
            # GCSへアップロード
            bucket_name = "keibaps-data"  # GCSバケット名をここに
            destination_blob_name = f"raceschedule/{year}{now.month:02}.json"
            upload_to_gcs(bucket_name, output_file, destination_blob_name)

        else:
            print("翌月の週末です")
            race_data = get_race_schedule(driver, next_month.year, next_month.month)
            # 結果をJSONファイルに保存
            output_dir = "raceschedule"
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{year}{next_month.month:02}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(race_data, f, ensure_ascii=False, indent=4)
            print(f"結果をJSONファイルに保存しました: {output_file}")
            # GCSへアップロード
            bucket_name = "keibaps-data"  # GCSバケット名をここに
            destination_blob_name = f"raceschedule/{year}{now.month:02}.json"
            upload_to_gcs(bucket_name, output_file, destination_blob_name)
    finally:
        driver.quit()

if __name__ == "__main__":
    job()  # 初回実行
#     # run_scheduler()
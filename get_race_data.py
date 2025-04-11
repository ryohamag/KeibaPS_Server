import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import os
from get_past_results import get_past_results
from google.cloud import storage
from upload_to_gcs import upload_to_gcs

#レース種別を取得
def extract_race_type(race_type):
    match = re.match(r"^(芝|ダ)\d+", race_type)
    return match.group(0) if match else race_type

def get_race_type(driver, url):
    try:
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceData01"))
        )
        race_data = driver.find_element(By.CLASS_NAME, "RaceData01").text
        for part in race_data.split("/"):
            part = part.strip()
            match = re.search(r"(芝|ダ)\d+", part)
            if match:
                race_type = match.group(0)
                print(race_type)
                return race_type
    except Exception as e:
        print(f"Error: {e}")
        return None

#出走馬のデータを取得し、jsonに保存する
def get_race_data(driver, year, course, round, date, race_num):
    course_dict = {
        "札幌": "01",
        "函館": "02",
        "福島": "03",
        "新潟": "04",
        "東京": "05",
        "中山": "06",
        "中京": "07",
        "京都": "08",
        "阪神": "09",
        "小倉": "10"
    }

    course_num = course_dict.get(course, "00")

    #出馬表ページのURL
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={year}{course_num}{round}{date}{race_num}"

    #データ格納用リスト
    all_horses_results = []

    #出馬表ページを開き、馬のリンクを取得

    race_type = get_race_type(driver, url)
    try:
        driver.get(url)
        WebDriverWait(driver, 60).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".HorseName a"))
        )
        horse_links = driver.find_elements(By.CSS_SELECTOR, ".HorseName a")

        WebDriverWait(driver, 60).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceList_Item02"))
        )
        race_title_element = driver.find_element(By.CLASS_NAME, "RaceList_Item02")
        race_title = race_title_element.find_element(By.CLASS_NAME, "RaceName").text if race_title_element else "タイトルなし"

        for link in horse_links:
            horse_url = link.get_attribute("href")
            horse_name = link.get_attribute("title")
            horse_results = get_past_results(horse_url)
            if horse_results:
                #race_typeに合致するレースのタイムを抽出
                matching_times = [(result["タイム"], result["開催"], result["馬場"], result["斤量"], result["通過"], result["ペース"]) for result in horse_results if result["距離"] == race_type]
                matched = bool(matching_times)
                if not matching_times:
                    if len(horse_results) >= 3:
                        matching_times = [(result["タイム"], result["開催"], result["馬場"], result["斤量"], result["通過"], result["ペース"]) for result in horse_results[:3]]
                    else:
                        matching_times = [(result["タイム"], result["開催"], result["馬場"], result["斤量"], result["通過"], result["ペース"]) for result in horse_results]
                all_horses_results.append({
                    "horse_url": horse_url,
                    "horse_name": horse_name,
                    "race_title": race_title,
                    "race_type": race_type,
                    "results": horse_results,
                    "matching_times": matching_times,
                    "matched": matched
                })
            else:
                matching_times = [("初出走", "初出走", "初出走", "初出走", "初出走", "初出走")]
                all_horses_results.append({
                    "horse_url": horse_url,
                    "horse_name": horse_name,
                    "results": [],
                    "matching_times": matching_times,
                    "matched": False
                })

    finally:
        pass

    #結果をJSONファイルに保存
    output_dir = "racedata"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{year}{course_num}{round}{date}{race_num}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_horses_results, f, ensure_ascii=False, indent=4)

    print(f"結果をJSONファイルに保存しました: {os.path.abspath(output_file)}")
    # GCSへアップロード
    bucket_name = "keibaps-data"  # GCSバケット名をここに
    destination_blob_name = f"racedata/{year}{course_num}{round}{date}{race_num}.json"
    upload_to_gcs(bucket_name, output_file, destination_blob_name)

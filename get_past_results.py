from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

#出走馬の過去の競争成績を取得
def get_past_results(horseUrl):
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # ヘッドレスモードを有効にする
    options.add_argument('--disable-gpu')  # GPUを無効にする（ヘッドレスモードでのレンダリングを改善）
    options.add_argument('--window-size=1920x1080')  # ウィンドウサイズを設定
    options.add_argument('--ignore-certificate-errors')  # 証明書の検証を無効にする

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(horseUrl)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "db_h_race_results"))
        )

        rows = driver.find_elements(By.CSS_SELECTOR, "table.db_h_race_results tr")
        race_data = []

        for row in rows[1:]:
            cols = row.find_elements(By.TAG_NAME, "td")
            cols_text = [col.text.strip().replace('\u3000', ' ') for col in cols]

            if len(cols_text) >= 23:
                race_data.append({
                    "日付": cols_text[0] if cols_text[0] else None,
                    "開催": cols_text[1] if cols_text[1] else None,
                    "天気": cols_text[2] if cols_text[2] else None,
                    "R": cols_text[3] if cols_text[3] else None,
                    "レース名": cols_text[4] if cols_text[4] else None,
                    "頭数": cols_text[6] if cols_text[6] else None,
                    "枠番": cols_text[7] if cols_text[7] else None,
                    "馬番": cols_text[8] if cols_text[8] else None,
                    "オッズ": cols_text[9] if cols_text[9] else None,
                    "人気": cols_text[10] if cols_text[10] else None,
                    "着順": cols_text[11] if cols_text[11] else None,
                    "騎手": cols_text[12] if cols_text[12] else None,
                    "斤量": cols_text[13] if cols_text[13] else None,
                    "距離": cols_text[14] if cols_text[14] else None,
                    "馬場": cols_text[15] if cols_text[15] else None,
                    "タイム": cols_text[17] if cols_text[17] else None,
                    "着差": cols_text[18] if cols_text[18] else None,
                    "通過": cols_text[20] if cols_text[20] else None,
                    "ペース": cols_text[21] if cols_text[21] else None,
                    "上がり": cols_text[22] if cols_text[22] else None,
                    "馬体重": cols_text[23] if cols_text[23] else None,
                })

        return race_data

    except Exception as e:
        print(f"エラーが発生しました (URL: {horseUrl}): {e}")
        return []

    finally:
        pass

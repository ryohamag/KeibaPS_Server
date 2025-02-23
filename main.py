from selenium import webdriver
from get_race_data import get_race_data

options = webdriver.ChromeOptions()
options.add_argument('--headless')  # ヘッドレスモードを有効にする
options.add_argument('--disable-gpu')  # GPUを無効にする（ヘッドレスモードでのレンダリングを改善）
options.add_argument('--window-size=1920x1080')  # ウィンドウサイズを設定
options.add_argument('--ignore-certificate-errors')  # 証明書の検証を無効にする

driver = webdriver.Chrome(options=options)
#第6引数を01から12までループさせる
for race_num in range(3, 4):
    race_num_str = f"{race_num:02d}"  # 01, 02, ..., 12 の形式に変換
    get_race_data(driver, "2025", "京都", "01", "06", race_num_str)

driver.quit()
# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.
# keiba_scraper/spiders/race_calendar_spider.py

# import scrapy
# from urllib import parse
# from keiba_scraper.items import RaceScheduleItem

# class RaceCalendarSpider(scrapy.Spider):
#     name = "race_calendar"
#     allowed_domains = ["race.netkeiba.com"]

#     def __init__(self, year=None, month=None, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.year = year
#         self.month = month
#         self.base_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"

#     def start_requests(self):
#         yield scrapy.Request(
#             url=self.base_url,
#             callback=self.parse_calendar,
#             headers={
#                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
#             }
#         )

#     def parse_calendar(self, response):
#         cells = response.css(".RaceCellBox")
#         for cell in cells:
#             link = cell.css("a::attr(href)").get()
#             if not link:
#                 continue

#             kaisai_date = self.extract_query_param(link, "kaisai_date")
#             courses = cell.css(".JyoName::text").getall()
#             full_url = response.urljoin(link)

#             yield scrapy.Request(
#                 url=full_url,
#                 callback=self.parse_race_detail,
#                 cb_kwargs={"kaisai_date": kaisai_date, "courses": courses}
#             )

#     def parse_race_detail(self, response, kaisai_date, courses):
#         titles = response.css(".RaceList_DataTitle::text").getall()

#         yield RaceScheduleItem(
#             date=kaisai_date,
#             courses=courses,
#             race_titles=[title.strip() for title in titles if title.strip()]
#         )

#     def extract_query_param(self, url, key):
#         parsed = parse.urlparse(url)
#         params = parse.parse_qs(parsed.query)
#         return params.get(key, [None])[0]


import scrapy
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrapy.http import HtmlResponse
from selenium.webdriver.chrome.options import Options
import time

class RaceCalendarSpider(scrapy.Spider):
    name = "race_calendar"
    allowed_domains = ["race.netkeiba.com"]

    def __init__(self, year=None, month=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.year = year
        self.month = month
        self.base_url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"

        # Seleniumの設定
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # ヘッドレスモード
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        self.driver = webdriver.Chrome(options=chrome_options)

    def start_requests(self):
        yield scrapy.Request(
            url=self.base_url,
            callback=self.parse_calendar,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            }
        )

    def parse_calendar(self, response):
        cells = response.css(".RaceCellBox")
        for cell in cells:
            link = cell.css("a::attr(href)").get()
            if not link:
                continue

            kaisai_date = self.extract_query_param(link, "kaisai_date")
            courses = cell.css(".JyoName::text").getall()
            full_url = response.urljoin(link)

            yield scrapy.Request(
                url=full_url,
                callback=self.parse_race_detail,
                cb_kwargs={"kaisai_date": kaisai_date, "courses": courses}
            )

    def parse_race_detail(self, response, kaisai_date, courses):
        # Seleniumで詳細ページを開く
        self.driver.get(response.url)

        # 明示的な待機を使用して要素が読み込まれるのを待つ
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "RaceList_DataTitle"))
        )

        # RaceList_DataTitle内のすべてのテキストを取得
        race_info_elements = self.driver.find_elements(By.CLASS_NAME, "RaceList_DataTitle")
        race_titles_list = [elem.text.strip() for elem in race_info_elements if elem.text.strip()]

        # レースタイトルをカンマ区切りで結合し、リスト形式にする
        race_titles = [", ".join(race_titles_list)]  # カンマ区切りの文字列をリストに格納

        # デバッグ用出力
        print(f"Race Titles: {race_titles}")
        self.logger.info(f"Race Titles: {race_titles}")

        # アイテムを生成
        yield {
            "date": kaisai_date,
            "courses": courses,
            "race_titles": race_titles,  # リスト形式で保存
        }

    def extract_query_param(self, url, key):
        from urllib import parse
        parsed = parse.urlparse(url)
        params = parse.parse_qs(parsed.query)
        return params.get(key, [None])[0]

    def closed(self, reason):
        # Seleniumのドライバを終了
        self.driver.quit()

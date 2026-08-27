import re

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}


# 指定日(YYYYMMDD)に開催される全レースのrace_idを取得する
# netkeibaのレース一覧ページが内部で使っているAjaxエンドポイントを直接叩くため、
# 月間カレンダーの巡回や開催回・日目のパースが不要になる
def get_race_ids_for_date(kaisai_date):
    url = "https://race.netkeiba.com/top/race_list_sub.html"
    params = {"kaisai_date": kaisai_date, "current_group": kaisai_date}
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    race_ids = sorted(set(re.findall(r"race_id=(\d{12})", response.text)))
    return race_ids

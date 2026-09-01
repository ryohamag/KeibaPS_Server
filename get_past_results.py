import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

# 内部で使うキー名 -> netkeiba側の列見出しテキスト
# インデックス固定ではなく見出し名で引くことで、netkeiba側の列追加に強くする
COLUMN_MAP = {
    "日付": "日付",
    "開催": "開催",
    "天気": "天気",
    "R": "R",
    "レース名": "レース名",
    "頭数": "頭数",
    "枠番": "枠番",
    "馬番": "馬番",
    "オッズ": "オッズ",
    "人気": "人気",
    "着順": "着順",
    "騎手": "騎手",
    "斤量": "斤量",
    "距離": "距離",
    "馬場": "馬場",
    "タイム": "タイム",
    "タイム指数": "ﾀｲﾑ指数タイム指数(通常)タイム指数マスター",
    "着差": "着差",
    "通過": "通過",
    "ペース": "ペース",
    "上がり": "上り",
    "馬体重": "馬体重",
}


def extract_horse_id(horse_url):
    return horse_url.rstrip("/").split("/")[-1]


# 出走馬の過去の競走成績を取得(db.netkeibaのAjax API経由)
def get_past_results(horse_url):
    horse_id = extract_horse_id(horse_url)
    api_url = "https://db.netkeiba.com/horse/ajax_horse_results.html"
    params = {"input": "UTF-8", "output": "json", "id": horse_id}

    try:
        response = requests.get(api_url, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "OK":
            return []

        soup = BeautifulSoup(payload["data"], "html.parser")
        table = soup.find("table", class_="db_h_race_results")
        if table is None:
            return []

        thead = table.find("thead")
        if thead is None:
            return []
        headers_text = [th.get_text(strip=True) for th in thead.find_all("th")]
        header_index = {name: i for i, name in enumerate(headers_text)}

        body = table.find("tbody") or table
        race_data = []
        for row in body.find_all("tr"):
            cols = row.find_all("td")
            if not cols:
                continue
            cols_text = [col.get_text(strip=True).replace("　", " ") for col in cols]

            def col(header_name):
                idx = header_index.get(header_name)
                if idx is None or idx >= len(cols_text):
                    return None
                value = cols_text[idx]
                # "**" は非会員には非公開であることを示すマスク表示
                # (タイム指数などは直近1走のみ実値が入り、それ以前はこのマスクになる)
                if not value or value == "**":
                    return None
                return value

            # netkeiba側は上り(上がり3ハロン)のtdに、そのレースでの順位を
            # class="rank_1"〜"rank_3"として埋め込んでいる(4位以下は付与なし)
            agari_idx = header_index.get("上り")
            agari_rank = None
            if agari_idx is not None and agari_idx < len(cols):
                for c in cols[agari_idx].get("class") or []:
                    if c.startswith("rank_"):
                        agari_rank = c.replace("rank_", "")
                        break

            record = {
                internal_key: col(source_header)
                for internal_key, source_header in COLUMN_MAP.items()
            }
            record["上がり順位"] = agari_rank
            race_data.append(record)

        return race_data

    except (requests.RequestException, ValueError) as e:
        print(f"エラーが発生しました (URL: {horse_url}): {e}")
        return []

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import combinations

import requests

from ranking_logic import RANKINGS

JST = timezone(timedelta(hours=9))

BUCKET_BASE_URL = "https://storage.googleapis.com/keibaps-data"
BUCKET_LIST_URL = "https://storage.googleapis.com/storage/v1/b/keibaps-data/o"

# 1点あたりの購入額(円)。払戻はnetkeiba上で100円あたりの金額なので、100円固定で計算する
UNIT_STAKE = 100

# スナップショットを「開催日の朝9時(JST)より前」に生成されたものだけに限定する
# 「前日までに生成」ではなく朝9時とするのは、GitHub Actionsのcron遅延で、
# 金曜夜の確定版が当日未明にずれ込んでも有効なデータとして扱うため
# (JRAの最初の発走は9時台後半なので、これより前なら結果の混入はない)
SNAPSHOT_DEADLINE_HOUR = 9

# 検証する買い目: (表示名, 券種, 上位何頭を買うか)
# 券種 "tansho_fukusho" は単勝+複勝を同額ずつ買う「単複」
BETS = [
    ("単勝 1位", "tansho", 1),
    ("複勝 1位", "fukusho", 1),
    ("単複 1位", "tansho_fukusho", 1),
    ("馬連BOX 上位3頭", "umaren", 3),
    ("馬連BOX 上位5頭", "umaren", 5),
    ("三連複BOX 上位5頭", "sanrenpuku", 5),
]

# 予想ランキングの比較対象(アプリの予想ではなく、結果ページの人気順を使う)
BASELINE_RANKING = "人気(参考)"


# ---------------------------------------------------------------- GCS読み込み

def list_blob_names(prefix):
    names = []
    params = {"prefix": prefix, "fields": "items(name),nextPageToken"}
    while True:
        response = requests.get(BUCKET_LIST_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        names.extend(item["name"] for item in payload.get("items", []))
        token = payload.get("nextPageToken")
        if not token:
            return names
        params["pageToken"] = token


def fetch_json(blob_name):
    response = requests.get(f"{BUCKET_BASE_URL}/{blob_name}", timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def list_kaisai_dates(since=None, today=None):
    today = today or datetime.now(JST).strftime("%Y%m%d")
    dates = []
    for name in list_blob_names("racedata/final/index/"):
        match = re.search(r"/(\d{8})\.json$", name)
        if not match:
            continue
        date = match.group(1)
        if date > today or (since and date < since):
            continue
        dates.append(date)
    return sorted(dates)


def list_stored_result_ids():
    return {
        re.search(r"/(\d{12})\.json$", name).group(1)
        for name in list_blob_names("raceresult/")
        if re.search(r"/(\d{12})\.json$", name)
    }


def load_race_ids_by_date(kaisai_dates):
    with ThreadPoolExecutor(max_workers=8) as pool:
        indexes = list(pool.map(lambda d: fetch_json(f"racedata/final/index/{d}.json"), kaisai_dates))
    return {
        date: index["race_ids"]
        for date, index in zip(kaisai_dates, indexes)
        if index
    }


# ---------------------------------------------------------------- スナップショットの検証

# 前日確定版のスナップショットが、レース結果の混入していない(=予想に使ってよい)ものか
# レース後に手動再実行されたfinalは、過去成績に当該レース自身が入ってしまうため除外する
def is_clean_snapshot(snapshot, kaisai_date):
    generated_at = datetime.fromisoformat(snapshot["generated_at"])
    deadline = datetime.strptime(kaisai_date, "%Y%m%d").replace(
        hour=SNAPSHOT_DEADLINE_HOUR, tzinfo=JST
    )
    return generated_at < deadline


def _horse_id(horse_url):
    return horse_url.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------- 予想順位

# スナップショットからランキング別の「予想順の馬番リスト」を作る
# 実際に出走した馬(取消・除外を除く)だけで順位を付け直す
# (アプリは取消馬も順位計算に含めているが、取消がわかっていれば買わないため、
#  バックテストでは出走馬のみで計算するのが実運用に近い)
def build_predicted_orders(snapshot, race_result):
    started = {h["horse_id"]: h for h in race_result["results"] if h["started"]}

    entries = []
    for entry in snapshot["entries"]:
        horse = started.get(_horse_id(entry["horse_url"]))
        if horse is not None:
            entries.append((entry, horse["horse_number"]))
    if not entries:
        return {}

    number_by_url = {entry["horse_url"]: number for entry, number in entries}
    orders = {}
    for name, rank_fn in RANKINGS.items():
        ranks = rank_fn([entry for entry, _ in entries])
        ordered_urls = sorted(ranks, key=ranks.get)
        orders[name] = [number_by_url[url] for url in ordered_urls]

    popular = sorted(
        (h for h in started.values() if h["popularity"] is not None),
        key=lambda h: (h["popularity"], h["horse_number"]),
    )
    orders[BASELINE_RANKING] = [h["horse_number"] for h in popular]
    return orders


# ---------------------------------------------------------------- 買い目の払戻計算

def _tickets(bet_type, picks):
    if bet_type in ("tansho", "fukusho"):
        return [frozenset([n]) for n in picks]
    size = {"umaren": 2, "sanrenpuku": 3}[bet_type]
    return [frozenset(c) for c in combinations(picks, size)]


# 1レース分の (購入額, 払戻額) を返す。そのレースで発売されていない券種や、
# 出走頭数が足りず買い目を作れない場合は None(集計対象外)
def evaluate_bet(payouts, bet_type, top_n, order):
    if bet_type == "tansho_fukusho":
        tansho = evaluate_bet(payouts, "tansho", top_n, order)
        fukusho = evaluate_bet(payouts, "fukusho", top_n, order)
        if tansho is None or fukusho is None:
            return None
        return tansho[0] + fukusho[0], tansho[1] + fukusho[1]

    winners = payouts.get(bet_type) or []
    if not winners or len(order) < top_n:
        return None

    tickets = _tickets(bet_type, order[:top_n])
    payout = sum(
        w["payout"] * tickets.count(frozenset(w["numbers"]))
        for w in winners
    )
    # 払戻は100円あたりの金額。UNIT_STAKE が100円以外でも比例して計算できるようにしておく
    return len(tickets) * UNIT_STAKE, payout * UNIT_STAKE // 100


# ---------------------------------------------------------------- 集計

class BetStats:
    def __init__(self):
        self.races = 0
        self.hit_races = 0
        self.stake = 0
        self.payout = 0
        self.best_race_payout = 0
        self.best_race_stake = 0

    def add(self, stake, payout):
        self.races += 1
        self.stake += stake
        self.payout += payout
        if payout > 0:
            self.hit_races += 1
        if payout > self.best_race_payout:
            self.best_race_payout = payout
            self.best_race_stake = stake

    @property
    def recovery_rate(self):
        return self.payout / self.stake if self.stake else None

    @property
    def hit_rate(self):
        return self.hit_races / self.races if self.races else None

    # 最も大きく当たった1レースを除いた回収率。
    # 万馬券1本で回収率が大きく振れるため、運に左右されていないかの目安になる
    @property
    def recovery_rate_without_best(self):
        stake = self.stake - self.best_race_stake
        return (self.payout - self.best_race_payout) / stake if stake > 0 else None


def run_backtest(records):
    """records: [{"snapshot": ..., "result": ..., "kaisai_date": ...}]"""
    ranking_names = list(RANKINGS) + [BASELINE_RANKING]
    stats = {
        ranking: {bet_name: BetStats() for bet_name, _, _ in BETS}
        for ranking in ranking_names
    }

    evaluated_races = 0
    for record in records:
        orders = build_predicted_orders(record["snapshot"], record["result"])
        if not orders:
            continue
        evaluated_races += 1
        for ranking, order in orders.items():
            for bet_name, bet_type, top_n in BETS:
                outcome = evaluate_bet(record["result"]["payouts"], bet_type, top_n, order)
                if outcome is not None:
                    stats[ranking][bet_name].add(*outcome)

    return {"stats": stats, "evaluated_races": evaluated_races}

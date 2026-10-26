import math

import numpy as np

from backtest import (
    BASELINE_RANKING,
    BETS,
    LONGSHOT_BANDS,
    LONGSHOT_MIN_ODDS,
    LONGSHOT_TOP_N,
    _odds_band,
    build_predicted_orders,
    evaluate_bet,
)
from ranking_logic import RANKINGS

# 月次の通知に載せる検定
#
# 検定をたくさん並べると、どれか1つは偶然でp<0.05になる(多重比較)。そこで、
# 判定に使う「本命の仮説」を1つだけ事前に固定し、それ以外は参考扱いにする。
# また、仮説を立てるときに見たデータで検定すると甘くなるため、本命の仮説は
# 仮説を立てた後のデータ(HYPOTHESIS_SINCE 以降)だけで判定する。

# 本命の仮説: 指数上位3の黒オッズ馬は、同じオッズ帯の他の黒オッズ馬より複勝率が高い
# (2026/10/10の集計を見て立てた仮説なので、翌開催の10/12以降で検証する)
PRIMARY_RANKING = "指数"
PRIMARY_METRIC = "複勝率"
HYPOTHESIS_SINCE = "20261012"
ALPHA = 0.05

# 効果が複勝率+3pt程度のとき、検出力80%で判定するのに必要なレース数の目安
# (上位3の黒オッズ馬は1レースあたり約1.3頭、他の黒オッズ馬の複勝率は約11%として概算)
TARGET_RACES = 500

METRICS = {"複勝率": "placed", "勝率": "won"}

BOOTSTRAP_SAMPLES = 10000
BOOTSTRAP_CHUNK = 1000  # レース数が増えてもメモリを使いすぎないよう、分けて再標本する
BOOTSTRAP_SEED = 0  # 毎回同じ結果になるよう固定(週によって区間が揺れないようにする)


def _normal_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


# ---------------------------------------------------------------- 黒オッズ馬の比較

def _longshot_horses(records):
    """黒オッズ馬1頭ずつの (オッズ帯, {ランキング: 上位3か}, 複勝圏か, 1着か)
    複勝が発売されていないレース(出走5頭以下)は、複勝率を定義できないため除く"""
    horses = []
    for record in records:
        result = record["result"]
        payouts = result["payouts"]
        if not payouts.get("fukusho"):
            continue
        orders = build_predicted_orders(record["snapshot"], result)
        if not orders:
            continue
        placed = {n for w in payouts["fukusho"] for n in w["numbers"]}
        won = {n for w in payouts.get("tansho") or [] for n in w["numbers"]}
        tops = {r: set(orders.get(r, [])[:LONGSHOT_TOP_N]) for r in RANKINGS}
        for h in result["results"]:
            if not h["started"] or h["odds"] is None or h["odds"] < LONGSHOT_MIN_ODDS:
                continue
            number = h["horse_number"]
            horses.append({
                "band": _odds_band(h["odds"]),
                "top": {r: number in tops[r] for r in RANKINGS},
                "placed": number in placed,
                "won": number in won,
            })
    return horses


def compare_longshots(horses, ranking, metric):
    """ランキング上位3の黒オッズ馬と、それ以外の黒オッズ馬の比較
    オッズ帯で層別したCochran–Mantel–Haenszel検定(片側: 上位3の方が高い)。
    帯ごとに比べてから合算するので、帯の構成の違い(上位3には人気寄りの馬が多い)に左右されない"""
    key = METRICS[metric]
    bands = []
    numerator = variance = 0.0
    for band, _, _ in LONGSHOT_BANDS:
        rows = [h for h in horses if h["band"] == band]
        top_n = sum(1 for h in rows if h["top"][ranking])
        top_hit = sum(1 for h in rows if h["top"][ranking] and h[key])
        other_n = len(rows) - top_n
        other_hit = sum(1 for h in rows if not h["top"][ranking] and h[key])
        bands.append({"band": band, "top_n": top_n, "top_hit": top_hit, "other_n": other_n, "other_hit": other_hit})

        total, hits = top_n + other_n, top_hit + other_hit
        if total < 2 or top_n == 0 or other_n == 0:
            continue
        numerator += top_hit - top_n * hits / total
        variance += top_n * other_n * hits * (total - hits) / (total * total * (total - 1))

    z = numerator / math.sqrt(variance) if variance > 0 else None
    return {
        "bands": bands,
        "top_n": sum(b["top_n"] for b in bands),
        "top_hit": sum(b["top_hit"] for b in bands),
        "other_n": sum(b["other_n"] for b in bands),
        "other_hit": sum(b["other_hit"] for b in bands),
        "z": z,
        "p": _normal_sf(z) if z is not None else None,
    }


# ---------------------------------------------------------------- 回収率の信頼区間

def bootstrap_recovery(records):
    """レース単位のブートストラップで、回収率の95%信頼区間と、人気(参考)との差の95%区間を求める
    同じ再標本を全ての買い方に使うので、人気との差は「同じレースで比べた」対応のある比較になる"""
    rankings = list(RANKINGS) + [BASELINE_RANKING]
    stakes = {(r, b): [] for r in rankings for b, _, _ in BETS}
    payouts = {(r, b): [] for r in rankings for b, _, _ in BETS}
    for record in records:
        orders = build_predicted_orders(record["snapshot"], record["result"])
        if not orders:
            continue
        for ranking in rankings:
            for bet_name, bet_type, top_n in BETS:
                outcome = evaluate_bet(record["result"]["payouts"], bet_type, top_n, orders.get(ranking, []))
                stakes[(ranking, bet_name)].append(outcome[0] if outcome else 0)
                payouts[(ranking, bet_name)].append(outcome[1] if outcome else 0)

    race_count = len(stakes[(rankings[0], BETS[0][0])])
    if race_count == 0:
        return {}
    stakes = {k: np.array(v, dtype=float) for k, v in stakes.items()}
    payouts = {k: np.array(v, dtype=float) for k, v in payouts.items()}

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = {k: [] for k in stakes}
    for start in range(0, BOOTSTRAP_SAMPLES, BOOTSTRAP_CHUNK):
        size = min(BOOTSTRAP_CHUNK, BOOTSTRAP_SAMPLES - start)
        index = rng.integers(0, race_count, size=(size, race_count))
        for k in stakes:
            stake = stakes[k][index].sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                samples[k].append(payouts[k][index].sum(axis=1) / stake)
    samples = {k: np.concatenate(v) for k, v in samples.items()}

    results = {}
    for (ranking, bet_name), sample in samples.items():
        total_stake = stakes[(ranking, bet_name)].sum()
        if total_stake == 0:
            continue
        entry = {
            "rate": payouts[(ranking, bet_name)].sum() / total_stake,
            "low": np.nanpercentile(sample, 2.5),
            "high": np.nanpercentile(sample, 97.5),
        }
        if ranking != BASELINE_RANKING:
            diff = sample - samples[(BASELINE_RANKING, bet_name)]
            entry["diff_low"] = np.nanpercentile(diff, 2.5)
            entry["diff_high"] = np.nanpercentile(diff, 97.5)
        results[(ranking, bet_name)] = entry
    return results


# ---------------------------------------------------------------- まとめ

def run_significance(records):
    after = [r for r in records if r["kaisai_date"] >= HYPOTHESIS_SINCE]
    all_horses = _longshot_horses(records)
    after_horses = _longshot_horses(after)

    primary = compare_longshots(after_horses, PRIMARY_RANKING, PRIMARY_METRIC)
    primary["races"] = len(after)
    primary["significant"] = primary["p"] is not None and primary["p"] < ALPHA

    exploratory = [
        {
            "ranking": ranking,
            "metric": metric,
            "all": compare_longshots(all_horses, ranking, metric),
            "after": compare_longshots(after_horses, ranking, metric),
        }
        for ranking in RANKINGS
        for metric in METRICS
    ]

    return {
        "primary": primary,
        "exploratory": exploratory,
        "recovery": bootstrap_recovery(records),
    }

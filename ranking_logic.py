INF = float("inf")


# iOSアプリ側 RaceCard+Analysis.swift / RaceEntry+Analysis.swift / RaceTimeParser.swift の移植
# アプリが画面に出している順位と、バックテストで検証する順位を一致させるため、
# ロジックを変更する場合はiOS側と必ず同時に直すこと


# "1:47.9" -> 107.9
def seconds_from_time(time_string):
    if not time_string:
        return None
    parts = time_string.split(":")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]) * 60 + float(parts[1])
    except ValueError:
        return None


def _float_or_none(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int_or_none(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


# 参考タイム(matching_results)の中で最も速いタイムの秒数
def best_matching_seconds(entry):
    seconds = [seconds_from_time(r.get("タイム")) for r in entry.get("matching_results") or []]
    seconds = [s for s in seconds if s is not None]
    return min(seconds) if seconds else None


# 直近1走(results の先頭)のタイム指数。非会員には直近1走ぶんしか公開されない
def recent_time_index(entry):
    results = entry.get("results") or []
    return _int_or_none(results[0].get("タイム指数")) if results else None


# 3段階の優先度で比較するキー(小さいほど強い)
#   0: 同条件(matched)の参考タイムがある馬 -> タイムの速い順
#   1: 同条件ではないが直近走の着差が分かる馬 -> 着差が小さい順
#   2: どちらの情報もない馬 -> 最下位
def _time_key(entry):
    seconds = best_matching_seconds(entry)
    if entry.get("matched") and seconds is not None:
        return (0, seconds)
    results = entry.get("results") or []
    margin = _float_or_none(results[0].get("着差")) if results else None
    if margin is not None:
        return (1, margin)
    return (2, INF)


def _ordinal_ranks(entries, key):
    # 同値の場合は馬番順で決める(Swift側のsortは安定ではないが、再現性のため固定する)
    ordered = sorted(entries, key=lambda e: (key(e), e.get("horse_number") or 999))
    return {e["horse_url"]: i + 1 for i, e in enumerate(ordered)}


def time_ranks(entries):
    return _ordinal_ranks(entries, _time_key)


def time_index_ranks(entries):
    def key(entry):
        value = recent_time_index(entry)
        return -value if value is not None else INF

    return _ordinal_ranks(entries, key)


# タイム順位 + 指数順位の合計(小さいほど総合力が高い)
# 同点の場合はタイム順位が良い方を上位とする
def total_ranks(entries):
    t_ranks = time_ranks(entries)
    i_ranks = time_index_ranks(entries)
    worst = len(entries) + 1

    def key(entry):
        url = entry["horse_url"]
        t = t_ranks.get(url, worst)
        i = i_ranks.get(url, worst)
        return (t + i, t)

    return _ordinal_ranks(entries, key)


RANKINGS = {
    "指数": time_index_ranks,
    "タイム": time_ranks,
    "総合": total_ranks,
}

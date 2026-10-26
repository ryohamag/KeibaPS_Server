import io
import os
from datetime import datetime
from itertools import groupby

import matplotlib

matplotlib.use("Agg")  # GitHub Actions上など、画面のない環境で描画するため

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from backtest import (  # noqa: E402
    BASELINE_RANKING,
    BETS,
    LONGSHOT_ALL,
    LONGSHOT_BASELINE,
    LONGSHOT_MIN_ODDS,
    LONGSHOT_TOP_N,
    UNIT_STAKE,
    run_backtest,
)
from ranking_logic import RANKINGS  # noqa: E402
from report_image import FONT_CANDIDATES  # noqa: E402

# 累計回収率の推移を折れ線グラフで描く(月に1回の通知用)
# 各開催日時点での「それまでの全レースの累計」なので、週ごとの振れより全体の傾向を見る

# アプリの表示色に合わせる(指数=indigo、総合=teal)
LINE_STYLES = {
    "指数": {"color": "#4F46E5"},
    "タイム": {"color": "#EA580C"},
    "総合": {"color": "#0D9488"},
    BASELINE_RANKING: {"color": "#6B7280", "linestyle": "--"},
    LONGSHOT_BASELINE: {"color": "#6B7280", "linestyle": "--"},
}

# 黒オッズ馬のパネル: (表示名, 回収率の分子の属性, 分母の頭数の属性, 1頭あたりの購入額)
LONGSHOT_PANELS = [
    ("単勝", "tansho_payout", "horses", UNIT_STAKE),
    ("複勝", "fukusho_payout", "fukusho_horses", UNIT_STAKE),
]

# 序盤はレース数が少なく数百%に振れるため、縦軸の上限を抑える
Y_MAX_CAP = 3.0


def _use_japanese_font():
    for regular, _ in FONT_CANDIDATES:
        if os.path.exists(regular):
            font_manager.fontManager.addfont(regular)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=regular).get_name()
            return
    raise RuntimeError("日本語フォントが見つかりません(Ubuntuでは fonts-noto-cjk が必要です)")


def cumulative_series(records):
    """開催日ごとに、その日までの累計回収率を求める
    戻り値: (日付のリスト, {(パネル名, 系列名): [回収率 or None, ...]})"""
    totals = {}
    series = {}
    dates = []

    def add(key, stake, payout):
        total = totals.setdefault(key, [0, 0])
        total[0] += stake
        total[1] += payout

    for kaisai_date, day_records in groupby(records, key=lambda r: r["kaisai_date"]):
        summary = run_backtest(list(day_records))
        dates.append(datetime.strptime(kaisai_date, "%Y%m%d"))

        for ranking in list(RANKINGS) + [BASELINE_RANKING]:
            for bet_name, _, _ in BETS:
                stat = summary["stats"][ranking][bet_name]
                add((bet_name, ranking), stat.stake, stat.payout)

        for group in list(RANKINGS) + [LONGSHOT_BASELINE]:
            stat = summary["longshot"][group][LONGSHOT_ALL]
            for panel, payout_attr, count_attr, stake in LONGSHOT_PANELS:
                add((f"黒オッズ {panel}", group), getattr(stat, count_attr) * stake, getattr(stat, payout_attr))

        for key, (stake, payout) in totals.items():
            series.setdefault(key, [None] * (len(dates) - 1))
            series[key].append(payout / stake if stake else None)

    return dates, series


def render_trend_chart(records, meta):
    _use_japanese_font()
    records = sorted(records, key=lambda r: r["kaisai_date"])
    dates, series = cumulative_series(records)

    panels = [(bet_name, list(RANKINGS) + [BASELINE_RANKING]) for bet_name, _, _ in BETS]
    panels += [
        (f"黒オッズ {panel}", list(RANKINGS) + [LONGSHOT_BASELINE])
        for panel, _, _, _ in LONGSHOT_PANELS
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 8.5), sharex=True)
    for ax, (panel, names) in zip(axes.flat, panels):
        y_max = 1.2
        for name in names:
            values = series.get((panel, name))
            if not values:
                continue
            percent = [v * 100 if v is not None else None for v in values]
            ax.plot(dates, percent, marker="o", markersize=3, linewidth=1.8, label=name, **LINE_STYLES[name])
            y_max = max(y_max, max((v for v in values if v is not None), default=0))
        ax.axhline(100, color="#16A34A", linewidth=1, linestyle=":")
        ax.set_ylim(0, min(y_max, Y_MAX_CAP) * 105)
        title = panel
        if panel.startswith("黒オッズ"):
            title = f"{panel}(上位{LONGSHOT_TOP_N}位・{LONGSHOT_MIN_ODDS:g}倍以上)"
        ax.set_title(title, fontsize=12)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d"))
        ax.grid(alpha=0.3)
        ax.tick_params(axis="x", labelrotation=45, labelsize=9)
        ax.legend(fontsize=8, loc="upper right")

    fig.suptitle(
        f"累計回収率の推移  {meta['first_date']} 〜 {meta['last_date']}(各開催日までの全レースの累計)",
        fontsize=15,
    )
    fig.text(
        0.5, 0.01,
        "緑の点線=回収率100% / 灰色の破線=比較用(人気順、または黒オッズ全体)。"
        "序盤はレース数が少なく大きく振れるため、後半の落ち着き方を見る",
        ha="center", fontsize=10, color="#64748B",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110)
    plt.close(fig)
    return buffer.getvalue()

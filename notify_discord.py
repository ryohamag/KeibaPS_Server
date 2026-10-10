import os

import requests

from backtest import BASELINE_RANKING, BETS
from ranking_logic import RANKINGS

# 回収率が100%を超えたかどうかが一目で分かるよう、行頭に印を付ける
PROFIT_MARK = "🟢"
LOSS_MARK = "🔻"


def _format_rate(rate):
    return f"{rate * 100:.1f}%" if rate is not None else "-"


def _format_line(bet_name, stat):
    if stat.races == 0:
        return f"**{bet_name}** 対象レースなし"
    mark = PROFIT_MARK if stat.recovery_rate >= 1 else LOSS_MARK
    return (
        f"{mark} **{bet_name}** 回収率 **{_format_rate(stat.recovery_rate)}**"
        f" ・的中率 {_format_rate(stat.hit_rate)}"
        f" ・最大1本除外 {_format_rate(stat.recovery_rate_without_best)}"
        f" ・{stat.races}R"
    )


def build_embed(summary, meta):
    fields = []
    for ranking in list(RANKINGS) + [BASELINE_RANKING]:
        lines = [_format_line(bet_name, summary["stats"][ranking][bet_name]) for bet_name, _, _ in BETS]
        fields.append({"name": f"■ {ranking}ランキング", "value": "\n".join(lines), "inline": False})

    description = (
        f"期間: {meta['first_date']} 〜 {meta['last_date']}"
        f"({meta['date_count']}開催日 / {summary['evaluated_races']}レース)\n"
        "1点100円・払戻は確定払戻。「最大1本除外」は最も大きく当たった1レースを除いた回収率"
    )
    if meta["excluded_snapshots"]:
        description += f"\n結果混入のため除外したレース: {meta['excluded_snapshots']}"

    return {
        "title": "KeibaPS 予想ランキングの回収率検証",
        "description": description,
        "color": 0x2E8B57,
        "fields": fields,
        "footer": {
            "text": "人気(参考)は結果ページの人気順で、比較用のベースライン。"
                    "高配当1本で大きく振れるため、数百レース程度では誤差が大きい"
        },
    }


def send_embed(embed, webhook_url=None):
    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("環境変数 DISCORD_WEBHOOK_URL が設定されていません")
    response = requests.post(webhook_url, json={"embeds": [embed]}, timeout=30)
    response.raise_for_status()

import json
import os

import requests

from backtest import (
    BASELINE_RANKING,
    BETS,
    LONGSHOT_ALL,
    LONGSHOT_BANDS,
    LONGSHOT_BASELINE,
    LONGSHOT_MIN_ODDS,
    LONGSHOT_TOP_N,
)
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


def _format_horse_rate(rate):
    return f"{rate * 100:.1f}%" if rate is not None else "-"


def _format_longshot_line(band, stat):
    if stat.horses == 0:
        return f"{band}: 該当なし"
    average_finish = f"{stat.average_finish:.1f}着" if stat.average_finish is not None else "-"
    return (
        f"{band}: {stat.horses}頭"
        f" ・勝率 {_format_horse_rate(stat.win_rate)}"
        f" ・複勝率 {_format_horse_rate(stat.place_rate)}"
        f" ・単勝回収 **{_format_horse_rate(stat.tansho_recovery)}**"
        f" ・複勝回収 **{_format_horse_rate(stat.fukusho_recovery)}**"
        f" ・単複回収 **{_format_horse_rate(stat.combo_recovery)}**"
        f" ・平均{average_finish}"
    )


# 黒オッズ(単勝10倍以上)なのに予想ランキング上位に来た馬を、1頭ずつ買った場合の成績
def build_longshot_fields(summary):
    bands = [LONGSHOT_ALL] + [name for name, _, _ in LONGSHOT_BANDS]
    fields = []
    for ranking in list(RANKINGS) + [LONGSHOT_BASELINE]:
        if ranking == LONGSHOT_BASELINE:
            name = f"□ 比較: {LONGSHOT_BASELINE}(ランキング不問)"
        else:
            name = f"◆ 黒オッズ × {ranking}ランキング上位{LONGSHOT_TOP_N}"
        lines = [_format_longshot_line(band, summary["longshot"][ranking][band]) for band in bands]
        fields.append({"name": name, "value": "\n".join(lines), "inline": False})
    return fields


def build_embed(summary, meta):
    fields = []
    for ranking in list(RANKINGS) + [BASELINE_RANKING]:
        lines = [_format_line(bet_name, summary["stats"][ranking][bet_name]) for bet_name, _, _ in BETS]
        fields.append({"name": f"■ {ranking}ランキング", "value": "\n".join(lines), "inline": False})

    fields.append({
        "name": f"━━ 黒オッズ(単勝{LONGSHOT_MIN_ODDS:g}倍以上)の馬を1頭ずつ単勝・複勝で購入 ━━",
        "value": "ランキング上位なのに人気がない馬は、本当に好走しているか(比較は「黒オッズ全体」)",
        "inline": False,
    })
    fields.extend(build_longshot_fields(summary))

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


# 表を画像として添付して投稿する。画像の描画に失敗した場合(日本語フォント未導入など)は、
# 通知自体が止まらないよう呼び出し側でテキスト版のembedにフォールバックする
def send_images(summary, meta, webhook_url=None):
    from report_image import render_longshot_table, render_race_table

    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("環境変数 DISCORD_WEBHOOK_URL が設定されていません")

    race_png = render_race_table(summary, meta)
    longshot_png = render_longshot_table(summary, meta)

    description = f"{meta['first_date']} 〜 {meta['last_date']}({meta['date_count']}開催日 / {summary['evaluated_races']}レース)"
    if meta["excluded_snapshots"]:
        description += f"\n結果混入のため除外したレース: {meta['excluded_snapshots']}"
    payload = {
        "embeds": [
            {
                "title": "KeibaPS 予想ランキングの回収率検証",
                "description": description,
                "color": 0x2E8B57,
                "image": {"url": "attachment://race.png"},
            },
            {
                "image": {"url": "attachment://longshot.png"},
                "footer": {"text": "高配当1本で大きく振れるため、数百レース程度では誤差が大きい"},
            },
        ]
    }
    response = requests.post(
        webhook_url,
        data={"payload_json": json.dumps(payload)},
        files={
            "files[0]": ("race.png", race_png, "image/png"),
            "files[1]": ("longshot.png", longshot_png, "image/png"),
        },
        timeout=60,
    )
    response.raise_for_status()

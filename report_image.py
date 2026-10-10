import io
import os

from PIL import Image, ImageDraw, ImageFont

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

# Discordはembedで表形式を扱えないため、集計結果の表を画像として描画して添付する
# (回収率100%超などをセルの色で強調できる)

# 通常/太字フォントの候補(ローカルのmacOS、GitHub Actions上のUbuntu)
# Ubuntuでは `apt-get install fonts-noto-cjk` で入る
FONT_CANDIDATES = [
    ("/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
]

SCALE = 2  # 高解像度で描画して、Discord上でも文字がつぶれないようにする

WHITE = (255, 255, 255)
INK = (30, 41, 59)
MUTED = (100, 116, 139)
LINE = (203, 213, 225)
HEADER_BG = (51, 65, 85)
BASELINE_BG = (243, 244, 246)
PROFIT_BG, PROFIT_FG = (198, 239, 206), (0, 97, 0)
BETTER_BG, BETTER_FG = (219, 234, 254), (30, 64, 175)


def _load_fonts():
    for regular, bold in FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            def make(path, size):
                return ImageFont.truetype(path, size * SCALE)
            return {
                "title": make(bold, 22),
                "head": make(bold, 15),
                "main": make(bold, 18),
                "main_plain": make(regular, 18),
                "sub": make(regular, 12),
                "note": make(regular, 13),
            }
    raise RuntimeError("日本語フォントが見つかりません(Ubuntuでは fonts-noto-cjk が必要です)")


def _pct(rate):
    return f"{rate * 100:.1f}%" if rate is not None else "-"


class _Canvas:
    def __init__(self, width, height, fonts):
        self.fonts = fonts
        self.image = Image.new("RGB", (width * SCALE, height * SCALE), WHITE)
        self.draw = ImageDraw.Draw(self.image)

    def text_center(self, box, lines):
        """box=(x, y, w, h)に、(テキスト, フォント名, 色)の行を縦中央で描く"""
        x, y, w, h = [v * SCALE for v in box]
        heights = []
        for text, font_key, _ in lines:
            bbox = self.draw.textbbox((0, 0), text, font=self.fonts[font_key])
            heights.append(bbox[3] - bbox[1])
        gap = 4 * SCALE
        total = sum(heights) + gap * (len(lines) - 1)
        cursor = y + (h - total) / 2
        for (text, font_key, color), height in zip(lines, heights):
            font = self.fonts[font_key]
            bbox = self.draw.textbbox((0, 0), text, font=font)
            self.draw.text(
                (x + (w - (bbox[2] - bbox[0])) / 2 - bbox[0], cursor - bbox[1]),
                text, font=font, fill=color,
            )
            cursor += height + gap

    def text_left(self, xy, text, font_key, color):
        x, y = xy
        self.draw.text((x * SCALE, y * SCALE), text, font=self.fonts[font_key], fill=color)

    def rect(self, box, fill):
        x, y, w, h = [v * SCALE for v in box]
        self.draw.rectangle([x, y, x + w, y + h], fill=fill)

    def hline(self, y, x0, x1, width=1):
        self.draw.line([x0 * SCALE, y * SCALE, x1 * SCALE, y * SCALE], fill=LINE, width=width * SCALE)

    def png(self):
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


# ---------------------------------------------------------------- レース単位の表

def render_race_table(summary, meta):
    fonts = _load_fonts()
    rankings = list(RANKINGS) + [BASELINE_RANKING]
    label_w, col_w, row_h, head_h = 200, 180, 92, 40
    top, margin = 74, 16
    width = margin * 2 + label_w + col_w * len(rankings)
    height = top + head_h + row_h * len(BETS) + 60

    canvas = _Canvas(width, height, fonts)
    canvas.text_left((margin, 14), "予想ランキング別の回収率(上位を購入)", "title", INK)
    canvas.text_left(
        (margin, 46),
        f"{meta['first_date']} 〜 {meta['last_date']}  {meta['date_count']}開催日 / {summary['evaluated_races']}レース ・ 1点100円",
        "note", MUTED,
    )

    y = top
    canvas.rect((margin, y, width - margin * 2, head_h), HEADER_BG)
    canvas.text_center((margin, y, label_w, head_h), [("買い目", "head", WHITE)])
    for i, ranking in enumerate(rankings):
        canvas.text_center((margin + label_w + col_w * i, y, col_w, head_h), [(ranking, "head", WHITE)])
    y += head_h

    for bet_name, _, _ in BETS:
        canvas.text_center((margin, y, label_w, row_h), [(bet_name, "main_plain", INK)])
        for i, ranking in enumerate(rankings):
            stat = summary["stats"][ranking][bet_name]
            x = margin + label_w + col_w * i
            if stat.races == 0:
                canvas.text_center((x, y, col_w, row_h), [("-", "main_plain", MUTED)])
                continue
            profit = stat.recovery_rate >= 1
            if profit:
                canvas.rect((x + 3, y + 3, col_w - 6, row_h - 6), PROFIT_BG)
            canvas.text_center((x, y, col_w, row_h), [
                (_pct(stat.recovery_rate), "main", PROFIT_FG if profit else INK),
                (f"的中率 {_pct(stat.hit_rate)}", "sub", MUTED),
                (f"最大1本除外 {_pct(stat.recovery_rate_without_best)}", "sub", MUTED),
            ])
        y += row_h
        canvas.hline(y, margin, width - margin)

    canvas.text_left((margin, y + 12), "太字=回収率 / 緑=回収率100%超 / 最大1本除外=最も大きく当たった1レースを除いた回収率", "note", MUTED)
    canvas.text_left((margin, y + 32), "人気(参考)=結果ページの最終人気順で同じ買い方をした場合(比較用)", "note", MUTED)
    return canvas.png()


# ---------------------------------------------------------------- 黒オッズの表

LONGSHOT_COLUMNS = [
    ("頭数", 70),
    ("勝率", 80),
    ("複勝率", 80),
    ("単勝回収", 96),
    ("複勝回収", 96),
    ("単複回収", 96),
    ("平均着順", 86),
]


def _longshot_cells(stat, base):
    """(テキスト, 背景色, 文字色)のリスト。baseは同じオッズ帯の基準(黒オッズ全体)で、基準行ではNone"""
    def recovery(rate):
        if rate is None:
            return "-", None, MUTED
        if rate >= 1:
            return _pct(rate), PROFIT_BG, PROFIT_FG
        return _pct(rate), None, INK

    def better(value, base_value, lower_is_better=False):
        if value is None:
            return "-", None, MUTED
        text = f"{value:.1f}着" if lower_is_better else _pct(value)
        if base is None or base_value is None:
            return text, None, INK
        wins = value < base_value if lower_is_better else value > base_value
        return (text, BETTER_BG, BETTER_FG) if wins else (text, None, INK)

    return [
        (f"{stat.horses}", None, INK),
        better(stat.win_rate, base and base.win_rate),
        better(stat.place_rate, base and base.place_rate),
        recovery(stat.tansho_recovery),
        recovery(stat.fukusho_recovery),
        recovery(stat.combo_recovery),
        better(stat.average_finish, base and base.average_finish, lower_is_better=True),
    ]


def render_longshot_table(summary, meta):
    fonts = _load_fonts()
    bands = [LONGSHOT_ALL] + [name for name, _, _ in LONGSHOT_BANDS]
    groups = [LONGSHOT_BASELINE] + list(RANKINGS)
    label_w, band_w, row_h, head_h = 210, 84, 40, 40
    top, margin = 74, 16
    width = margin * 2 + label_w + band_w + sum(w for _, w in LONGSHOT_COLUMNS)
    height = top + head_h + row_h * len(bands) * len(groups) + 80

    canvas = _Canvas(width, height, fonts)
    canvas.text_left(
        (margin, 14),
        f"黒オッズ(単勝{LONGSHOT_MIN_ODDS:g}倍以上)の馬を1頭ずつ購入した場合", "title", INK,
    )
    canvas.text_left(
        (margin, 46),
        f"各ランキング上位{LONGSHOT_TOP_N}位以内の黒オッズ馬の成績 ・ 単勝・複勝・単複を各100円",
        "note", MUTED,
    )

    y = top
    canvas.rect((margin, y, width - margin * 2, head_h), HEADER_BG)
    canvas.text_center((margin, y, label_w, head_h), [("対象", "head", WHITE)])
    canvas.text_center((margin + label_w, y, band_w, head_h), [("オッズ帯", "head", WHITE)])
    x = margin + label_w + band_w
    for name, w in LONGSHOT_COLUMNS:
        canvas.text_center((x, y, w, head_h), [(name, "head", WHITE)])
        x += w
    y += head_h

    for group in groups:
        is_baseline = group == LONGSHOT_BASELINE
        if is_baseline:
            canvas.rect((margin, y, width - margin * 2, row_h * len(bands)), BASELINE_BG)
        for i, band in enumerate(bands):
            stat = summary["longshot"][group][band]
            # 「全体」の行は基準とオッズ帯の構成が違い比較できないため、青の強調は付けない
            base = None if is_baseline or band == LONGSHOT_ALL else summary["longshot"][LONGSHOT_BASELINE][band]
            if i == 0:
                label = f"{group}(基準)" if is_baseline else f"{group}上位{LONGSHOT_TOP_N}"
                canvas.text_center((margin, y, label_w, row_h), [(label, "main", INK)])
            canvas.text_center((margin + label_w, y, band_w, row_h), [(band, "main_plain", INK)])
            if stat.horses == 0:
                x = margin + label_w + band_w
                canvas.text_center((x, y, sum(w for _, w in LONGSHOT_COLUMNS), row_h), [("該当なし", "main_plain", MUTED)])
            else:
                x = margin + label_w + band_w
                for (text, bg, fg), (_, w) in zip(_longshot_cells(stat, base), LONGSHOT_COLUMNS):
                    if bg:
                        canvas.rect((x + 2, y + 2, w - 4, row_h - 4), bg)
                    canvas.text_center((x, y, w, row_h), [(text, "main_plain", fg)])
                    x += w
            y += row_h
        canvas.hline(y, margin, width - margin, width=2)

    canvas.text_left((margin, y + 12), "緑=回収率100%超 / 青=同じオッズ帯の基準(黒オッズ全体)より良い(勝率・複勝率は高い、平均着順は小さい)", "note", MUTED)
    canvas.text_left((margin, y + 32), "基準=ランキングで絞る前の、同じオッズ帯の馬全体。全体の行は基準と帯の構成が違うため、帯ごとに比べる", "note", MUTED)
    canvas.text_left((margin, y + 52), "オッズはレース後の確定オッズ。件数が少ないうちは偶然の範囲を超えているとは言えない", "note", MUTED)
    return canvas.png()

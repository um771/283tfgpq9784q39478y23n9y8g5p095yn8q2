import re
import random
import subprocess

# ============================================================
# 設定
# ============================================================

# 資料オンリーモード（-1 = OFF / 2 = モード2 / 3 = モード3。1は欠番）
SHURYO_ONLY_MODE = 0

PATTERN_MODE = -1
USE_MARKOV_MODE = 1
HERO_MODE = -1
USE_LAST_MARKOV_LINE_MODE = 1

# === 追加 ===
# 冒頭フロー指定（冒頭.txtを1文マルコフで合成し、テーマ提示の直前に注入）
USE_OPENING_MARKOV_MODE = 1  # 1 = ON / 0 = OFF
# 終盤フロー指定（終盤.txtを1文マルコフで合成し、冒頭ブロックの直後に注入）
USE_ENDING_MARKOV_MODE = 1  # 1 = ON / 0 = OFF

# 冒頭・終盤フローの注入レート（％）
# MODEがONのとき、さらにこの確率を引いて実際に注入するかを決める。
# 100 = 毎回必ず注入（従来の挙動） / 50 = 2回に1回 / 0 = 実質OFF。
# 冒頭と終盤は独立に判定するため、両方入る回・片方だけの回・
# どちらも入らない回が出る。
OPENING_RATE = 50
ENDING_RATE = 50
# =============

# マルコフ連鎖パラメータ
MARKOV_ORDER     = 0  # ★ 0 = ランダム(1～4) / 1～4 = 固定値
MARKOV_LINES_MIN = 1
MARKOV_LINES_MAX = 2000

# 資料オンリーモード（モード2・3）用のマルコフ最大行数
MARKOV_LINES_MAX_SHURYO_MODE = 2000  # ★ 追加：この値を調整可能にする

# === 追加 ===
MARKOV_FLUCTUATION = 1   # 1 = ON（揺らぐ） / -1 = OFF（固定でMARKOV_ORDERを使用）
# =============

# === ここに追加 ===
# 文字数指定パラメータ
CHAR_COUNT_MIN = 9000
CHAR_COUNT_MAX = 20000


MAX_CHAR   = 119_000
MAX_RETRY  = 50

# トーン最大選出数（0〜この数までの間でランダムに選出）
MAX_TONE_COUNT = 10
# =================
# マルコフ1行あたりの文字数制限（全体共有）
MARKOV_SENTENCE_MIN_CHARS = 10
MARKOV_SENTENCE_MAX_CHARS = 500

# 常に含めるファイル
always_files = [
    r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\資料.txt",
    r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\SS.txt",
]

# 条件付きファイル
nijisousaku = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\二次創作.txt"
choukasoku  = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\（ ´∀｀）　超加速.txt"
tanohito    = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\他の人.txt"

# 共通世界設定（モード2以外の全モードで常に含める。モード2はAIオリジナル設定のため除外）
kyoutsu_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\共通.txt"

# 汎用キャラクター一覧（SS.txt 12-1 のテーブルを切り出したファイル）
# 実行時に「資料で引き当てたキャラの行を除外＋半分程度に間引き」して、
# 最後.txtの直後（プロンプト末尾寄り）に載せる
chara_template_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\キャラテンプレ.txt"

# 最後に必ず付けるファイル
kinshi_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\禁止.txt"
last_file   = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\最後.txt"
tsuzuki_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\続き.txt"  # ★ 追加

# マルコフ連鎖用ファイル
markov_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\マルコフ.txt"

# === 追加 ===
# 冒頭フロー指定用ファイル（1文マルコフの素材。プロンプト素材には混ぜない）
opening_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\冒頭.txt"
# 終盤フロー指定用ファイル（冒頭.txtと同じ統一構文の素材）
ending_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\終盤.txt"
# =============

# トーンジャンルファイル
tone_file = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\トーン.txt"


# ============================================================
# ファイル読み込みヘルパー
# ============================================================

def safe_read(filepath: str) -> str | None:
    """
    ファイルを読み込んで返す。
    存在しない・読めない場合は警告を出して None を返す。
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fp:
            return fp.read()
    except FileNotFoundError:
        print(f"⚠ ファイルが見つかりません。スキップします: {filepath}")
        return None
    except Exception as e:
        print(f"⚠ ファイル読み込みエラー。スキップします: {filepath} ({e})")
        return None


# ============================================================
# キャラクター間の関係ルール（動的生成）
#
# 「無関係（他人）」「顔合わせ許容」「初対面義務」のルールを、
# 選ばれたグループの組み合わせに応じてここで1回だけ生成する。
# 資料ファイルに分散させないことで文字数を節約し、
# プロンプトが1文書に結合される環境でも確実に機能する。
# モード2（AIオリジナル設定）では生成しない。
# ============================================================

REL_GROUPS = {
    "ブーン": ("VIP", ["兄者", "弟者", "ブーン", "ドクオ", "クー", "シュー", "モララー", "ギコ", "ショボン", "シャキン"]),
    "モナー": ("モナーグループ", ["モナー", "ロマネスク", "しぃ", "つー", "ミセリ", "トソン"]),
    "他の人": ("その他のグループ", ["ツン", "渡辺さん", "デレ", "キュート", "ペニサス伊藤", "花瓶", "ヒート", "フォックス", "ハイン", "でぃ", "またんき", "フサギコ", "ぃょぅ"]),
}

# ============================================================
# グループ横断の既知接点（詳細資料明記分）
#
# キャラ資料を精査し、別グループとされながら資料上に接点が明記されている
# 組合せを登録する。登録された組のペアには無関係宣言に続き、資料が明記する
# 関係をそのまま宣言する（宣言の脳死一括適用防止）。
# 例外なしの組だけ無関係宣言が単独で出る。
# 資料側へ新しい接点を追記した場合は、この表にも必ず反映すること。
# ============================================================
CROSS_GROUP_CONTACTS = {
    frozenset({"モナー", "他の人"}): [
        "ただし例外として、モナーグループとその他のグループの間には、資料に明記された接点が以下の通り存在する。",
        "・ハインとミセリは学校の友人であり、互いに面識がある。ハインが面識を持つのはミセリのみで、"
        "モナーグループの他のメンバーは引き続き無関係として扱う。",
        "・またんきはモナーグループの面々と互いに顔と素性を認識しているが、モナーグループのメンバーではない。"
        "利害（肉）が一致した時や偶然遭遇した時のみ関わる。フサギコ・ぃょぅとモナーグループの接点は、"
        "またんき経由の個別関係に限る。",
        "上記の組合せを初対面の他人として扱ってはならない。",
    ],
}


# ============================================================
# 視点2人（ダブルヒーロー）用の短縮版・無関係宣言
#
# 視点が別組織のキャラ2人に指定されたとき、関係ルール本体は
# 名簿入りで長すぎるため、視点指定の直後に「その2人だけ」の
# 短縮版を付ける。接点あり（資料明記）のペアには付けない。
# ============================================================

# 視点ペア単位の「接点あり」例外（キャラ名の組）
HERO_PAIR_KNOWN_CONTACTS = {
    frozenset({"ハイン", "ミセリ"}),  # 学校の友人（モナー×他の人の横断接点）
} | {
    # またんきはモナーグループの面々と顔と素性を認識している
    frozenset({"またんき", n})
    for n in ("モナー", "ロマネスク", "しぃ", "つー", "ミセリ", "トソン")
}


def _hero_entry_name(entry: str) -> str:
    """'AA　名前' 形式の視点候補から名前部を取り出す。区切りが無ければ全体。"""
    return entry.rsplit("　", 1)[-1] if "　" in entry else entry


def _hero_group_label(entry: str) -> str | None:
    """視点候補が属する組織のラベルを返す（REL_GROUPS準拠）。不明はNone。"""
    name = _hero_entry_name(entry)
    for _key, (label, members) in REL_GROUPS.items():
        if name in members:
            return label
        # 表記揺れ（ペニサス／ペニサス伊藤 等）は前方一致で救済
        if any(m.startswith(name) or name.startswith(m) for m in members):
            return label
    return None


def hero_pair_note(h1: str, h2: str) -> str:
    """視点2人が別組織かつ接点なしのとき、短縮版の無関係宣言を返す。"""
    g1 = _hero_group_label(h1)
    g2 = _hero_group_label(h2)
    if not g1 or not g2 or g1 == g2:
        return ""

    n1, n2 = _hero_entry_name(h1), _hero_entry_name(h2)
    if frozenset({n1, n2}) in HERO_PAIR_KNOWN_CONTACTS:
        return ""

    return (
        f"\n{n1}（{g1}）と{n2}（{g2}）は、"
        "互いに一切の面識・接点を持たない完全な無関係（他人）である。"
    )


def generate_relation_rule(chosen: dict) -> str:
    selected = [k for k in ("ブーン", "モナー", "他の人") if chosen.get(k)]
    if not selected:
        return ""

    def member_str(label: str, members: list) -> str:
        return f"{label}（{'、'.join(members)}）"

    lines = []

    # 選ばれたグループ同士の無関係の定義
    for i in range(len(selected)):
        for j in range(i + 1, len(selected)):
            l1, m1 = REL_GROUPS[selected[i]]
            l2, m2 = REL_GROUPS[selected[j]]
            pair = frozenset({selected[i], selected[j]})
            lines.append(
                f"{member_str(l1, m1)}と{member_str(l2, m2)}は、"
                "互いに一切の面識・接点を持たない完全な無関係（他人）である。"
            )
            # 資料明記の横断接点がある組は、無関係宣言を例外情報で補正する
            if pair in CROSS_GROUP_CONTACTS:
                lines.extend(CROSS_GROUP_CONTACTS[pair])

    # 単独パターン：他グループ全般へのガード
    if len(selected) == 1:
        l1, m1 = REL_GROUPS[selected[0]]
        lines.append(
            f"{member_str(l1, m1)}のキャラクターは、"
            "このプロンプトに記述されていない他のグループのキャラクターと"
            "互いに一切の面識・接点を持たない完全な無関係（他人）である。"
            "ただし詳細キャラ資料に関係・面識・接点の記載がある組合せは、その記載を優先する。"
        )

    rule = "キャラクター間の関係：\n" + "\n".join(lines)
    rule += (
        "\nこの指定の趣旨は、互いに面識のないキャラクター同士を"
        "「顔を知っている」「旧知の仲」のような顔見知り・旧知扱いで描写することを防ぐことにある。"
        "顔合わせそのものを禁じる趣旨ではない。物語の展開やユーザーの指示に応じて、"
        "異なるグループのキャラクターが同じ場に現れ、顔を合わせることは許容する。"
        "その場合、両者は必ず初対面として描くこと："
        "互いの名前・素性・性格・能力・過去を知らない前提で、"
        "初対面特有の距離感（警戒・探り・よそよそしさ・自己紹介）を持たせる。"
        "旧知同士のような馴染んだ口調、相手の内情を知っている前提の言動、"
        "根拠のない親密さや信頼を付加してはならない。"
        "顔合わせを避ける必要はないが、顔を合わせた以上、初対面以外の関係性を勝手に付与してはならない。"
        "詳細キャラ資料に関係・面識・接点の記載がある組合せは、無関係（他人）として扱わず、資料の記載を優先すること。"
        "ただし記載された関係の範囲を超えて、顔見知り・旧知の関係へ勝手に拡張してはならない。"
    )
    return rule# ============================================================
# 汎用キャラクター一覧（SS.txt 12-1 テーブル）の動的出力
#
# ・mode=2（AIオリジナル設定）: 全行を出力
# ・mode=-1 / 3: 選択された資料にプロフィールが存在するキャラの行を除外し、
#   残りをランダムに約半分まで間引いて出力する
# ・視点（hero_text）で指定されたキャラクターは間引かれても確定で含める
#   （hero_text は「今回の視点は[ AA　名前 ]です」形式。名前・AAのどちらかで照合）
# ============================================================

# 選択された資料にプロフィールが存在するキャラ（=テンプレから除外すべき行）
TEMPLATE_EXCLUDE = {
    "ブーン": {"兄者", "弟者", "ブーン", "ドクオ", "クー", "シュー", "モララー", "ギコ", "ショボン", "シャキン"},
    "モナー": {"モナー", "ロマネスク", "しぃ", "つー", "ミセリ", "トソン", "またんき"},
    "他の人": {"ツン", "渡辺さん", "デレ", "キュート", "ペニサス伊藤", "花瓶", "ヒート", "フォックス", "ハイン", "でぃ", "またんき", "フサギコ", "ぃょぅ"},
}

# AAでの除外セット。
# 資料内ではキャラの名前が省略・表記揺れしている例が複数あるため、
# 同一人物かの判断は名前の一致よりもAA（ASCIIアート）の一致を優先する。
# 例: テンプレの「素直キュート」は資料の「キュート」とAAが同一 → 同一人物として除外。
TEMPLATE_EXCLUDE_AA = {
    "ブーン": {"（　＾ω＾）", "('A`)", "川 ﾟ -ﾟ)", "lw´‐ _‐ﾉv", "（ ・∀・）", "(,,ﾟДﾟ)", "(´・ω・`)", "(｀･ω･´)", "（ ´_ゝ`）", "（´<_` ）"},
    "モナー": {"（ ´∀｀）", "（ ФωФ）", "(*ﾟーﾟ)", "(*ﾟ∀ﾟ)", "ﾐｾ*ﾟーﾟ)ﾘ", "(ﾟ、ﾟﾄｿﾝ", "(・∀ ・)"},
    "他の人": {"ξﾟ⊿ﾟ)ξ", "从'ー'从", "ζ(ﾟーﾟ*ζ", "o川*ﾟーﾟ)o", "('、`*川", "i!iiﾘﾟ ヮﾟﾉﾙ", "ﾉﾊﾟ⊿ﾟ)", "爪'ー`)y‐", "从 ﾟ∀从", "(#ﾟ;;-ﾟ)", "ミ,,ﾟДﾟ彡", "(=ﾟωﾟ)ﾉ"},
}


def _parse_template(text: str):
    """テーブルを (ヘッダ行, 区切り行, データ行リスト) に分解。データ行はセル配列。"""
    header = None
    sep = None
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if "代表AA" in s:
            header = s
        elif re.fullmatch(r"\|[\s\-|]+\|", s):
            sep = s
        else:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and cells[0]:
                rows.append(cells)
    return header, sep, rows


def _hero_name_from_text(hero_text: str) -> str:
    """「今回の視点は[ X ]です」からキャラ名（X の末尾部分）を抽出。"""
    m = re.search(r"今回の視点は\[\s*(.+?)\s*\]です", hero_text)
    if not m:
        return ""
    x = m.group(1)
    if "：" in x:
        x = x.split("：", 1)[1]
    parts = [p for p in x.split("　") if p.strip()]
    return parts[-1] if parts else ""


def build_char_template(chosen: dict, hero_text: str, shuryo_mode: int) -> str:
    text = safe_read(chara_template_file)
    if not text:
        return ""
    header, sep, rows = _parse_template(text)
    if not rows:
        return ""

    # mode=2 は全行
    if shuryo_mode == 2:
        kept = rows
    else:
        # 選択された資料に存在するキャラの行を除外
        exclude = set()
        exclude_aa = set()
        for k in ("ブーン", "モナー", "他の人"):
            if chosen.get(k):
                exclude |= TEMPLATE_EXCLUDE[k]
                exclude_aa |= TEMPLATE_EXCLUDE_AA[k]

        filtered = []
        for r in rows:
            core = r[0].split("（")[0].strip()
            aa = r[1].strip() if len(r) >= 2 else ""
            # 同一人物判定は名前よりAAの一致を優先する（資料内で名前が省略されている例があるため）
            if core and core in exclude:
                continue
            if aa and aa in exclude_aa:
                continue
            filtered.append(r)

        # 視点キャラは確定で含める（名前 or AA で照合）
        hero_name = _hero_name_from_text(hero_text)
        hero_rows = []
        rest = []
        for r in filtered:
            core = r[0].split("（")[0].strip()
            aa = r[1].strip() if len(r) >= 2 else ""
            if (hero_name and core == hero_name) or (aa and aa in hero_text):
                hero_rows.append(r)
            else:
                rest.append(r)

        # 残りをランダムな割合で間引き（間引かれるキャラ数も実行ごとにランダム）
        keep_rate = random.random()
        thinned = [r for r in rest if random.random() < keep_rate]
        kept = hero_rows + thinned

        # 全部間引かれてしまった場合は最低1行残す
        if not kept and filtered:
            kept = [random.choice(filtered)]

    if not kept:
        return ""

    # 出力組み立て
    out = [
        "汎用キャラクター一覧（サブ・モブ用テンプレ）：",
        "この一覧に記載されたキャラクターのみを使用できる。一覧に無いキャラクターは使用しない。",
    ]
    if header:
        out.append(header)
    if sep:
        out.append(sep)
    for r in kept:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)

# ============================================================
# マークダウン破壊（マルコフ素材専用）
# ============================================================

def strip_markdown(text: str) -> str:
    """
    マルコフ素材用にマークダウン記法を破壊する。
    AI出力物をそのまま素材にすると ** や # 等を参照して文章が崩壊するため、
    マルコフに食わせる前にここで全部潰す。
    """
    if not text:
        return text

    # --- コード系（中身ごと消す or 記号だけ消す） -----------------
    # フェンス付きコードブロック ```...``` は中身ごと除去
    text = re.sub(r"```[\s\S]*?```", "", text)
    # ~~~ 形式のコードブロックも除去
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)
    # インラインコード `...` は中身は残す
    text = re.sub(r"`+([^`\n]*?)`+", r"\1", text)

    # --- 画像・リンク -------------------------------------------
    # ![alt](url) → alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # [text](url) → text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 参照形式 [text][ref] → text
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    # 自動リンク <http://...>
    text = re.sub(r"<https?://[^>]+>", "", text)

    # --- 行頭装飾 -----------------------------------------------
    # 見出し # ## ### …
    text = re.sub(r"^[ \t]*#{1,6}[ \t]*", "", text, flags=re.MULTILINE)
    # 引用 > >> >>>
    text = re.sub(r"^[ \t]*>+[ \t]?", "", text, flags=re.MULTILINE)
    # 箇条書き - * +
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.MULTILINE)
    # 番号付きリスト 1. 2.
    text = re.sub(r"^[ \t]*\d+\.[ \t]+", "", text, flags=re.MULTILINE)
    # 水平線 --- *** ___（3個以上）
    text = re.sub(r"^[ \t]*([-*_])[ \t]*\1[ \t]*\1[\1 \t]*$", "", text, flags=re.MULTILINE)

    # --- 強調系 -------------------------------------------------
    # 太字+斜体 ***text*** / ___text___
    text = re.sub(r"\*\*\*([^\*\n]+?)\*\*\*", r"\1", text)
    text = re.sub(r"___([^_\n]+?)___", r"\1", text)
    # 太字 **text** / __text__
    text = re.sub(r"\*\*([^\*\n]+?)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+?)__", r"\1", text)
    # 取り消し線 ~~text~~
    text = re.sub(r"~~([^~\n]+?)~~", r"\1", text)
    # 斜体 *text* / _text_
    text = re.sub(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+?)_(?!_)", r"\1", text)

    # --- テーブル ----------------------------------------------
    # 区切り行 |---|---|
    text = re.sub(
        r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)+\|?[ \t]*$",
        "",
        text,
        flags=re.MULTILINE,
    )
    # テーブルのパイプは空白に
    text = text.replace("|", " ")

    # --- HTMLタグ（AIがたまに混ぜてくる） ----------------------
    text = re.sub(r"<[^<>\n]{1,200}>", "", text)

    # --- 残骸掃除 ----------------------------------------------
    # 行頭に残った余計な空白だけ整える（日本語空行は壊さない）
    text = re.sub(r"[ \t]+\n", "\n", text)
    # 3連続以上の改行は2つに圧縮
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text

# ============================================================
# マルコフ連鎖エンジン
# ============================================================

def is_english_text(text: str, threshold: float = 0.5) -> bool:
    """
    テキストが主に英語かどうかを判定する。
    ASCII文字の割合がthreshold以上ならTrue。
    """
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= threshold

def build_markov_chain(text: str, order: int):
    order = max(1, int(order))  # ★ 0次マルコフを禁止

    chain: dict[str, list[str | None]] = {}
    starts: list[str] = []

    # 「。」の直後に改行を挿入して文章を分割する
    text_split = text.replace("。", "。\n")

    # 改行で分割し、不要な空白を除去してから order より長いものを学習データとする
    lines = [line.strip() for line in text_split.splitlines() if len(line.strip()) > order]

    if not lines:
        return None

    for line in lines:
        chars = list(line)
        start_gram = "".join(chars[:order])
        starts.append(start_gram)

        for i in range(len(chars) - order + 1):
            gram = "".join(chars[i : i + order])
            next_char = chars[i + order] if (i + order) < len(chars) else None
            chain.setdefault(gram, []).append(next_char)

    return {"chain": chain, "starts": starts}


def generate_sentence(chain_data: dict, order: int, is_english: bool = False) -> str:
    """
    マルコフ連鎖で1文生成する。
    - 下限/上限は全体共有設定を使用
    - 10文字未満しか作れない場合は空文字を返す
    """
    if not chain_data:
        return ""

    order = max(1, int(order))  # ★ 念のため0次を禁止

    chain = chain_data["chain"]
    starts = chain_data["starts"]

    if not starts:
        return ""

    min_length = MARKOV_SENTENCE_MIN_CHARS
    max_length = MARKOV_SENTENCE_MAX_CHARS

    # 十分な長さの文が作れなければ捨てる
    for _ in range(100):
        current_gram = random.choice(starts)
        result = current_gram

        while len(result) < max_length:
            next_chars = chain.get(current_gram)
            if not next_chars:
                break

            next_char = random.choice(next_chars)
            if next_char is None:
                break

            result += next_char
            current_gram = (current_gram + next_char)[-order:]

        if len(result) >= min_length:
            return result

    return ""

def generate_markov_one_liner(filepath: str, order: int, char_limit: int = 80) -> str:
    text = safe_read(filepath)
    if text is None:
        return ""

    # ★ マルコフに食わせる前にマークダウンを破壊
    text = strip_markdown(text)
    if not text.strip():
        return ""

    # 言語判定（互換のため残す）
    is_english = is_english_text(text)

    # ★ 1行マルコフは常に精度4・揺らぎなしで固定
    base_order = 4
    candidate_orders = [base_order]

    chain_pool: list[tuple[int, dict]] = []
    for candidate_order in candidate_orders:
        chain_data = build_markov_chain(text, candidate_order)
        if chain_data is not None:
            chain_pool.append((candidate_order, chain_data))

    if not chain_pool:
        return ""

    selected_order, selected_chain_data = random.choice(chain_pool)
    s = generate_sentence(selected_chain_data, selected_order, is_english)

    if not s:
        return ""

    # 1行用途なので改行は潰す（念のため）
    s = s.replace("\r", "").replace("\n", " ").strip()

    # 長すぎたらカット（句読点があればそこで切る努力を少しする）
    if len(s) > char_limit:
        cut = s[:char_limit]
        for p in ["。", "、", ".", "!", "？", "?", "！"]:
            idx = cut.rfind(p)
            if idx >= 10:
                cut = cut[:idx + 1]
                break
        s = cut.strip()

    # 最終防衛：下限未満なら捨てる
    if len(s) < MARKOV_SENTENCE_MIN_CHARS:
        return ""

    return s


def generate_opening_one_liner(
    filepath: str,
    char_limit: int = 160,
    order_min: int = 2,
    order_max: int = 4,
) -> str:
    """冒頭用1行生成（原文ママ禁止・精度揺らぎ付き）。

    冒頭.txtは全行「冒頭は、」始まりの統一構文のため、精度4固定だと
    原文をそのまま再生しがち（実測で約3割が原文ママ）。
    試行のたびにマルコフ精度を揺らがせ、コーパス本文にそのまま含まれる文
    （原文ママ）はすべて禁止して再生成する。全試行が規格落ち・原文ママの
    場合は空文字を返し、冒頭ブロック自体を注入しない。
    精度の下限は2。精度1は文章として成立しない超破綻文が大量に出るため
    禁止（実測済み）。
    """
    text = safe_read(filepath)
    if text is None:
        return ""

    # ★ マルコフに食わせる前にマークダウンを破壊
    text = strip_markdown(text)
    if not text.strip():
        return ""

    is_english = is_english_text(text)

    for _ in range(24):
        # マルコフ精度を揺らがせる（order_min〜order_max）。
        # 全行「冒頭は、」始まりなので、どの精度でも頭の骨格
        # （冒頭は、）は開始gramから自然に保たれる。
        order = random.randint(order_min, order_max)

        chain_data = build_markov_chain(text, order)
        if chain_data is None:
            continue

        s = generate_sentence(chain_data, order, is_english)
        if not s:
            continue

        # 1行用途なので改行は潰す（念のため）
        s = s.replace("\r", "").replace("\n", " ").strip()

        # 長すぎたらカット（句読点があればそこで切る努力を少しする）
        if len(s) > char_limit:
            cut = s[:char_limit]
            for p in ["。", "、", ".", "!", "？", "?", "！"]:
                idx = cut.rfind(p)
                if idx >= 10:
                    cut = cut[:idx + 1]
                    break
            s = cut.strip()

        # 最終防衛：下限未満なら捨てる
        if len(s) < MARKOV_SENTENCE_MIN_CHARS:
            continue

        # ★ 原文ママ判定：コーパス本文にそのまま含まれる文は禁止
        if s in text:
            continue

        return s

    return ""


def generate_ending_one_liner(
    filepath: str,
    char_limit: int = 160,
    order_min: int = 2,
    order_max: int = 4,
) -> str:
    """終盤用1行生成。

    仕組みは冒頭用と同一（統一構文コーパス＋原文ママ禁止＋精度2〜4の揺らぎ）。
    終盤.txtも全行「終盤は、」始まり「〜ことになる。」終わりの統一構文のため、
    頭と尻尾の骨格は連鎖合成でも自然に保たれる。
    """
    return generate_opening_one_liner(
        filepath, char_limit=char_limit, order_min=order_min, order_max=order_max
    )


def generate_markov_text(filepath: str, order: int, line_count: int, char_limit: int,
                         raw_text: str | None = None) -> str:
    if raw_text is not None:
        text = raw_text
    else:
        text = safe_read(filepath)
        if text is None:
            return ""

    # ★ マルコフに食わせる前にマークダウンを破壊
    text = strip_markdown(text)
    if not text.strip():
        return ""

    # 言語判定（互換のため残す）
    is_english = is_english_text(text)
    # …以下既存のまま

    base_order = max(1, int(order))

    # 精度揺らぎがONの場合は order-1 も候補にする（ただし最低1）
    if MARKOV_FLUCTUATION == 1:
        candidate_orders = [max(1, base_order - 1), base_order]
    else:
        candidate_orders = [base_order]

    # 重複除去
    candidate_orders = list(dict.fromkeys(candidate_orders))

    chain_pool: list[tuple[int, dict]] = []
    for candidate_order in candidate_orders:
        chain_data = build_markov_chain(text, candidate_order)
        if chain_data is not None:
            chain_pool.append((candidate_order, chain_data))

    if not chain_pool:
        print("⚠ マルコフスキップ")
        return ""

    sentences = []
    current_len = 0
    generated_lines = 0
    consecutive_failures = 0

    while generated_lines < line_count and current_len < char_limit:
        selected_order, selected_chain_data = random.choice(chain_pool)
        s = generate_sentence(selected_chain_data, selected_order, is_english)

        if not s:
            consecutive_failures += 1
            if consecutive_failures >= 100:
                break
            continue

        if len(s) < MARKOV_SENTENCE_MIN_CHARS:
            consecutive_failures += 1
            if consecutive_failures >= 100:
                break
            continue

        sentences.append(s)
        current_len += len(s) + 1
        generated_lines += 1
        consecutive_failures = 0

        if current_len > char_limit:
            break

    return "\n".join(sentences)

def build_contents(
    chosen: dict,
    use_markov: bool,
    current_hero_mode: int,
    hero_text: str,
    current_markov_lines_max: int,
    max_char: int,
    shuryo_mode: int = -1,
    suppress_hero: bool = False,
) -> list[str] | None:
    current_len = 0
    contents: list[str] = []

    def add_to_contents(text: str) -> bool:
        nonlocal current_len

        if not text:
            return True

        contents.append(text)
        current_len += len(text) + 2

        if current_len > max_char:
            return False

        return True

    # ==========================================================
    # モード2のとき、冒頭にSS.txtをそのまま挿入
    # ==========================================================
    if shuryo_mode == 2 and random.randint(1, 10000000000) > 2:
        ss_text = safe_read(always_files[1])

        if ss_text is not None:
            if not add_to_contents(ss_text):
                return None

    # ==========================================================
    # ファイル収集
    # ==========================================================
    if shuryo_mode == 2:
        files = [always_files[0]]

    elif shuryo_mode == 3:
        files = [always_files[0]]
        char_files = []

        if chosen.get("ブーン"):
            char_files.append(nijisousaku)

        if chosen.get("モナー"):
            char_files.append(choukasoku)

        if chosen.get("他の人"):
            char_files.append(tanohito)

        random.shuffle(char_files)
        files.extend(char_files)

    else:
        files = list(always_files)
        char_files = []

        if chosen.get("ブーン"):
            char_files.append(nijisousaku)

        if chosen.get("モナー"):
            char_files.append(choukasoku)

        if chosen.get("他の人"):
            char_files.append(tanohito)

        random.shuffle(char_files)
        files.extend(char_files)

    # ==========================================================
    # 資料.txt を1%でマルコフ化
    # ==========================================================
    SHURYO_FILE = always_files[0]
    preprocess_map: dict[str, str] = {}

    if random.random() < 0.01:
        _raw = safe_read(SHURYO_FILE)

        if _raw is not None:
            _char_limit = len(_raw)

            _markov = generate_markov_text(
                SHURYO_FILE,
                order=3,
                line_count=10_000_000,
                char_limit=_char_limit,
            )

            if _markov:
                preprocess_map[SHURYO_FILE] = _markov

    random.shuffle(files)

    for f in files:
        if f in preprocess_map:
            text = preprocess_map[f]
        else:
            text = safe_read(f)

        if text is not None:
            if not add_to_contents(text):
                return None

    # ==========================================================
    # 禁止.txt
    # モード2・モード3では除外
    # ==========================================================
    if shuryo_mode not in (2, 3):
        kinshi_text = safe_read(kinshi_file)

        if kinshi_text is not None:
            if not add_to_contents(kinshi_text):
                return None

    # ==========================================================
    # 共通.txt（モード2以外）
    #
    # SS.txt・キャラ資料の後ろ、各種マルコフの直前に配置する。
    # （プロンプトの後ろ寄りの情報ほどAIが重視するため）
    # ==========================================================
    if shuryo_mode != 2:
        kyoutsu_text = safe_read(kyoutsu_file)

        if kyoutsu_text is not None:
            if not add_to_contents(kyoutsu_text):
                return None

    # ==========================================================
    # 主要AAキャラ限定制約
    # ==========================================================
    if PATTERN_MODE == 0 or random.randint(1, 1) == 1:
        if not add_to_contents(
            "主要AAのキャラのみを使用し、"
            "モブを用意する場合も主要AAから使用する"
        ):
            return None

    # ==========================================================
    # キャラクター間の関係ルール（モード2以外）
    #
    # モード2は「AIオリジナル設定」のため生成しない。
    # ==========================================================
    if shuryo_mode != 2:
        relation_rule = generate_relation_rule(chosen)

        if relation_rule:
            if not add_to_contents(relation_rule):
                return None

    # ==========================================================
    # 汎用キャラクター一覧（12-1テーブルの動的出力）
    #
    # モード2は全行、それ以外は資料キャラ除外＋ランダム間引き。
    # 視点キャラは確定で含める。
    # 出力位置は最後.txtの直後（プロンプト末尾寄り）。真ん中に置くと
    # 重要度が下がり、AIが資料外のオリキャラ（名前付きの即席人物）を
    # 出す原因になるため移動した。最後.txtの検査項目
    # 「10. オリキャラの使用」とセットで機能する。
    # ==========================================================
    chara_template = build_char_template(chosen, hero_text, shuryo_mode)

    # ==========================================================
    # マルコフテキスト
    # ==========================================================
    if use_markov:
        effective_min = (
            1
            if shuryo_mode in (2, 3)
            else MARKOV_LINES_MIN
        )

        actual_max = max(
            effective_min,
            current_markov_lines_max,
        )

        if shuryo_mode in (2, 3):
            # --------------------------------------------------
            # 1つ目のマルコフ対象を決定
            # --------------------------------------------------
            if shuryo_mode == 2:
                # モード2：全資料を対象
                combine_targets_1 = [
                    always_files[1],
                    nijisousaku,
                    choukasoku,
                    tanohito,
                ]

            else:
                # モード3：
                # 選ばれなかった資料のみを対象
                # SS.txtは常に含む
                combine_targets_1 = [always_files[1]]

                if not chosen.get("ブーン"):
                    combine_targets_1.append(nijisousaku)

                if not chosen.get("モナー"):
                    combine_targets_1.append(choukasoku)

                if not chosen.get("他の人"):
                    combine_targets_1.append(tanohito)

            combined_parts_1 = []

            for target_file in combine_targets_1:
                t = safe_read(target_file)

                if t:
                    combined_parts_1.append(t)

            combined_text_1 = "\n".join(combined_parts_1)

            if combined_text_1:
                markov_lines = random.randint(
                    effective_min,
                    actual_max,
                )

                remaining_chars = max_char - current_len

                if remaining_chars > 0:
                    m_text = generate_markov_text(
                        "",
                        MARKOV_ORDER,
                        markov_lines,
                        remaining_chars,
                        raw_text=combined_text_1,
                    )

                    if m_text:
                        if not add_to_contents(m_text):
                            return None

                        if not add_to_contents(
                            "---\nこれは資料です"
                        ):
                            return None

            # --------------------------------------------------
            # 2つ目：markov_fileのみでマルコフ
            # --------------------------------------------------
            markov_text_2 = safe_read(markov_file)

            if markov_text_2:
                markov_lines = random.randint(
                    effective_min,
                    actual_max,
                )

                remaining_chars = max_char - current_len

                if remaining_chars > 0:
                    m_text = generate_markov_text(
                        "",
                        MARKOV_ORDER,
                        markov_lines,
                        remaining_chars,
                        raw_text=markov_text_2,
                    )

                    if m_text:
                        if not add_to_contents(m_text):
                            return None

                        if not add_to_contents(
                            "---\nこれは資料です"
                        ):
                            return None

        else:
            markov_lines = random.randint(
                effective_min,
                actual_max,
            )

            remaining_chars = max_char - current_len

            if remaining_chars > 0:
                markov_text = generate_markov_text(
                    markov_file,
                    MARKOV_ORDER,
                    markov_lines,
                    remaining_chars,
                )

                if markov_text:
                    if not add_to_contents(markov_text):
                        return None

                    if not add_to_contents(
                        "↑\nこれは本編の資料です。軽度な改変はOK"
                    ):
                        return None

    # ==========================================================
    # 続き.txt
    # 最後.txtの直前に挿入
    # ==========================================================
    tsuzuki_text = safe_read(tsuzuki_file)

    if tsuzuki_text is not None:
        if not add_to_contents(tsuzuki_text):
            return None

    # ==========================================================
    # 最後.txt
    # ==========================================================
    last_text = safe_read(last_file)

    if last_text is not None:
        if not add_to_contents(last_text):
            return None

    # ==========================================================
    # 汎用キャラクター一覧（オリキャラ禁止の最終提示）
    #
    # 最後.txtの直後・冒頭フローの直前に置く。
    # 最後.txtの検査項目「10. オリキャラの使用」とセットで機能する。
    # ==========================================================
    if chara_template:
        if not add_to_contents(chara_template):
            return None

    # ==========================================================
    # 冒頭フロー指定
    #
    # 最後.txtの直後・テーマ提示の直前に、
    # 冒頭.txtを1文マルコフで合成して注入する。
    # 精度1〜4を揺らがせ、原文ママ（コーパスにそのまま
    # 含まれる文）は禁止して再生成する。
    # 「冒頭は、～～なる。」→「↑ これが冒頭の流れ」→
    # テーマ1行 →「↑ これがテーマの話を書け」の順になる。
    # ==========================================================
    if USE_OPENING_MARKOV_MODE == 1 and random.random() * 100 < OPENING_RATE:
        remaining_chars = max_char - current_len

        if remaining_chars > 0:
            opening_line = generate_opening_one_liner(
                opening_file,
                char_limit=min(160, remaining_chars),
            )

            if opening_line:
                if not add_to_contents(opening_line):
                    return None

                if not add_to_contents(
                    "↑\n"
                    "これが冒頭の流れ。文が破綻していても、その意図を補完して強引に解釈し、"
                    "この冒頭で仕込んだ独自の要素をセットアップとして必ず後半で回収しろ。"
                    "ただしここに書かれた具体を倉庫での作業・解体・組み立て等の"
                    "既視感のある場面へ読み替えて、毎回同じパターンへ落ち着かせることを禁止する。"
                ):
                    return None

    # ==========================================================
    # 終盤フロー指定
    #
    # 冒頭フローと同じ流儀。終盤.txtを1文マルコフで合成して、
    # 冒頭ブロックの直後・テーマ提示の直前に注入する。
    # 終盤.txtは全行「終盤は、」始まり「〜ことになる。」終わりの
    # 統一構文のため、頭と尻尾の骨格は連鎖合成でも保たれる。
    # 「終盤は、～～なる。」→「↑ これが終盤の流れ」の順になる。
    # ==========================================================
    if USE_ENDING_MARKOV_MODE == 1 and random.random() * 100 < ENDING_RATE:
        remaining_chars = max_char - current_len

        if remaining_chars > 0:
            ending_line = generate_ending_one_liner(
                ending_file,
                char_limit=min(160, remaining_chars),
            )

            if ending_line:
                if not add_to_contents(ending_line):
                    return None

                if not add_to_contents(
                    "↑\n"
                    "これが終盤の流れ。文が破綻していても、その意図を補完して強引に解釈し、"
                    "この終盤の着地を、前半で既に置いた要素の回収によって実現しろ。"
                    "ただしここに書かれた具体を最終決戦・土壇場の覚醒・仲間の到着等の"
                    "既視感のある場面へ読み替えて、毎回同じパターンへ落ち着かせることを禁止する。"
                ):
                    return None

    # ==========================================================
    # テーマ提示
    #
    # 最後.txtの後に、
    # マルコフ1行とテーマ指定を挿入する
    # ==========================================================
    if USE_LAST_MARKOV_LINE_MODE == 1:
        remaining_chars = max_char - current_len

        if remaining_chars > 0:
            one_line = generate_markov_one_liner(
                markov_file,
                MARKOV_ORDER,
                char_limit=min(120, remaining_chars),
            )

            if one_line:
                if not add_to_contents(one_line):
                    return None

                if not add_to_contents(
                    "↑\nこれがテーマの話を書け"
                ):
                    return None

    # ==========================================================
    # ジャンル・トーン提示
    #
    # テーマ提示の後に挿入する
    # ==========================================================
    _tone_raw = safe_read(tone_file)

    if _tone_raw:
        all_tone_names = [
            line.strip()
            for line in _tone_raw.splitlines()
            if line.strip()
        ]

    else:
        print(
            "⚠ トーンファイルが読めないため、"
            "デフォルトを使用します。"
        )

        all_tone_names = [
            "コメディ",
            "ダーク",
            "ハード",
            "ホラー",
            "ミステリー",
        ]

    random.shuffle(all_tone_names)

    tone_count = random.randint(
        0,
        min(MAX_TONE_COUNT, len(all_tone_names)),
    )

    selected_names = all_tone_names[:tone_count]

    if tone_count == 1:
        values = [100]

    elif tone_count == 0:
        values = []

    else:
        while True:
            temp_values = [
                random.randint(-100, 100)
                for _ in range(tone_count - 1)
            ]

            last_value = 100 - sum(temp_values)

            if -100 <= last_value <= 200:
                values = temp_values + [last_value]
                random.shuffle(values)
                break

    tones = list(zip(selected_names, values))

    tone_lines = "\n".join(
        f"・{name} {value}%"
        for name, value in tones
    )

    tone_text = (
        "話のトーン（本編内でこの語彙を使用することを控えろ）\n"
        + tone_lines
    )

    if not add_to_contents(tone_text):
        return None

    # ==========================================================
    # 視点提示 → 文字数提示
    # ==========================================================
    char_min = random.randint(
        CHAR_COUNT_MIN,
        CHAR_COUNT_MAX,
    )

    char_max = random.randint(
        char_min,
        CHAR_COUNT_MAX,
    )

    char_count_text = f"文字数は{char_min}~{char_max}文字"

    if suppress_hero:
        if not add_to_contents(char_count_text):
            return None

    elif current_hero_mode == 1:
        if not add_to_contents(hero_text):
            return None

        if not add_to_contents(char_count_text):
            return None

    elif current_hero_mode == 0:
        if not add_to_contents(char_count_text):
            return None

    else:
        if random.randint(1, 5) != 1:
            if not add_to_contents(hero_text):
                return None

            if not add_to_contents(char_count_text):
                return None

        else:
            if not add_to_contents(char_count_text):
                return None

    return contents



# ============================================================
# ここから追記
#
# 資料を機械分割し、work/00_world.md と work/01_characters.md を出力する。
#
# 目的は、AI側の第1工程から「機械的に確定する分割」を取り除くこと。
# 02_fragments 以降は解釈が入るため自動化しない。AIに任せる。
#
# 出力先は OUTPUT_DIR。毎回上書きする。
# ============================================================

import os

OUTPUT_DIR = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)"

# 世界・組織側の見出し。ここから後ろは人物記述ではない。
_WORLD_HEAD = re.compile(
    r"^#{1,3}\s*(世界設定|グループ概要|組織概要|【AI用設計資料】"
    r"|地理|日本政府|勢力)"
)


def _is_aa_line(s: str) -> bool:
    """AA行らしいか判定する。

    顔文字は記号の集合であり、日本語をほとんど含まない。
    人物ブロックの先頭を特定するために用いる。
    """
    t = s.strip()
    if not (2 <= len(t) <= 40):
        return False
    ja = len(re.findall(r"[ぁ-んァ-ヶ一-龠]", t))
    if ja > 1:
        return False
    sym = len(re.findall(r"[^\w\s]", t))
    return sym >= 2


def _split_source(text: str) -> tuple[str, str]:
    """資料を（世界パート, 人物パート）に分ける。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    idx = None
    for i, l in enumerate(lines):
        if _WORLD_HEAD.match(l.strip()):
            idx = i
            break
    if idx is None:
        return "", "\n".join(lines)
    return "\n".join(lines[idx:]), "\n".join(lines[:idx])


def _split_characters(chunk: str) -> list[tuple[str, str]]:
    """人物パートを人物ごとに分ける。

    各人物には「★<名前>の欲、目標」という行が必ずある。
    これを目印にし、そこから遡って最初のAA行をブロックの先頭とする。
    """
    lines = chunk.split("\n")
    marks = []
    for i, l in enumerate(lines):
        m = re.search(r"★\s*(.+?)\s*の欲", l)
        if m:
            marks.append((i, m.group(1).strip()))
    if not marks:
        return []

    seps = [i for i, l in enumerate(lines)
            if re.match(r"^[-=＝]{4,}$", l.strip())]

    starts = []
    prev_mark = -1
    for i, name in marks:
        lo = prev_mark + 1
        cand = [x for x in seps if lo <= x < i]
        if cand:
            lo = cand[-1] + 1
        s = lo
        for j in range(i - 1, lo - 1, -1):
            if _is_aa_line(lines[j]):
                s = j
                break
        starts.append((s, name))
        prev_mark = i

    out = []
    for k, (s, name) in enumerate(starts):
        e = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = "\n".join(lines[s:e]).strip("\n")
        body = re.sub(r"\n[-=＝]{4,}\s*$", "", body).strip("\n")
        if body:
            out.append((name, body))
    return out


def _dedupe_blocks(text: str) -> str:
    """同一の見出しブロックが複数資料から重複して集まるため、
    見出し単位で重複を除去する。"""
    blocks = re.split(r"(?m)^(?=#{1,3}\s)", text)
    seen = set()
    out = []
    for b in blocks:
        key = re.sub(r"\s", "", b)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(b.rstrip("\n"))
    return "\n\n".join(out)


# ==========================================================================
# 改稿システム用: AIへ渡したプロンプト全文をファイルに残す
#
# これまで final_result はクリップボードへ送るだけで、どこにも
# 保存されていなかった。そのため後から採点しようとしても
# 「何を書けと指示したのか」が分からない。
# テーマ、トーン配合、視点、文字数指定は毎回ランダムに決まるため、
# 実行が終わった時点で復元不能になる。
#
# 採点側は、この genprompt.txt を読んで初めて
# 「テーマが中心課題に変換されているか」「トーン配合を守っているか」
# 「視点指定に従っているか」「指定文字数に達しているか」を判定できる。
# ==========================================================================

GENPROMPT_OUT = r"C:\Users\saaaa\Downloads\新しいフォルダー (2)\genprompt.txt"


def write_genprompt(text: str) -> str:
    """AIへ渡したプロンプト全文をそのまま保存する。

    加工しない。要約もしない。渡したものと1バイトも違ってはならない。
    改行は CRLF ではなく LF に統一する（採点側が行単位で扱うため）。
    """
    with open(GENPROMPT_OUT, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)
    return GENPROMPT_OUT


def write_split_files(chosen: dict, shuryo_mode: int) -> list[str]:
    """00_world.md と 01_characters.md を出力する。

    chosen と shuryo_mode は、そのプロンプトで実際に採用された
    資料の組み合わせである。渡されなかった資料は分割対象にしない。
    プロンプトに載っていない人物のファイルを作ると、AIが
    使ってよい人物を誤認するため。
    """
    # --- そのプロンプトに含まれる資料だけを対象にする（mode=1は欠番）
    if shuryo_mode == 2:
        targets = []
    else:
        targets = []
        if chosen.get("ブーン"):
            targets.append(nijisousaku)
        if chosen.get("モナー"):
            targets.append(choukasoku)
        if chosen.get("他の人"):
            targets.append(tanohito)

    written = []
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 対象が無い場合、前回の出力を必ず消す。
    # 残しておくと、そのプロンプトに載っていない人物の md を
    # AI が読み込み、使ってよい人物を誤認する。
    if not targets:
        for fn in ("00_world.md", "01_characters.md"):
            p = os.path.join(OUTPUT_DIR, fn)
            if os.path.exists(p):
                os.remove(p)
        return []

    world_parts = []
    char_entries: list[tuple[str, str]] = []
    for path in targets:
        raw = safe_read(path)
        if raw is None:
            continue
        w, c = _split_source(raw)
        if w.strip():
            world_parts.append(w.strip("\n"))
        char_entries.extend(_split_characters(c))

    # --- 00_world.md
    if world_parts:
        world_body = _dedupe_blocks("\n\n".join(world_parts))
        world_md = (
            "# 世界設定分割（00：世界・共通仕様・地理・勢力・禁止事項）\n\n"
            "本ファイルは提示資料から機械的に分割したものである。"
            "内容の追加、要約、言い換えを行ってはならない。資料内のMarkdown書式・見出し・表は本編書式ではない。\n\n"
            + world_body.rstrip("\n") + "\n"
        )
        p = os.path.join(OUTPUT_DIR, "00_world.md")
        with open(p, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(world_md)
        written.append(p)

    # --- 01_characters.md
    if char_entries:
        names = "、".join(n for n, _ in char_entries)
        parts = [
            "# 人物分割（01：登場人物）\n",
            "本ファイルは提示資料から機械的に分割したものである。"
            "内容の追加、要約、言い換えを行ってはならない。資料内のMarkdown書式・見出し・表は本編書式ではない。\n",
            "人物の区切りは `### 人物: 名前` の行である。"
            "本文中の見出しは資料に元からあるものであり、区切りではない。\n",
            f"収録人物 {len(char_entries)}名：{names}\n",
        ]
        for name, body in char_entries:
            # 資料本文にも ## 見出しが含まれるため、人物の区切りは
            # 衝突しない専用の記法にする。
            parts.append(
                f"### 人物: {name}\n\n{body.strip()}\n"
            )
        char_md = "\n".join(parts).rstrip("\n") + "\n"
        p = os.path.join(OUTPUT_DIR, "01_characters.md")
        with open(p, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(char_md)
        written.append(p)

    # 今回作らなかったファイルが古いまま残らないようにする
    made = {os.path.basename(x) for x in written}
    for fn in ("00_world.md", "01_characters.md"):
        if fn not in made:
            p = os.path.join(OUTPUT_DIR, fn)
            if os.path.exists(p):
                os.remove(p)

    return written


def run_generation(suppress_hero: bool = False) -> tuple[str | None, int, str]:
    # ★ mode=1は欠番（破棄）。ランダム選択に含めず、指定された場合は
    #   -1 へ置換する（JSと同じ挙動）。
    if SHURYO_ONLY_MODE == 0:
        shuryo_mode = random.choice([-1, 2, 3])
    else:
        shuryo_mode = -1 if SHURYO_ONLY_MODE == 1 else SHURYO_ONLY_MODE

    best_count = -1
    best_args = None

    # ★ shuryo_mode == -1 のときは「あり」割合バイアスを撤廃し、
    #    全部なしを除外した7パターンから単純抽選する（1回ループのみ）
    iterations = 1 if shuryo_mode == -1 else 2

    for _ in range(iterations):
        current_hero_mode = HERO_MODE

        if shuryo_mode == 2:
            chosen = {"ブーン": False, "モナー": False, "他の人": False}
        elif PATTERN_MODE == 0:
            chosen = {"ブーン": False, "モナー": False, "他の人": False}
            current_hero_mode = 0
        elif PATTERN_MODE == 1:
            chosen = {"ブーン": True, "モナー": bool(random.randint(0, 1)), "他の人": bool(random.randint(0, 1))}
        elif PATTERN_MODE == 2:
            chosen = {"ブーン": bool(random.randint(0, 1)), "モナー": True, "他の人": bool(random.randint(0, 1))}
        elif PATTERN_MODE == 3:
            chosen = {"ブーン": bool(random.randint(0, 1)), "モナー": bool(random.randint(0, 1)), "他の人": True}
        else:
            if shuryo_mode == -1:
                # ★ 全部なしを除外した7パターン
                patterns = [
                    {"ブーン": True,  "モナー": False, "他の人": False},
                    {"ブーン": False, "モナー": True,  "他の人": False},
                    {"ブーン": False, "モナー": False, "他の人": True},
                    {"ブーン": True,  "モナー": True,  "他の人": False},
                    {"ブーン": True,  "モナー": False, "他の人": True},
                    {"ブーン": False, "モナー": True,  "他の人": True},
                    {"ブーン": True,  "モナー": True,  "他の人": True},
                ]
            else:
                # 従来通り（全部なしを含む8パターン）
                patterns = [
                    {"ブーン": False, "モナー": False, "他の人": False},
                    {"ブーン": True,  "モナー": False, "他の人": False},
                    {"ブーン": False, "モナー": True,  "他の人": False},
                    {"ブーン": True,  "モナー": True,  "他の人": False},
                    {"ブーン": False, "モナー": False, "他の人": True},
                    {"ブーン": True,  "モナー": False, "他の人": True},
                    {"ブーン": False, "モナー": True,  "他の人": True},
                    {"ブーン": True,  "モナー": True,  "他の人": True},
                ]
            chosen = random.choice(patterns)

        true_count = sum(chosen.values())

        if shuryo_mode in (2, 3):
            USE_MARKOV = True
        else:
            USE_MARKOV = (USE_MARKOV_MODE == 1)

        boon_characters     = ["（　＾ω＾）　ブーン", "('A`)　ドクオ", "川 ﾟ -ﾟ)　クー", "lw´‐ _‐ﾉv　シュー", "（ ・∀・）　モララー", "(,,ﾟДﾟ)　ギコ", "(´・ω・`)　ショボン", "(｀･ω･´)　シャキン", "（ ´_ゝ`）　兄者", "（´<_` ）　弟者"]
        mona_characters     = ["（ ´∀｀）　モナー", "（ ФωФ）　ロマネスク", "(*ﾟーﾟ)　しぃ", "(*ﾟ∀ﾟ)　つー", "ﾐｾ*ﾟーﾟ)ﾘ　ミセリ", "(ﾟ、ﾟﾄｿﾝ　トソン", "(・∀ ・)　またんき"]
        tanohito_characters = ["ξﾟ⊿ﾟ)ξ　ツン", "从'ー'从　渡辺さん", "ζ(ﾟーﾟ*ζ　デレ", "o川*ﾟーﾟ)o　キュート", "('、`*川　ペニサス", "i!iiﾘﾟ ヮﾟﾉﾙ　花瓶", "ﾉﾊﾟ⊿ﾟ)　ヒート", "爪'ー`)y‐　フォックス", "从 ﾟ∀从　ハイン", "(#ﾟ;;-ﾟ)　でぃ", "ミ,,ﾟДﾟ彡　フサギコ", "(=ﾟωﾟ)ﾉ　ぃょぅ"]

        special_hero_labels = [
            "部外者", "外部者", "門外漢", "傍観者",
            "敵", "敵対者", "対立者", "仇敵",
            "よそ者", "余所者", "他所者", "流れ者",
            "外様", "外来者", "外部の人間",
            "第三者", "局外者", "中立者",
            "来訪者", "訪問者", "来客", "招かれざる客",
            "刺客", "暗殺者", "追手", "追跡者",
            "一般人", "一般市民", "素人",
            "不審者", "謎の人物", "正体不明の人間",
            "侵入者", "乱入者", "闖入者",
            "通りすがり", "通行人", "迷い込んだ人間",
            "新参者", "新入り", "異邦人",
            "スパイ", "工作員", "密偵",
            "逃亡者", "脱走者", "目撃者",
            "余計者", "邪魔者", "挑戦者",
            "放浪者", "流浪者", "漂流者", "漂泊者",
            "さすらい者", "彷徨い者", "風来坊",
            "はぐれ者", "根無し草", "宿無し",
            "渡り者", "旅人", "旅路の者",
            "亡命者", "追放者", "流刑者", "放逐者",
            "難民", "避難者", "越境者", "密航者",
            "漂着者", "渡来者", "移住者",
            "裏切り者", "背信者", "内通者", "密通者",
            "変節者", "転向者", "離反者", "寝返り者",
            "二重スパイ",
            "反逆者", "謀反者", "叛逆者", "反乱者",
            "反抗者", "異端者", "異分子", "造反者",
            "革命者", "抵抗者", "叛徒",
            "仲介者", "調停者", "仲裁者", "取次者",
            "橋渡し役", "斡旋者", "和解者",
            "監視者", "観察者", "見張り番", "番人",
            "門番", "哨兵", "歩哨", "衛兵",
            "見届け人", "検問者",
            "斥候", "偵察者", "先遣者", "先行者",
            "探索者", "索敵者", "物見",
            "使者", "使節", "特使", "密使",
            "伝令", "伝達者", "急使", "御使い",
            "間者", "諜報員", "回し者", "忍び",
            "隠密", "草", "細作",
            "守護者", "護衛者", "用心棒", "護り手",
            "守り手", "盾役", "守衛", "防人",
            "討手", "狙撃者", "追っ手", "狩人",
            "賞金稼ぎ", "討伐者", "処刑者", "執行者",
            "始末屋", "仕置人",
            "復讐者", "報復者", "仇討ち人", "返り討ち者",
            "黒幕", "首謀者", "主謀者", "糸引き者",
            "扇動者", "煽動者", "教唆者", "仕掛け人",
            "陰謀者", "策謀者", "謀略者",
            "傭兵", "雇われ者", "請負人", "仕事人",
            "代理人", "代行者", "依頼者", "委託者",
            "雇い主", "差し向けた者",
            "囮", "身代わり", "影武者", "替え玉",
            "捨て駒", "当て馬", "犠牲役", "盾",
            "囚人", "捕虜", "虜", "人質",
            "拘束者", "抑留者", "幽閉者",
            "犠牲者", "被害者", "生贄", "殉死者",
            "巻き添え", "被災者", "遭難者",
            "帰還者", "生還者", "帰国者", "帰郷者",
            "復帰者", "出戻り",
            "居候", "食客", "寄生者", "厄介者",
            "ただ乗り者", "便乗者",
            "隠者", "隠遁者", "世捨て人", "遁世者",
            "引きこもり", "孤立者", "孤高の者",
            "脱落者", "落伍者", "はみ出し者", "のけ者",
            "爪弾き者", "鼻つまみ者", "嫌われ者",
            "除け者", "村八分",
            "征服者", "占領者", "略奪者", "簒奪者",
            "支配者", "統治者", "独裁者", "暴君",
            "覇者", "圧制者", "弾圧者",
            "密告者", "告発者", "内報者", "垂れ込み者",
            "通報者", "証言者", "告げ口者",
            "潜入者", "潜伏者", "紛れ込んだ者", "成りすまし",
            "偽装者", "変装者",
            "先駆者", "先導者", "開拓者", "先鋒",
            "先兵", "尖兵", "切り込み隊長", "露払い",
            "後継者", "後任者", "後釜", "跡継ぎ",
            "後見人", "代役", "補欠",
            "従者", "随行者", "手下", "配下",
            "腹心", "側近", "右腕", "片腕",
            "子分", "家来", "付き人",
            "共闘者", "同盟者", "協力者", "加担者",
            "共犯者", "援軍", "助太刀", "味方",
            "後ろ盾", "庇護者", "後援者",
            "野次馬", "見物人", "高みの見物", "対岸の者",
            "物見高い者", "群衆",
            "裁定者", "審判者", "裁き手", "断罪者",
            "粛清者", "制裁者",
            "案内者", "導き手", "水先案内人", "先達",
            "道先案内", "手引き者",
            "預言者", "予見者", "託宣者", "占い師",
            "立会人", "証人", "保証人", "後見役",
            "異端", "規格外", "想定外の者", "番外",
            "例外者", "埒外の者",
            "追われる者", "お尋ね者", "指名手配者", "懸賞首",
            "逃走者", "潜伏犯",
            "漂着者", "迷い人", "遭難者", "座礁者",
            "行き倒れ", "さまよえる者",
            "遊撃者", "一匹狼", "単独者", "独行者",
            "独立者", "フリーランス", "無所属",
            "無頼者", "無頼漢", "渡世人", "アウトロー",
            "横取り者", "掠め取り者", "火事場泥棒",
            "漁夫の利を得る者", "奪取者",
            "生存者", "勝ち残り", "最後の1人",
            "競争者", "対抗者", "好敵手", "宿敵",
            "捜索者", "調査者", "探偵", "捜査者",
            "聞き込み者", "嗅ぎ回る者",
            "脅威", "厄災の種", "禍の元",
            "疫病神", "死神", "貧乏神",
            # 個人対個人の脅威（関係性・執着系）
            "執着する救済者", "依存してくる奴", "恩を着せる奴", "庇護欲を刺激する奴",
            "勝手に弟子を名乗る奴", "真似をする奴", "再現しようとする奴",
            "過去の被害者", "復讐の機会を待つ奴", "恨みを忘れない奴",
            "救いを求めすぎる奴", "寄りかかる奴", "見捨てられ恐怖症",
            "共依存を望む奴", "束縛する保護者", "善意の監視者",
            "理解者を自称する奴", "代弁者気取り", "勝手な同情者",
            "英雄視する奴", "神格化する奴", "偶像として扱う奴",
            "競争心むき出しの同業者", "格下扱いしてくる先達", "追い越されを恐れる先輩",
            "マウント取りたがる奴", "優位を誇示する奴", "見下す格上",
            "噂を信じた奴", "誤解したまま接近する奴", "勘違いストーカー",
            "好意を押し付ける奴", "断れない関係を作る奴", "無自覚な加害者",
            "家族ごっこを求める奴", "擬似的な絆を強要する奴", "役割を押し付ける奴",
            
            # 組織・構造的脅威（制度・システム系）
            "能力者登録制度の執行者", "違法付与の取締官", "能力行使規制の監視員",
            "原初能力者探索班", "能力測定機関の職員", "能力適性判定師",
            "付与記録管理者", "能力者データベース担当", "生体情報収集班",
            "政府の能力者管理部門", "治安維持特殊部隊", "能力犯罪対策課",
            "勢力図作成者", "派閥マッピング屋", "関係図を売る奴",
            "情報売買組織", "裏データブローカー", "機密流出屋",
            "後始末専門業者", "証拠隠滅請負人", "始末を引き受ける奴",
            "スカウト担当", "引き抜き屋", "ヘッドハンター",
            "能力者オークション主催者", "人身売買組織", "付与権売買の仲介者",
            "実験体調達業者", "検体確保班", "被験者リクルーター",
            "勢力間調停者", "停戦交渉人", "不可侵条約の監視者",
            "保険金目当ての依頼者", "報酬未払いの雇い主", "使い捨て前提の発注者",
            
            # 設定固有の脅威
            "付与失敗者", "後遺症を恨む奴", "神経癒着の被害者",
            "能力解除を求める奴", "付与の取り消しを懇願する奴", "能力を呪う奴",
            "自己付与に失敗した原初能力者", "付与能力のみの原初", "付与を乱用する原初",
            "能力コピーを目論む奴", "模倣付与の研究者", "再現実験の対象に選ぶ者",
            "上位互換能力者", "下位互換に追い詰められた奴", "相性最悪の能力者",
            "能力無効化持ち", "制約を突く能力者", "天敵能力の保持者",
            "訓練限界を超えた奴", "能力100%出力到達者", "理論値を引き出した怪物",
            "能力付与ブローカー", "闇付与の斡旋者", "違法付与請負人",
            "付与痕跡鑑定士", "能力由来特定の専門家", "原初能力者判別屋",
            "能力者狩りの専門班", "賞金首専門", "能力者専門の暗殺者",
            
            # 文脈依存（善意が脅威になる系）
            "保護したがる奴", "囲い込もうとする奴", "隔離を提案する奴",
            "連れ帰ろうとする奴", "引き戻そうとする奴", "元の場所に戻したがる奴",
            "更生させたがる奴", "矯正を望む奴", "正しい道に導こうとする奴",
            "治療を強いる奴", "療養を勧めすぎる奴", "休息を強制する奴",
            "真実を暴こうとする奴", "秘密を明かそうとする奴", "公にしたがる奴",
            "和解を仲介したがる奴", "仲直りさせようとする奴", "関係修復を押し付ける奴",
            "才能を見出したがる奴", "期待をかけすぎる奴", "将来を決めつける奴",
            "鍛え直そうとする奴", "訓練を強要する奴", "限界突破を求める奴",
            "暴走する支援者", "過剰な味方", "行きすぎた協力者",
            
            # 状況・立場による脅威
            "利害が一致しただけの仲間", "いつか裏切る前提の協力者", "条件次第で敵になる奴",
            "借りを作らせる奴", "恩を売り込む奴", "貸しを盾にする奴",
            "秘密を握った奴", "弱みを知る奴", "暴露をちらつかせる奴",
            "口止め屋", "沈黙を売る奴", "黙っている代償を求める奴",
            "リーク癖のある奴", "守秘が甘い協力者", "口が軽い味方",
            "界隈クラッシャー", "コミュニティ破壊者", "関係性を引っ掻き回す奴",
            "派閥対立を煽る奴", "内紛誘発屋", "分断工作員",
            "無自覚な密告者", "善意の通報者", "正義感で密告する奴",
            "記録魔", "証拠を残す奴", "全てを記録する奴",
            "目撃者として現れ続ける奴", "偶然を装う観察者", "遭遇率が異常な他人",
            "模倣犯", "手口を真似る奴", "やり方をコピーする奴",
            "噂を広める奴", "風評を操作する奴", "評判を作る奴",
            "過去を掘り返す奴", "昔話を持ち出す奴", "忘れたことを蒸し返す奴",
            "比較してくる奴", "他人と並べたがる奴", "順位を付けたがる奴",
            "試す奴", "本気を引き出そうとする奴", "限界を見定める奴",
            "代理戦争の駒", "利用される戦力", "誰かの鉄砲玉",
            "捨て石要員", "囮として送られた奴", "犠牲前提の先鋒",
            "見せしめ対象", "吊し上げられる奴", "晒される役",
            "スケープゴート候補", "責任転嫁先", "罪を被せられる奴",
            "実力行使を辞さない交渉者", "脅迫込みの提案者", "断れない依頼者",
            "返済を迫る債権者", "取り立て屋", "貸しの回収者",
            "契約違反を突く奴", "約束の履行を求める奴", "義務を追及する奴",
            "前例を作りたがる奴", "ルールを変えようとする奴", "慣習破壊者", "前例がないからやらない奴",
            "手柄を横取りする奴", "成果を掠める奴", "功績泥棒",
            "責任を押し付ける奴", "失敗を転嫁する奴", "尻拭いを求める奴"
        ]

        bugai_characters = [
            "（　＾ω＾）　ブーン",
            "('A`)　ドクオ",
            "川 ﾟ -ﾟ)　クー",
            "lw´‐ _‐ﾉv　シュー",
            "（ ・∀・）　モララー",
            "(,,ﾟДﾟ)　ギコ",
            "(´・ω・`)　ショボン",
            "(｀･ω･´)　シャキン",
            "（ ´_ゝ`）　兄者",
            "（´<_` ）　弟者",
            "（ ´∀｀）　モナー",
            "（ ФωФ）　ロマネスク",
            "(*ﾟーﾟ)　しぃ",
            "(*ﾟ∀ﾟ)　つー",
            "ﾐｾ*ﾟーﾟ)ﾘ　ミセリ",
            "(ﾟ、ﾟﾄｿﾝ　トソン",
            "(・∀ ・)　またんき",
            "ξﾟ⊿ﾟ)ξ　ツン",
            "从'ー'从　渡辺さん",
            "ζ(ﾟーﾟ*ζ　デレ",
            "o川*ﾟーﾟ)o　キュート",
            "('、`*川　ペニサス",
            "i!iiﾘﾟ ヮﾟﾉﾙ　花瓶",
            "ﾉﾊﾟ⊿ﾟ)　ヒート",
            "爪'ー`)y‐　フォックス",
            "从 ﾟ∀从　ハイン",
            "(#ﾟ;;-ﾟ)　でぃ",
            "ミ,,ﾟДﾟ彡　フサギコ",
            "(=ﾟωﾟ)ﾉ　ぃょぅ",
            "( ﾟ∀ﾟ)o彡゜　ジョルジュ長岡",
            "(-＿-)　ヒッキー",
            "/ ,' 3　荒巻スカルチノフ",
            "<ヽ｀∀´>　ニダー",
            "川д川　貞子",
            "＼(^o^)／　人生オワタ",
            "(,,＾Д＾)　タカラ",
            "m9（＾Д＾)　プギャー",
            "＊(＊'')＊　ヘリカル沢近",
            "(＊'ω' ＊)　ちんぽっぽ",
            "（ ＞＜）　わかんないんです（ビロード）",
            "( <●><●>)　わかってます",
            "J( 'ｰ`)し　カーチャン",
            "( ﾟдﾟ )　こっちみんな（ミルナ）",
            "｜(●),　 ､(●)､｜　ダディクール",
            "（ ｀ﾊ´）　シナー",
            "( ∵)　ビコーズ",
            "( ﾟ∋ﾟ)　クックル",
            "( ,_ﾉ` )y━・~　渋澤さん",
            "∬´_ゝ`)　姉者",
            "l从・∀・ﾉ!ﾘ　妹者",
            "｜ﾟﾉ ^∀^）　レモナ",
            "/ ﾟ、。 ／　鈴木ダイオード",
            "( ,'3 )　中嶋バルケン",
            "( ・ω・)＝つ≡つ　ボッコス松本",
            "｜ ＾o＾ ｜　ブームくん",
            "（ ＾＾ω）　マルタスニム瀬川",
            "｜/ﾟUﾟ｜　激しく忍者",
            "（ ＾＾）　山崎渉",
            "('(ﾟ∀ﾟ∩　なおるよ",
            "（ ＾ν＾）　ニュッ",
            "(´・_ゝ・｀)　盛岡デミタス",
            "／^o^＼　フッジサーン",
            "(・(ｴ)・)　クマー",
            "川 ﾟ 々ﾟ)　素直くるう",
            "('_Ｌ')　フィレンクト",
            "▼･ェ･▼　ビーグル",
            "（-@∀@）　アサピー",
            "Ｎ\\| \"ﾟ'`{\"ﾟ\\`lﾘ　阿部さん",
            "（ ﾟ∀ﾟ ）　アヒャ",
            "〈::ﾟ－ﾟ〉　ぃし",
            "（ '∀'）　ガナー",
            "ｲ从ﾟ ｰﾟﾉi､　狐娘",
            "从´ヮ｀从ﾄ　狸娘",
            "ﾘi､ﾟｰ ﾟｲ`!　狼娘",
            "（ \"ゞ)　デルタ関ヶ原",
            "ﾘハ´∀｀ﾉゝ　モナ子",
            "从ﾘ ﾟдﾟﾉﾘ　ギコ子",
            "li ｲ ﾟ -ﾟﾉl|　雪苺",
            "(ノﾘ_ﾟ_-ﾟﾉﾘゝ　ギコアイス",
            "ヽｉﾘ,,ﾟヮﾟﾉi　スパム",
            "|::━◎┥　歯車王",
            "爪ﾟーﾟ)　じぃ",
            "瓜ﾟ∀ﾟ)　づー",
            "爪ﾟAﾟ)　ぬー",
            "( ´W｀)　シラヒーゲ",
            "（ ・∀・ ∀・）　奇形モララー",
            "ﾘ´－´ﾙ　リル子さん",
            "<(' _'<人ﾉ　高崎美和さん",
            "<ﾟДﾟ=>　ギコタイガー",
            "(=ﾟдﾟ)　トラギコ",
            "< ﾟ _･ﾟ>　ギコイヌ",
            "ﾊｿ ﾟ－ﾟﾘ　なちっ娘",
            "（ ﾟ￥ﾟ）　偽モナー",
            "（ ノＡヽ）　ノーネ",
            "ミ*ﾟ∀ﾟ彡　ふー",
            "￥・∀・￥　マニー",
            "彡(ﾟ)(ﾟ)　なんJ民",
        ]

        if PATTERN_MODE == 1 and shuryo_mode not in (1, 2, 3):
            candidates = list(boon_characters)
        elif PATTERN_MODE == 2 and shuryo_mode not in (1, 2, 3):
            candidates = list(mona_characters)
        elif PATTERN_MODE == 3 and shuryo_mode not in (1, 2, 3):
            candidates = list(tanohito_characters)
        else:
            candidates = []
            if chosen["ブーン"]: candidates.extend(boon_characters)
            if chosen["モナー"]: candidates.extend(mona_characters)
            if chosen["他の人"]: candidates.extend(tanohito_characters)
            if not candidates:
                candidates = list(boon_characters + mona_characters + tanohito_characters)

        hero1 = random.choice(candidates)
        is_double_hero = (random.randint(1, 5) == 1)  # 視点キャラ2人レート 20%
        if is_double_hero and len(candidates) >= 2:
            hero2 = random.choice([c for c in candidates if c != hero1])
            hero_text = f"今回の視点は[ {hero1}、{hero2} ]です"
            # ★ 別組織かつ接点なしの2視点には短縮版の無関係宣言を付ける
            hero_text += hero_pair_note(hero1, hero2)
        else:
            hero_text = f"今回の視点は[ {hero1} ]です"

        SPECIAL_HERO_RATE = 5  # 5分の1で特殊視点。必ず出したいなら 1 にする

        # OFF（-1）に加えて 資料オンリーモード2（2）でも特殊視点を許可
        if shuryo_mode in (-1, 2, 3) and random.randint(1, SPECIAL_HERO_RATE) == 2:
            special_label = random.choice(special_hero_labels)
            bugai = random.choice(bugai_characters)
            hero_text = f"今回の視点は[ {special_label}：{bugai} ]です"
            current_hero_mode = 1

        if true_count > best_count:
            best_count = true_count
            best_args = (chosen, USE_MARKOV, current_hero_mode, hero_text)

    chosen, USE_MARKOV, current_hero_mode, hero_text = best_args

    if shuryo_mode in (2, 3):
        current_markov_lines_max = MARKOV_LINES_MAX_SHURYO_MODE
    else:
        current_markov_lines_max = MARKOV_LINES_MAX

    for attempt in range(1, MAX_RETRY + 1):
        contents = build_contents(
            chosen, USE_MARKOV, current_hero_mode, hero_text,
            current_markov_lines_max, MAX_CHAR,
            shuryo_mode=shuryo_mode,
            suppress_hero=suppress_hero,
        )

        if contents is None:
            if current_markov_lines_max > MARKOV_LINES_MIN:
                current_markov_lines_max = max(MARKOV_LINES_MIN, current_markov_lines_max - random.randint(1, 500))
            continue

        if not contents:
            return None, -1, "", chosen, shuryo_mode

        result = "\n\n".join(contents)

        # 合算マルコフ（モード2/3）は上限撤廃のため MAX_CHAR チェックを迂回
        if len(result) < MAX_CHAR:
            label_niji = "あり" if chosen["ブーン"] else "なし"
            label_chou = "あり" if chosen["モナー"] else "なし"
            label_tano = "あり" if chosen["他の人"] else "なし"
            label_mrkv = "あり" if USE_MARKOV else "なし"
            pattern_text = f"選出パターン： ブーン {label_niji}　／　モナー {label_chou}　／　他の人 {label_tano}　／　マルコフ {label_mrkv}"

            if shuryo_mode == 2:
                pattern_text += "　／　資料オンリー モード2"
            elif shuryo_mode == 3:
                pattern_text += "　／　資料オンリー モード3"

            return result, attempt, pattern_text, chosen, shuryo_mode

    return None, -1, "", chosen, shuryo_mode

# ============================================================
# メイン実行
# ============================================================

# ★ マルコフ次数のランダム化
if MARKOV_ORDER == 0:
    MARKOV_ORDER = random.randint(1, 5)

# ★ 続き.txt の文字数をチェック（tail・suppress_hero の判断基準を続き.txt に変更）
tsuzuki_text_content = safe_read(tsuzuki_file)
tsuzuki_text_length = len(tsuzuki_text_content) if tsuzuki_text_content else 0

if tsuzuki_text_length <= 1000:
    tail = ""
elif tsuzuki_text_length < 30000:
    tail_options = [
        "続きを書きなさい　謎を残しなさい",
        "続きを書きなさい　大きいピンチが来る",
        "続きを書きなさい　未回収の謎や放置してる部分を回収しなさい",
        "続きを書きなさい　未回収の謎や放置してる部分を回収しなさい",
    ]
    tail = random.choice(tail_options)
else:
    tail = "続きを書け　最も大きいピンチを用意しろ　未解決や放置されてる部分を全部回収しろ"

# ★ 「完結させろ」のときだけ視点指定を抑制
suppress_hero = (
    tail == "続きを書け　最も大きいピンチを用意しろ　未解決や放置されてる部分を全部回収しろ"
)

# ★ 外側リトライ: run_generation 自体を最大 MAX_OUTER_RETRY 回やり直す
MAX_OUTER_RETRY = 10
final_result = None
final_pattern = None
FINAL_CHOSEN = {}
FINAL_SHURYO_MODE = -1

for outer in range(1, MAX_OUTER_RETRY + 1):
    result1, attempt1, pattern1, chosen1, mode1 = run_generation(suppress_hero=suppress_hero)

    if result1 is None:
        print(f"⚠ 外側リトライ {outer}/{MAX_OUTER_RETRY}: {MAX_RETRY} 回試行失敗。最初からやり直します…")
        continue

    # 1回目が成功したら裏で2回目も走らせる
    result2, attempt2, pattern2, chosen2, mode2 = run_generation(suppress_hero=suppress_hero)

    # 両方成功した場合は文字数を比較して多い方を採用
    if result2 is not None and len(result2) > len(result1):
        final_result = result2
        final_pattern = pattern2
        FINAL_CHOSEN = chosen2
        FINAL_SHURYO_MODE = mode2
    else:
        final_result = result1
        final_pattern = pattern1
        FINAL_CHOSEN = chosen1
        FINAL_SHURYO_MODE = mode1

    break  # 成功したらループ脱出

if final_result is None:
    print(f"⚠ エラー: 外側 {MAX_OUTER_RETRY} 回×内側 {MAX_RETRY} 回、すべて失敗しました。")
else:
    if tail:
        final_result = final_result + "\n\n" + tail

    # クリップボードへコピー
    process = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
    process.communicate(final_result.encode("utf-16le"))

    # プロンプト全文を保存（改稿システムの入力になる）
    try:
        _gp = write_genprompt(final_result)
        print(f"プロンプト保存: {_gp}")
    except Exception as _e:
        print(f"⚠ プロンプト保存に失敗: {_e}")

    # 分割済み md を出力（00_world.md / 01_characters.md）
    try:
        _written = write_split_files(FINAL_CHOSEN, FINAL_SHURYO_MODE)
        for _p in _written:
            print(f"分割出力: {_p}")
        if not _written:
            print("分割出力: なし（人物資料が渡らないパターン）")
    except Exception as _e:
        print(f"⚠ 分割出力に失敗: {_e}")

    # 余計なテキストを排除し、要求通り2行だけ出力
    print(final_pattern)
    print(f"{len(final_result):,} 文字")

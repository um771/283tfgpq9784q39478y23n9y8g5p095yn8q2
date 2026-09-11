"""
小説生成プロンプト ジェネレーター（Python版）
SS.html の JavaScript エンジンと同等の出力をする。

主な変更点（旧py → 新py）:
  - キャラ資料を9ファイル（二次創作・超加速・ラボ組・学校組・ホスト組・ツン・渡辺さん・ハイン・でぃ）に細分化
  - キャラ単位の優先度（29名を毎回シャッフル、所属txtを順次追加）
  - ブロックランダム順モード（shuffleBlocksMode）
  - 視点キャラ固定（fixedHero / group:◯◯）
  - 一人称視点指定レート（firstPersonRate）
  - SlotEngine（スロット辞書×文型フレーム直積合成）
  - SkeletonEngine（物語骨格カード→文章化）
  - 冒頭／終盤フロー指示文
  - キャラテンプレ提示数の制限（charTemplateMin/Max）
  - キャラブロック内シャッフル
  - ダブルヒーローの短縮版無関係宣言
  - 横断接点の9資料対応更新
"""

import re
import random
import subprocess
import os
import sys
import json
from typing import Any

# ============================================================
# パス自動判定
# ============================================================

def _get_base_dir() -> str:
    candidates = [
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
        "/home/user/uploads",
        "/home/user",
    ]
    for d in candidates:
        if os.path.exists(os.path.join(d, "SS.txt")) and os.path.exists(os.path.join(d, "マルコフ.txt")):
            return d
    for d in candidates:
        if os.path.exists(os.path.join(d, "SS.txt")):
            return d
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _get_base_dir()
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 設定
# ============================================================

# 資料オンリーモード（0=ランダム / -1=通常 / 2=モード2 / 3=モード3。1は欠番）
SHURYO_ONLY_MODE = 0

USE_MARKOV_MODE = 1
HERO_MODE = -1
USE_LAST_MARKOV_LINE_MODE = 1

# 冒頭/終盤フロー
USE_OPENING_MARKOV_MODE = 1
USE_ENDING_MARKOV_MODE = 1
OPENING_RATE = 50
ENDING_RATE = 50

# 骨格カード
SKELETON_RATE = 50

# キャラテンプレ提示数
CHAR_TEMPLATE_MIN = 12
CHAR_TEMPLATE_MAX = 40

# マルコフ連鎖パラメータ
MARKOV_ORDER = 0  # 0=ランダム(1〜5) / 1〜5=固定
MARKOV_LINES_MIN = 1
MARKOV_LINES_MAX = 1000
MARKOV_LINES_MAX_SHURYO_MODE = 1000
MARKOV_LINES_HARD_MAX = 1000
MARKOV_FLUCTUATION = 1

# 文字数指定
CHAR_COUNT_MIN = 9000
CHAR_COUNT_MAX = 20000

MAX_CHAR = 119_000
MAX_RETRY = 50
MAX_OUTER_RETRY = 10

# トーン最大選出数
MAX_TONE_COUNT = 10

# マルコフ1行あたりの文字数制限
MARKOV_SENTENCE_MIN_CHARS = 10
MARKOV_SENTENCE_MAX_CHARS = 500

# 特殊視点レート
SPECIAL_HERO_RATE = 20
DOUBLE_HERO_RATE = 20
NO_HERO_RATE = 20
FIRST_PERSON_RATE = 50

# ブロックランダム順モード（0=OFF / 1=ON）
SHUFFLE_BLOCKS_MODE = 0

# 視点キャラ固定（''=ランダム / キャラ名 / group:◯◯）
FIXED_HERO = ""

# 最低キャラ資料文字数
MIN_CHAR_MATERIAL_CHARS = 10000

# ファイルパス
always_files = [
    os.path.join(BASE_DIR, "資料.txt"),
    os.path.join(BASE_DIR, "SS.txt"),
]

nijisousaku_file = os.path.join(BASE_DIR, "二次創作.txt")
choukasoku_file = os.path.join(BASE_DIR, "超加速.txt")
lab_file = os.path.join(BASE_DIR, "ラボ組.txt")
school_file = os.path.join(BASE_DIR, "学校組.txt")
host_file = os.path.join(BASE_DIR, "ホスト組.txt")
tsun_file = os.path.join(BASE_DIR, "ツン.txt")
watanabe_file = os.path.join(BASE_DIR, "渡辺さん.txt")
hain_file = os.path.join(BASE_DIR, "ハイン.txt")
di_file = os.path.join(BASE_DIR, "でぃ.txt")

kyoutsu_file = os.path.join(BASE_DIR, "共通.txt")
chara_template_file = os.path.join(BASE_DIR, "キャラテンプレ.txt")
kinshi_file = os.path.join(BASE_DIR, "禁止.txt")
last_file = os.path.join(BASE_DIR, "最後.txt")
tsuzuki_file = os.path.join(BASE_DIR, "続き.txt")
markov_file = os.path.join(BASE_DIR, "マルコフ.txt")
tone_file = os.path.join(BASE_DIR, "トーン.txt")
opening_slot_file = os.path.join(BASE_DIR, "冒頭スロット.txt")
ending_slot_file = os.path.join(BASE_DIR, "終盤スロット.txt")

# ============================================================
# 9資料のキャラ定義
# ============================================================

CHAR_MATERIALS = [
    {"id": "nijisousaku", "label": "二次創作", "file": nijisousaku_file,
     "names": ["兄者", "弟者", "ブーン", "ドクオ", "クー", "シュー", "モララー", "ギコ", "ショボン", "シャキン"]},
    {"id": "choukasoku", "label": "超加速", "file": choukasoku_file,
     "names": ["モナー", "ロマネスク", "しぃ", "つー", "ミセリ", "トソン"]},
    {"id": "lab", "label": "ラボ組", "file": lab_file,
     "names": ["フォックス", "花瓶", "ヒート"]},
    {"id": "school", "label": "学校組", "file": school_file,
     "names": ["デレ", "キュート", "ペニサス"]},
    {"id": "host", "label": "ホスト組", "file": host_file,
     "names": ["またんき", "フサギコ", "ぃょぅ"]},
    {"id": "tsun", "label": "ツン", "file": tsun_file, "names": ["ツン"]},
    {"id": "watanabe", "label": "渡辺さん", "file": watanabe_file, "names": ["渡辺さん"]},
    {"id": "hain", "label": "ハイン", "file": hain_file, "names": ["ハイン"]},
    {"id": "di", "label": "でぃ", "file": di_file, "names": ["でぃ"]},
]

# キャラ→所属マテリアルの逆引き
def char_material_by_id(mid: str) -> dict | None:
    for m in CHAR_MATERIALS:
        if m["id"] == mid:
            return m
    return None

def char_material_label(mid: str) -> str:
    m = char_material_by_id(mid)
    return m["label"] if m else mid

# キャラ名→所属マテリアルID
def mat_id_for_hero_name(name: str) -> str | None:
    if not name:
        return None
    if name == "ペニサス伊藤":
        name = "ペニサス"
    if name == "都村トソン":
        name = "トソン"
    for m in CHAR_MATERIALS:
        if name in m["names"]:
            return m["id"]
    return None

# ============================================================
# キャラ・ラベルリスト（SS.html の NOVEL_DATA と同一）
# ============================================================

BOON_CHARACTERS = [
    "（　＾ω＾）　ブーン", "('A`)　ドクオ", "川 ﾟ -ﾟ)　クー", "lw´‐ _‐ﾉv　シュー",
    "（ ・∀・）　モララー", "(,,ﾟДﾟ)　ギコ", "(´・ω・`)　ショボン", "(｀･ω･´)　シャキン",
    "（ ´_ゝ`）　兄者", "（´<_` ）　弟者",
]

MONA_CHARACTERS = [
    "（ ´∀｀）　モナー", "（ ФωФ）　ロマネスク", "(*ﾟーﾟ)　しぃ", "(*ﾟ∀ﾟ)　つー",
    "ﾐｾ*ﾟーﾟ)ﾘ　ミセリ", "(ﾟ、ﾟﾄｿﾝ　トソン", "(・∀ ・)　またんき",
]

TANO_CHARACTERS = [
    "ξﾟ⊿ﾟ)ξ　ツン", "从'ー'从　渡辺さん", "ζ(ﾟーﾟ*ζ　デレ", "o川*ﾟーﾟ)o　キュート",
    "('、`*川　ペニサス", "i!iiﾘﾟ ヮﾟﾉﾙ　花瓶", "ﾉﾊﾟ⊿ﾟ)　ヒート", "爪'ー`)y‐　フォックス",
    "从 ﾟ∀从　ハイン", "(#ﾟ;;-ﾟ)　でぃ", "ミ,,ﾟДﾟ彡　フサギコ", "(=ﾟωﾟ)ﾉ　ぃょぅ",
]

SPECIAL_HERO_LABELS = [
    "部外者", "外部者", "門外漢", "傍観者", "敵", "敵対者", "対立者", "仇敵",
    "よそ者", "余所者", "他所者", "流れ者", "外様", "外来者", "外部の人間",
    "第三者", "局外者", "中立者", "来訪者", "訪問者", "来客", "招かれざる客",
    "刺客", "暗殺者", "追手", "追跡者", "一般人", "一般市民", "素人",
    "不審者", "謎の人物", "正体不明の人間", "侵入者", "乱入者", "闖入者",
    "通りすがり", "通行人", "迷い込んだ人間", "新参者", "新入り", "異邦人",
    "スパイ", "工作員", "密偵", "逃亡者", "脱走者", "目撃者",
    "余計者", "邪魔者", "挑戦者", "放浪者", "流浪者", "漂流者", "漂泊者",
    "さすらい者", "彷徨い者", "風来坊", "はぐれ者", "根無し草", "宿無し",
    "渡り者", "旅人", "旅路の者", "亡命者", "追放者", "流刑者", "放逐者",
    "難民", "避難者", "越境者", "密航者", "漂着者", "渡来者", "移住者",
    "裏切り者", "背信者", "内通者", "密通者", "変節者", "転向者", "離反者", "寝返り者",
    "二重スパイ", "反逆者", "謀反者", "叛逆者", "反乱者",
    "反抗者", "異端者", "異分子", "造反者", "革命者", "抵抗者", "叛徒",
    "仲介者", "調停者", "仲裁者", "取次者", "橋渡し役", "斡旋者", "和解者",
    "監視者", "観察者", "見張り番", "番人", "門番", "哨兵", "歩哨", "衛兵",
    "見届け人", "検問者", "斥候", "偵察者", "先遣者", "先行者",
    "探索者", "索敵者", "物見", "使者", "使節", "特使", "密使",
    "伝令", "伝達者", "急使", "御使い", "間者", "諜報員", "回し者", "忍び",
    "隠密", "草", "細作", "守護者", "護衛者", "用心棒", "護り手",
    "守り手", "盾役", "守衛", "防人", "討手", "狙撃者", "追っ手", "狩人",
    "賞金稼ぎ", "討伐者", "処刑者", "執行者", "始末屋", "仕置人",
    "復讐者", "報復者", "仇討ち人", "返り討ち者",
    "黒幕", "首謀者", "主謀者", "糸引き者", "扇動者", "煽動者", "教唆者", "仕掛け人",
    "陰謀者", "策謀者", "謀略者", "傭兵", "雇われ者", "請負人", "仕事人",
    "代理人", "代行者", "依頼者", "委託者", "雇い主", "差し向けた者",
    "囮", "身代わり", "影武者", "替え玉", "捨て駒", "当て馬", "犠牲役", "盾",
    "囚人", "捕虜", "虜", "人質", "拘束者", "抑留者", "幽閉者",
    "犠牲者", "被害者", "生贄", "殉死者", "巻き添え", "被災者", "遭難者",
    "帰還者", "生還者", "帰国者", "帰郷者", "復帰者", "出戻り",
    "居候", "食客", "寄生者", "厄介者", "ただ乗り者", "便乗者",
    "隠者", "隠遁者", "世捨て人", "遁世者", "引きこもり", "孤立者", "孤高の者",
    "脱落者", "落伍者", "はみ出し者", "のけ者", "爪弾き者", "鼻つまみ者", "嫌われ者",
    "除け者", "村八分", "征服者", "占領者", "略奪者", "簒奪者",
    "支配者", "統治者", "独裁者", "暴君", "覇者", "圧制者", "弾圧者",
    "密告者", "告発者", "内報者", "垂れ込み者", "通報者", "証言者", "告げ口者",
    "潜入者", "潜伏者", "紛れ込んだ者", "成りすまし", "偽装者", "変装者",
    "先駆者", "先導者", "開拓者", "先鋒", "先兵", "尖兵", "切り込み隊長", "露払い",
    "後継者", "後任者", "後釜", "跡継ぎ", "後見人", "代役", "補欠",
    "従者", "随行者", "手下", "配下", "腹心", "側近", "右腕", "片腕",
    "子分", "家来", "付き人", "共闘者", "同盟者", "協力者", "加担者",
    "共犯者", "援軍", "助太刀", "味方", "後ろ盾", "庇護者", "後援者",
    "野次馬", "見物人", "高みの見物", "対岸の者", "物見高い者", "群衆",
    "裁定者", "審判者", "裁き手", "断罪者", "粛清者", "制裁者",
    "案内者", "導き手", "水先案内人", "先達", "道先案内", "手引き者",
    "預言者", "予見者", "託宣者", "占い師", "立会人", "証人", "保証人", "後見役",
    "異端", "規格外", "想定外の者", "番外", "例外者", "埒外の者",
    "追われる者", "お尋ね者", "指名手配者", "懸賞首", "逃走者", "潜伏犯",
    "漂着者", "迷い人", "遭難者", "座礁者", "行き倒れ", "さまよえる者",
    "遊撃者", "一匹狼", "単独者", "独行者", "独立者", "フリーランス", "無所属",
    "無頼者", "無頼漢", "渡世人", "アウトロー", "横取り者", "掠め取り者", "火事場泥棒",
    "漁夫の利を得る者", "奪取者", "生存者", "勝ち残り", "最後の1人",
    "競争者", "対抗者", "好敵手", "宿敵", "捜索者", "調査者", "探偵", "捜査者",
    "聞き込み者", "嗅ぎ回る者", "脅威", "厄災の種", "禍の元", "疫病神", "死神", "貧乏神",
    "執着する救済者", "依存してくる奴", "恩を着せる奴", "庇護欲を刺激する奴",
    "勝手に弟子を名乗る奴", "真似をする奴", "再現しようとする奴",
    "過去の被害者", "復讐の機会を待つ奴", "恨みを忘れない奴",
    "救いを求めすぎる奴", "寄りかかる奴", "見捨てられ恐怖症",
    "共依存を望む奴", "束縛する保護者", "善意の監視者",
    "理解者を自称する奴", "代弁者気取り", "勝手な同情者",
    "英雄視する奴", "神格化する奴", "偶像として扱う奴",
    "保護したがる奴", "囲い込もうとする奴", "隔離を提案する奴",
    "連れ帰ろうとする奴", "引き戻そうとする奴", "元の場所に戻したがる奴",
    "更生させたがる奴", "矯正を望む奴", "正しい道に導こうとする奴",
    "治療を強いる奴", "療養を勧めすぎる奴", "休息を強制する奴",
]

BUGAI_CHARACTERS = BOON_CHARACTERS + MONA_CHARACTERS + TANO_CHARACTERS + [
    "( ﾟ∀ﾟ)o彡゜　ジョルジュ長岡", "(-＿-)　ヒッキー", "/ ,' 3　荒巻スカルチノフ",
    "<ヽ｀∀´>　ニダー", "川д川　貞子", "＼(^o^)／　人生オワタ", "(,,＾Д＾)　タカラ",
    "m9（＾Д＾)　プギャー", "＊(＊'')＊　ヘリカル沢近", "(＊'ω' ＊)　ちんぽっぽ",
]


# ============================================================
# ファイル読み込みヘルパー
# ============================================================

def safe_read(filepath: str) -> str | None:
    try:
        with open(filepath, "r", encoding="utf-8") as fp:
            return fp.read()
    except FileNotFoundError:
        print(f"⚠ ファイルが見つかりません: {filepath}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠ 読み込みエラー: {filepath} ({e})", file=sys.stderr)
        return None


# ============================================================
# ユーティリティ
# ============================================================

def num_or(v, fallback):
    """未設定・不正値のときは既定値へフォールバック"""
    if v is None or v == "":
        return fallback
    try:
        n = float(v)
    except (ValueError, TypeError):
        return fallback
    return max(0, min(100, n))


def int_or(v, fallback):
    if v is None or v == "":
        return fallback
    try:
        return max(1, int(v))
    except (ValueError, TypeError):
        return fallback


def norm_aa(s: str) -> str:
    """AA照合用の正規化"""
    if not s:
        return ""
    z = "（）［］｛｝＜＞｜"
    h = "()[]{}<>|"
    for a, b in zip(z, h):
        s = s.replace(a, b)
    return re.sub(r"[\s\u3000]", "", s)


# ============================================================
# SlotEngine（スロット辞書×文型フレーム直積合成）
# ============================================================

def _slot_parse_entry(line: str) -> dict:
    tokens = line.split()
    text_parts = []
    tags = []
    mutex = {}
    started = False
    for t in tokens:
        if not t:
            continue
        if t[0] in ("@", "^"):
            started = True
        if not started:
            text_parts.append(t)
            continue
        if t[0] == "@":
            tags.append(t[1:])
        elif t[0] == "^":
            kv = t[1:].split("=", 1)
            if len(kv) == 2:
                mutex[kv[0]] = kv[1]
    return {"text": " ".join(text_parts), "tags": tags, "mutex": mutex}


def _slot_parse_frame(line: str) -> list:
    parts = []
    last = 0
    for m in re.finditer(r"\{([^{}]+)\}", line):
        if m.start() > last:
            parts.append({"lit": line[last:m.start()]})
        spec = m.group(1)
        opt = False
        if spec.endswith("?"):
            opt = True
            spec = spec[:-1]
        segs = spec.split("@")
        name = segs.pop(0)
        need = segs
        segs2 = name.split("!")
        name = segs2[0]
        deny = segs2[1:]
        parts.append({"slot": name, "optional": opt, "need": need, "deny": deny})
        last = m.end()
    if last < len(line):
        parts.append({"lit": line[last:]})
    return parts


def slot_parse_dict(text: str) -> dict:
    lines = text.replace("\ufeff", "").splitlines()
    d = {"slots": {}, "slotOrder": [], "frames": [], "prefix": "", "suffix": ""}
    mode = None
    cur_slot = None
    frame_weight = 1
    for line in lines:
        line = line.strip()
        if not line or line[0] == ";" or line.startswith("//"):
            continue
        g = re.match(r"^#(PREFIX|SUFFIX)\s*(.*)$", line)
        if g:
            if g.group(1) == "PREFIX":
                d["prefix"] = g.group(2)
            else:
                d["suffix"] = g.group(2)
            mode = None
            continue
        h = re.match(r"^#(SLOT|FRAME|WEIGHT)\s*(.*)$", line)
        if h:
            if h.group(1) == "SLOT":
                toks = h.group(2).split()
                name = toks.pop(0) if toks else f"slot{len(d['slots'])}"
                if name not in d["slots"]:
                    d["slots"][name] = []
                    d["slotOrder"].append(name)
                cur_slot = name
                mode = "slot"
            elif h.group(1) == "FRAME":
                mode = "frame"
                frame_weight = 1
                wt = re.search(r"@重み(\d+)", h.group(2) or "")
                if wt:
                    frame_weight = max(1, int(wt.group(1)))
            elif h.group(1) == "WEIGHT":
                frame_weight = max(1, int(h.group(2) or "1"))
            continue
        if mode == "slot" and cur_slot:
            e = _slot_parse_entry(line)
            if e["text"]:
                d["slots"][cur_slot].append(e)
        elif mode == "frame":
            parts = _slot_parse_frame(line)
            d["frames"].append({"parts": parts, "weight": frame_weight, "src": line})
    return d


def _slot_entry_has_tag(e: dict, tag: str) -> bool:
    return tag in e["tags"]


def _slot_candidates(slot_dict: dict, ref: dict) -> list:
    pool = slot_dict["slots"].get(ref["slot"], [])
    if not pool:
        return []
    if not ref["need"] and not ref["deny"]:
        return pool
    out = []
    for e in pool:
        ok = True
        for t in ref["need"]:
            if not _slot_entry_has_tag(e, t):
                ok = False
                break
        if ok:
            for t in ref["deny"]:
                if _slot_entry_has_tag(e, t):
                    ok = False
                    break
        if ok:
            out.append(e)
    return out


def _slot_mutex_conflict(picked: list) -> bool:
    seen = {}
    for e in picked:
        for k, v in e.get("mutex", {}).items():
            if k in seen and seen[k] != v:
                return True
            seen[k] = v
    return False


def _slot_overlap_conflict(picked: list) -> bool:
    for i in range(len(picked)):
        for j in range(i + 1, len(picked)):
            a, b = picked[i]["text"], picked[j]["text"]
            if len(a) < 2 or len(b) < 2:
                continue
            if a in b or b in a:
                return True
    return False


def _slot_particle_conflict(body: str) -> bool:
    return bool(re.search(r"[でにへをごが][でにへをごが]", body)) or "、、" in body or bool(re.search(r"[、。][、。]", body))


def _slot_repeat_conflict(body: str, n: int = 5) -> bool:
    chars = list(body)
    if len(chars) < n * 2:
        return False
    seen = set()
    for i in range(len(chars) - n + 1):
        g = "".join(chars[i:i + n])
        if g in seen:
            return True
        seen.add(g)
    return False


def slot_generate(slot_dict: dict, opt: dict) -> str:
    tries = opt.get("tries", 200)
    min_chars = opt.get("minChars", 18)
    max_chars = opt.get("maxChars", 160)
    prefix = opt.get("prefix", slot_dict.get("prefix", ""))
    suffix = opt.get("suffix", slot_dict.get("suffix", ""))
    recent = opt.get("recent", set())
    if not slot_dict["frames"]:
        return ""
    for _ in range(tries):
        # Weighted frame selection
        total = sum(f["weight"] for f in slot_dict["frames"])
        r = random.random() * total
        frame = slot_dict["frames"][-1]
        for f in slot_dict["frames"]:
            r -= f["weight"]
            if r <= 0:
                frame = f
                break
        # Assemble
        out = ""
        picked = []
        ok = True
        for p in frame["parts"]:
            if "lit" in p:
                out += p["lit"]
                continue
            cands = _slot_candidates(slot_dict, p)
            if not cands:
                if p["optional"]:
                    continue
                ok = False
                break
            e = random.choice(cands)
            picked.append(e)
            out += e["text"]
        if not ok:
            continue
        if _slot_mutex_conflict(picked):
            continue
        if _slot_overlap_conflict(picked):
            continue
        body = re.sub(r"\s+", "", out)
        if _slot_particle_conflict(body):
            continue
        if _slot_repeat_conflict(body, 5):
            continue
        if len(body) < min_chars or len(body) > max_chars:
            continue
        if body in recent:
            continue
        recent.add(body)
        return prefix + body + suffix
    return ""


def slot_generate_flow(slot_dict: dict, opt: dict) -> str:
    """スロット辞書から1行生成（verbatim対応）"""
    verbatim_rate = opt.get("verbatimRate", 0)
    corpus_lines = opt.get("corpusLines", [])
    if verbatim_rate > 0 and corpus_lines and random.random() * 100 < verbatim_rate:
        recent = opt.get("recent", set())
        for _ in range(40):
            l = random.choice(corpus_lines)
            if l and l not in recent:
                recent.add(l)
                return l
        if corpus_lines:
            return random.choice(corpus_lines)
    return slot_generate(slot_dict, opt)


# ============================================================
# SkeletonEngine（物語骨格カード→文章化）
# ============================================================

def _skel_consume_control(token: str, meta: dict) -> bool:
    wm = re.match(r"^重み(\d+)$", token)
    if wm:
        meta["weight"] = max(1, int(wm.group(1)))
        return True
    if token[0] == "^":
        kv = token[1:].split("=", 1)
        if len(kv) == 2:
            meta["mutex"][kv[0]] = kv[1]
        return True
    if token[0] == "!":
        kv = token[1:].split("=", 1)
        if len(kv) == 2:
            meta["conds"].append({"key": kv[0], "vals": kv[1].split("|"), "deny": True})
        return True
    if token[0] == "@":
        body = token[1:]
        eq = body.find("=")
        if eq != -1:
            meta["conds"].append({"key": body[:eq], "vals": body[eq + 1:].split("|"), "deny": False})
        else:
            meta["tags"].append(body)
        return True
    return False


def _skel_new_meta() -> dict:
    return {"conds": [], "tags": [], "mutex": {}, "weight": 1}


def _skel_parse_entry_line(line: str) -> dict:
    tokens = line.split()
    meta = _skel_new_meta()
    texts = []
    for t in tokens:
        if not t:
            continue
        if not _skel_consume_control(t, meta):
            texts.append(t)
    meta["text"] = " ".join(texts).strip()
    return meta


def _skel_parse_frame_body(line: str) -> list:
    parts = []
    last = 0
    for m in re.finditer(r"\{([^{}]+)\}", line):
        if m.start() > last:
            parts.append({"lit": line[last:m.start()]})
        spec = m.group(1)
        opt = spec.endswith("?")
        if opt:
            spec = spec[:-1]
        segs = spec.split("@")
        name = segs.pop(0)
        need = segs
        segs2 = name.split("!")
        name = segs2[0]
        deny = segs2[1:]
        parts.append({"slot": name, "optional": opt, "need": need, "deny": deny})
        last = m.end()
    if last < len(line):
        parts.append({"lit": line[last:]})
    return parts


def _skel_parse_frame_line(line: str) -> dict:
    tokens = line.split()
    meta = _skel_new_meta()
    i = 0
    for i, t in enumerate(tokens):
        if not t:
            continue
        if not _skel_consume_control(t, meta):
            break
    else:
        i = len(tokens)
    meta["body"] = " ".join(tokens[i:]).strip()
    meta["parts"] = _skel_parse_frame_body(meta["body"]) if meta["body"] else []
    return meta


def skel_parse_dict(text: str) -> dict:
    lines = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    d = {"axes": {}, "axisOrder": [], "slots": {}, "slotOrder": [], "frames": [], "prefix": "", "suffix": ""}
    mode = None
    cur = None
    for line in lines:
        line = line.strip()
        if not line or line[0] == ";" or line.startswith("//"):
            continue
        g = re.match(r"^#(PREFIX|SUFFIX)\s*(.*)$", line)
        if g:
            if g.group(1) == "PREFIX":
                d["prefix"] = g.group(2)
            else:
                d["suffix"] = g.group(2)
            mode = None
            continue
        h = re.match(r"^#(AXIS|SLOT|TEXT)\s*(.*)$", line)
        if h:
            if h.group(1) == "AXIS":
                cur = h.group(2).strip() or f"axis{len(d['axes'])}"
                if cur not in d["axes"]:
                    d["axes"][cur] = []
                    d["axisOrder"].append(cur)
                mode = "entry"
            elif h.group(1) == "SLOT":
                cur = h.group(2).strip() or f"slot{len(d['slots'])}"
                if cur not in d["slots"]:
                    d["slots"][cur] = []
                    d["slotOrder"].append(cur)
                mode = "entry"
            else:
                mode = "frame"
            continue
        if mode == "entry":
            e = _skel_parse_entry_line(line)
            if not e["text"]:
                continue
            if cur and cur in d["axes"]:
                d["axes"][cur].append(e)
            elif cur and cur in d["slots"]:
                d["slots"][cur].append(e)
        elif mode == "frame":
            f = _skel_parse_frame_line(line)
            if f.get("body"):
                d["frames"].append(f)
    return d


# SkeletonEngine history（メモリ内、localStorage相当）
_skel_history: dict[str, dict] = {"冒頭": {"cards": [], "texts": []}, "終盤": {"cards": [], "texts": []}}


def _skel_load_history(kind: str) -> dict:
    return _skel_history.get(kind, {"cards": [], "texts": []})


def _skel_record(kind: str, card: dict, body: str):
    h = _skel_history.setdefault(kind, {"cards": [], "texts": []})
    h["cards"].append({"a": card.get("axes", {})})
    h["texts"].append(body)
    if len(h["cards"]) > 200:
        h["cards"] = h["cards"][-200:]
        if len(h["texts"]) > 200:
            h["texts"] = h["texts"][-200:]


def _skel_card_value(card: dict, key: str):
    if key in card.get("axes", {}):
        return card["axes"][key]
    if key in card.get("mutex", {}):
        return card["mutex"][key]
    return None


def _skel_conds_pass(conds: list, card: dict) -> bool:
    for c in conds:
        cur = _skel_card_value(card, c["key"])
        if c["deny"]:
            if cur is not None and cur in c["vals"]:
                return False
        else:
            if cur is None or cur not in c["vals"]:
                return False
    return True


def _skel_adjust_weights(entries: list, axis: str, hist: dict):
    for e in entries:
        e["_w"] = e["weight"]
    if not hist or not hist.get("cards") or len(hist["cards"]) < 10:
        return
    recent = hist["cards"][-100:]
    n = len(recent)
    sum_w = sum(e["weight"] for e in entries)
    if sum_w <= 0:
        return
    for e in entries:
        obs = sum(1 for c in recent if c.get("a", {}).get(axis) == e["text"]) / n
        target = e["weight"] / sum_w
        w = e["weight"]
        if obs < 0.0001:
            w *= (1 + min(1, target * 2))
        else:
            w *= (target / obs) ** 0.7
        e["_w"] = max(e["weight"] * 0.15, min(e["weight"] * 4, w))


def _skel_weighted_pick(entries: list):
    total = sum(e.get("_w", e["weight"]) for e in entries)
    if total <= 0:
        return entries[-1] if entries else None
    r = random.random() * total
    for e in entries:
        r -= e.get("_w", e["weight"])
        if r <= 0:
            return e
    return entries[-1]


def _skel_draw_card(d: dict, hist: dict) -> dict:
    card = {"axes": {}, "mutex": {}}
    for axis in d["axisOrder"]:
        pool = d["axes"].get(axis, [])
        cand = [e for e in pool if _skel_conds_pass(e.get("conds", []), card) and not any(card.get("mutex", {}).get(k) is not None and card["mutex"][k] != v for k, v in e.get("mutex", {}).items())]
        if not cand:
            continue
        _skel_adjust_weights(cand, axis, hist)
        pick = _skel_weighted_pick(cand)
        if pick:
            card["axes"][axis] = pick["text"]
            for k, v in pick.get("mutex", {}).items():
                card["mutex"][k] = v
    return card


def _skel_too_similar(card: dict, hist: dict) -> bool:
    recent = hist.get("cards", [])[-12:]
    for c in recent:
        a = c.get("a", {})
        common = sum(1 for k in card["axes"] if k in a)
        equal = sum(1 for k in card["axes"] if k in a and a[k] == card["axes"][k])
        if common > 0 and equal / common >= 0.6:
            return True
    return False


def skel_generate(d: dict, opts: dict) -> dict | str:
    kind = opts.get("kind", "冒頭")
    min_chars = opts.get("minChars", 18)
    max_chars = opts.get("maxChars", 140)
    tries = opts.get("tries", 120)
    card_tries = opts.get("cardTries", 60)
    hist = _skel_load_history(kind)
    for _ in range(card_tries):
        card = _skel_draw_card(d, hist)
        if _skel_too_similar(card, hist):
            continue
        # Realize
        frames = [f for f in d["frames"] if _skel_conds_pass(f.get("conds", []), card)]
        if not frames:
            continue
        for _ in range(tries):
            frame = _skel_weighted_pick(frames)
            out = ""
            ok = True
            used = []
            for p in frame.get("parts", []):
                if "lit" in p:
                    out += p["lit"]
                    continue
                name = p["slot"]
                if name.startswith("#"):
                    v = card["axes"].get(name[1:])
                    if v is None:
                        if p["optional"]:
                            continue
                        ok = False
                        break
                    out += v
                    continue
                pool = d["slots"].get(name, [])
                if not pool:
                    if p["optional"]:
                        continue
                    ok = False
                    break
                cand = [e for e in pool
                        if all(_slot_entry_has_tag(e, t) for t in p.get("need", []))
                        and not any(_slot_entry_has_tag(e, t) for t in p.get("deny", []))
                        and _skel_conds_pass(e.get("conds", []), card)]
                if not cand:
                    if p["optional"]:
                        continue
                    ok = False
                    break
                pick = _skel_weighted_pick(cand)
                if pick:
                    used.append(pick)
                    out += pick["text"]
            if not ok:
                continue
            body = re.sub(r"\s+", "", out)
            if not body or len(body) < min_chars or len(body) > max_chars:
                continue
            if body in (hist.get("texts") or []):
                continue
            _skel_record(kind, card, body)
            return {"text": (d.get("prefix", "") or "") + body + (d.get("suffix", "") or ""),
                    "body": body, "axes": card.get("axes", {}), "mutex": card.get("mutex", {})}
    # Fallback without dedup check
    card2 = _skel_draw_card(d, hist)
    frames2 = [f for f in d["frames"] if _skel_conds_pass(f.get("conds", []), card2)]
    if not frames2:
        return ""
    for _ in range(tries):
        frame = _skel_weighted_pick(frames2)
        out = ""
        ok = True
        for p in frame.get("parts", []):
            if "lit" in p:
                out += p["lit"]
                continue
            name = p["slot"]
            if name.startswith("#"):
                v = card2["axes"].get(name[1:])
                if v is None:
                    if p["optional"]:
                        continue
                    ok = False
                    break
                out += v
                continue
            pool = d["slots"].get(name, [])
            if not pool:
                if p["optional"]:
                    continue
                ok = False
                break
            cand = [e for e in pool
                    if all(_slot_entry_has_tag(e, t) for t in p.get("need", []))
                    and not any(_slot_entry_has_tag(e, t) for t in p.get("deny", []))
                    and _skel_conds_pass(e.get("conds", []), card2)]
            if not cand:
                if p["optional"]:
                    continue
                ok = False
                break
            pick = _skel_weighted_pick(cand)
            if pick:
                out += pick["text"]
        if not ok:
            continue
        body = re.sub(r"\s+", "", out)
        if not body or len(body) < min_chars or len(body) > max_chars:
            continue
        _skel_record(kind, card2, body)
        return {"text": (d.get("prefix", "") or "") + body + (d.get("suffix", "") or ""),
                "body": body, "axes": card2.get("axes", {}), "mutex": card2.get("mutex", {})}
    return ""


# ============================================================
# マークダウン破壊
# ============================================================

def strip_markdown(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)
    text = re.sub(r"`+([^`\n]*?)`+", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<https?://[^>]+>", "", text)
    text = re.sub(r"^[ \t]*#{1,6}[ \t]*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*>+[ \t]?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*\d+\.[ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*([-*_])[ \t]*\1[ \t]*\1[\1 \t]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*\*([^\*\n]+?)\*\*\*", r"\1", text)
    text = re.sub(r"___([^_\n]+?)___", r"\1", text)
    text = re.sub(r"\*\*([^\*\n]+?)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+?)__", r"\1", text)
    text = re.sub(r"~~([^~\n]+?)~~", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+?)_(?!_)", r"\1", text)
    text = re.sub(
        r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)+\|?[ \t]*$",
        "", text, flags=re.MULTILINE)
    text = text.replace("|", " ")
    text = re.sub(r"<[^<>\n]{1,200}>", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ============================================================
# マルコフ連鎖エンジン
# ============================================================

def is_english_text(text: str, threshold: float = 0.5) -> bool:
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= threshold


def build_markov_chain(text: str, order: int):
    order = max(1, int(order))
    chain: dict[str, list[str | None]] = {}
    starts: list[str] = []
    text_split = text.replace("。", "。\n")
    lines = [line.strip() for line in text_split.splitlines() if len(line.strip()) > order]
    if not lines:
        return None
    for line in lines:
        chars = list(line)
        starts.append("".join(chars[:order]))
        for i in range(len(chars) - order + 1):
            gram = "".join(chars[i:i + order])
            next_char = chars[i + order] if (i + order) < len(chars) else None
            chain.setdefault(gram, []).append(next_char)
    return {"chain": chain, "starts": starts}


def generate_sentence(chain_data: dict, order: int, min_len: int = None, max_len: int = None) -> str:
    if not chain_data:
        return ""
    order = max(1, int(order))
    chain = chain_data["chain"]
    starts = chain_data["starts"]
    if not starts:
        return ""
    min_length = min_len if min_len is not None else MARKOV_SENTENCE_MIN_CHARS
    max_length = max_len if max_len is not None else MARKOV_SENTENCE_MAX_CHARS
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


# マルコフチェーンのキャッシュ
_markov_cache: dict[str, dict] = {}


def _get_chain(text: str, order: int, cache_key: str):
    key = f"{cache_key}@{order}"
    if key in _markov_cache:
        return _markov_cache[key]
    c = build_markov_chain(text, order)
    _markov_cache[key] = c
    return c


def generate_markov_one_liner(text: str, order: int, char_limit: int = 80, cache_key: str = "__one") -> str:
    if not text:
        return ""
    cleaned = strip_markdown(text)
    if not cleaned.strip():
        return ""
    is_eng = is_english_text(cleaned)
    base_order = 4
    chain = _get_chain(cleaned, base_order, cache_key)
    if not chain:
        return ""
    s = generate_sentence(chain, base_order, MARKOV_SENTENCE_MIN_CHARS, MARKOV_SENTENCE_MAX_CHARS)
    if not s:
        return ""
    s = s.replace("\r", "").replace("\n", " ").strip()
    if len(s) > char_limit:
        cut = s[:char_limit]
        for p in ["。", "、", ".", "!", "？", "?", "！"]:
            idx = cut.rfind(p)
            if idx >= 10:
                cut = cut[:idx + 1]
                break
        s = cut.strip()
    if len(s) < MARKOV_SENTENCE_MIN_CHARS:
        return ""
    return s


def generate_markov_text(text: str, order: int, line_count: int, char_limit: int, cache_key: str = "markov") -> str:
    if not text:
        return ""
    cleaned = strip_markdown(text)
    if not cleaned.strip():
        return ""
    is_eng = is_english_text(cleaned)
    base_order = max(1, int(order))
    if MARKOV_FLUCTUATION == 1:
        candidate_orders = list(dict.fromkeys([max(1, base_order - 1), base_order]))
    else:
        candidate_orders = [base_order]
    pool = []
    for o in candidate_orders:
        chain = _get_chain(cleaned, o, cache_key)
        if chain:
            pool.append({"order": o, "chain": chain})
    if not pool:
        return ""
    sentences = []
    current_len = 0
    generated = 0
    fails = 0
    while generated < line_count and current_len < char_limit:
        sel = random.choice(pool)
        s = generate_sentence(sel["chain"], sel["order"], MARKOV_SENTENCE_MIN_CHARS, MARKOV_SENTENCE_MAX_CHARS)
        if not s or len(s) < MARKOV_SENTENCE_MIN_CHARS:
            fails += 1
            if fails >= 100:
                break
            continue
        sentences.append(s)
        current_len += len(s) + 1
        generated += 1
        fails = 0
        if current_len > char_limit:
            break
    return "\n".join(sentences)


def generate_flow_fallback_line(prefix: str, markov_text: str, char_limit: int, cache_key: str = "__fb") -> str:
    """スロット/骨格失敗時の代替：マルコフ.txtの1行マルコフで「冒頭は、〜」形式"""
    body = generate_markov_one_liner(markov_text, 4, max(10, char_limit - len(prefix)), cache_key)
    if not body:
        return ""
    body = re.sub(r"^[\s、。・「」（）()]+", "", body)
    body = re.sub(r"^(?:冒頭|終盤)は、\s*", "", body)
    if not body:
        return ""
    return prefix + body


# ============================================================
# フロー指示文
# ============================================================

FLOW_NOTE = {
    "冒頭": {
        "skel": "↑\nこれが冒頭の流れ。文の直後の［ ］は、この冒頭に課された物語機能の指定（骨格カード）である。タグの全項目を厳守して書き、どれも外さないこと。特に犠牲・喪失・トラブルの指定は勝手な回避・軽減・後出しの撤回を禁止する。ここで出した要素や言及は、物語のどこかで必ず意味を持つ伏線として張っておけ。",
        "slot": "↑\nこれが冒頭の流れ。ここで出した要素や言及は、物語のどこかで必ず意味を持つ伏線として張っておけ。",
        "markov": "↑\nこれが冒頭の流れ。文が破綻していても、その意図を補完して強引に解釈し、ここで出した要素や言及を物語のどこかで必ず意味を持つ伏線として張っておけ。",
    },
    "終盤": {
        "skel": "↑\nこれが終盤の流れ。文の直後の［ ］は、この結末に課された物語機能の指定（骨格カード）である。タグの全項目を厳守して書き、どれも外さないこと。特に犠牲が「死亡する」の場合は、指定された死因のまま必ず死亡エンドとして直接描け。死亡のぼかし・生存へのすり替え・直前の回避は禁止する。この終盤の着地を、物語のどこかで既に張った伏線を拾い上げる形で実現しろ。",
        "slot": "↑\nこれが終盤の流れ。この終盤の着地を、物語のどこかで既に張った伏線を拾い上げる形で実現しろ。",
        "markov": "↑\nこれが終盤の流れ。文が破綻していても、その意図を補完して強引に解釈し、この終盤の着地を、物語のどこかで既に張った伏線を拾い上げる形で実現しろ。",
    },
}


def _normalize_flow_text(text: str) -> str:
    if not text:
        return ""
    return text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")


# スロット辞書キャッシュ
_slot_dict_cache: dict[str, dict] = {}


def _get_slot_dict(key: str, text: str) -> dict | None:
    if not text:
        return None
    hit = _slot_dict_cache.get(key)
    if hit and hit.get("src") == text:
        return hit.get("dict")
    try:
        d = slot_parse_dict(text)
    except Exception:
        return None
    if not d or not d.get("frames"):
        return None
    _slot_dict_cache[key] = {"src": text, "dict": d}
    return d


# 骨格辞書キャッシュ
_skel_dict_cache: dict[str, dict] = {}


def _get_skeleton_dict(key: str, text: str) -> dict | None:
    if not text:
        return None
    hit = _skel_dict_cache.get(key)
    if hit and hit.get("src") == text:
        return hit.get("dict")
    try:
        d = skel_parse_dict(text)
    except Exception:
        return None
    if not d or not d.get("frames"):
        return None
    _skel_dict_cache[key] = {"src": text, "dict": d}
    return d


def generate_slot_flow_line(kind: str, files: dict, char_limit: int) -> str:
    limit = max(30, int(char_limit))
    prefix = kind + "は、"
    dict_text = files.get("openingSlot") if kind == "冒頭" else files.get("endingSlot")
    if not dict_text:
        return ""
    d = _get_slot_dict(kind, _normalize_flow_text(dict_text))
    if not d:
        return ""
    body_max = limit - len(prefix) - len(d.get("suffix", ""))
    if body_max < 12:
        return ""
    recent: set[str] = set()
    line = slot_generate_flow(d, {
        "verbatimRate": 0, "corpusLines": [],
        "minChars": 12, "maxChars": body_max,
        "tries": 200, "recent": recent,
    })
    if not line:
        return ""
    line = line.replace("\r", "").replace("\n", " ").strip()
    if not line or len(line) > limit:
        return ""
    return line


def generate_skeleton_flow_line(kind: str, files: dict, char_limit: int) -> tuple[str, str]:
    """骨格カードから冒頭/終盤の1行を生成。戻り値: (行, ソース種別)"""
    limit = max(30, int(char_limit))
    dict_text = files.get("openingSlot") if kind == "冒頭" else files.get("endingSlot")
    d = _get_skeleton_dict(kind, _normalize_flow_text(dict_text or ""))
    if not d:
        return "", ""
    result = skel_generate(d, {
        "kind": kind, "minChars": 18, "maxChars": max(20, limit - 10),
        "tries": 120, "cardTries": 60,
    })
    if not result or not isinstance(result, dict) or not result.get("text"):
        return "", ""
    line = result["text"].replace("\r", "").replace("\n", " ").strip()
    if not line or len(line) > limit:
        return "", ""
    # 構造タグ行を同梱
    tags = [f"{k}={v}" for k, v in (result.get("axes") or {}).items() if v]
    if tags:
        return line + "\n［" + "｜".join(tags) + "］", "skel"
    return line, "skel"


# ============================================================
# 視点キャラ固定
# ============================================================

_group_fix_cache: dict[str, str] = {}


def fixed_hero_name() -> str:
    v = FIXED_HERO
    if not v or v == "0" or v == "random" or v == "ランダム":
        return ""
    if v.startswith("group:"):
        mid = v[len("group:"):]
        m = char_material_by_id(mid)
        if not m or not m.get("names"):
            return ""
        if mid not in _group_fix_cache:
            _group_fix_cache[mid] = random.choice(m["names"])
        return _group_fix_cache[mid]
    return v


def hero_entry_for_name(name: str) -> str:
    """キャラ名から「AA　名前」形式のエントリを検索"""
    if not name:
        return ""
    search = name
    if search == "ペニサス伊藤":
        search = "ペニサス"
    if search == "都村トソン":
        search = "トソン"
    all_chars = BOON_CHARACTERS + MONA_CHARACTERS + TANO_CHARACTERS
    # 完全一致を優先
    for entry in all_chars:
        en = hero_entry_name(entry)
        if en == search or en == name:
            return entry
    # 部分一致フォールバック
    for entry in all_chars:
        if search in entry:
            return entry
    return ""


def hero_entry_name(entry: str) -> str:
    i = entry.rfind("　")
    return entry[i + 1:] if i >= 0 else entry


def hero_names_from_text(hero_text: str) -> list[str]:
    m = re.search(r"今回の視点は\[\s*(.+?)\s*\]です", hero_text or "")
    if not m:
        return []
    x = m.group(1)
    if "：" in x:
        x = x.split("：", 1)[1]
    names = []
    for chunk in re.split(r"[、,]", x):
        parts = [p for p in chunk.split("　") if p.strip()]
        if parts:
            names.append(parts[-1].strip())
    return names


def hero_name_from_text(hero_text: str) -> str:
    names = hero_names_from_text(hero_text)
    return names[0] if names else ""


# ============================================================
# キャラクター間の関係ルール（9資料対応）
# ============================================================

REL_GROUPS = {
    "nijisousaku": ("VIP", ["兄者", "弟者", "ブーン", "ドクオ", "クー", "シュー", "モララー", "ギコ", "ショボン", "シャキン"]),
    "choukasoku": ("モナーグループ", ["モナー", "ロマネスク", "しぃ", "つー", "ミセリ", "トソン"]),
    "lab": ("ラボ組", ["フォックス", "花瓶", "ヒート"]),
    "school": ("学校組", ["デレ", "キュート", "ペニサス伊藤"]),
    "host": ("ホスト組", ["またんき", "フサギコ", "ぃょぅ"]),
    "tsun": ("単独（ツン）", ["ツン"]),
    "watanabe": ("単独（渡辺さん）", ["渡辺さん"]),
    "hain": ("単独（ハイン）", ["ハイン"]),
    "di": ("単独（でぃ）", ["でぃ"]),
}

CROSS_CONTACTS = [
    {"a": "hain", "b": "choukasoku",
     "text": "ハインは超加速資料のミセリと学校の友人であり、互いに面識がある。ハインが面識を持つのはミセリだけで、モナーグループの他の人物は引き続き無関係として扱う。"},
    {"a": "hain", "b": "lab",
     "text": "ハインの自宅の近隣にラボ（外観・規模は一般住宅）があり、ハインはその騒音・異常事態を「よくわからないが迷惑なもの」として認識している。ただしラボの3人の名前・素性・実態は知らない。"},
    {"a": "host", "b": "choukasoku",
     "text": "ホスト組のまたんきはモナーグループの面々と互いに顔と素性を認識しているが、モナーグループのメンバーではない。利害（肉）が一致した時や偶然遭遇した時のみ関わる。フサギコとぃょぅの接点はまたんき経由の個別関係に限る。"},
]

HERO_PAIR_KNOWN = [
    ["ハイン", "ミセリ"],
    ["またんき", "モナー"], ["またんき", "ロマネスク"], ["またんき", "しぃ"],
    ["またんき", "つー"], ["またんき", "ミセリ"], ["またんき", "トソン"],
]


def hero_group_label(entry: str) -> str | None:
    name = hero_entry_name(entry)
    for key, (label, members) in REL_GROUPS.items():
        for m in members:
            if m == name or m.startswith(name) or name.startswith(m):
                return "単独" if "（" in label else label
    return None


def hero_pair_note(h1: str, h2: str) -> str:
    g1 = hero_group_label(h1)
    g2 = hero_group_label(h2)
    if not g1 or not g2 or g1 == g2:
        return ""
    n1, n2 = hero_entry_name(h1), hero_entry_name(h2)
    for pair in HERO_PAIR_KNOWN:
        if (pair[0] == n1 and pair[1] == n2) or (pair[0] == n2 and pair[1] == n1):
            return ""
    return f"\n{n1}（{g1}）と{n2}（{g2}）は、互いに一切の面識・接点を持たない完全な無関係（他人）である。"


def generate_relation_rule(selected_ids: list[str]) -> str:
    selected = [sid for sid in selected_ids if sid in REL_GROUPS]
    if not selected:
        return ""

    def member_str(label, members):
        return label if "（" in label else f"{label}（{'、'.join(members)}）"

    def find_contact(x, y):
        for c in CROSS_CONTACTS:
            if (c["a"] == x and c["b"] == y) or (c["a"] == y and c["b"] == x):
                return c
        return None

    lines = []
    for i in range(len(selected)):
        for j in range(i + 1, len(selected)):
            contact = find_contact(selected[i], selected[j])
            if contact:
                lines.append(contact["text"])
                continue
            g1 = REL_GROUPS[selected[i]]
            g2 = REL_GROUPS[selected[j]]
            lines.append(f"{member_str(*g1)}と{member_str(*g2)}は、互いに一切の面識・接点を持たない完全な無関係（他人）である。")
    if len(selected) == 1:
        only = REL_GROUPS[selected[0]]
        lines.append(f"{member_str(*only)}のキャラクターは、このプロンプトに記述されていない他のグループのキャラクターと互いに一切の面識・接点を持たない完全な無関係（他人）である。ただし詳細キャラ資料に関係・面識・接点の記載がある組合せは、その記載を優先する。")
    rule = "キャラクター間の関係：\n" + "\n".join(lines)
    rule += "\nこの指定の趣旨は、互いに面識のないキャラクター同士を「顔を知っている」「旧知の仲」のような顔見知り・旧知扱いで描写することを防ぐことにある。顔合わせそのものを禁じる趣旨ではない。物語の展開やユーザーの指示に応じて、異なるグループのキャラクターが同じ場に現れ、顔を合わせることは許容する。その場合、両者は必ず初対面として描くこと：互いの名前・素性・性格・能力・過去を知らない前提で、初対面特有の距離感（警戒・探り・よそよそしさ・自己紹介）を持たせる。旧知同士のような馴染んだ口調、相手の内情を知っている前提の言動、根拠のない親密さや信頼を付加してはならない。顔合わせを避ける必要はないが、顔を合わせた以上、初対面以外の関係性を勝手に付与してはならない。"
    rule += "\n詳細キャラ資料に関係・面識・接点の記載がある組合せは、無関係（他人）として扱わず、資料の記載を優先すること。ただし記載された関係の範囲を超えて、顔見知り・旧知の関係へ勝手に拡張してはならない。"
    return rule


# ============================================================
# 汎用キャラクター一覧（9資料対応）
# ============================================================

TEMPLATE_EXCLUDE_BY_FILE = {
    "nijisousaku": {"兄者", "弟者", "ブーン", "ドクオ", "クー", "シュー", "モララー", "ギコ", "ショボン", "シャキン"},
    "choukasoku": {"モナー", "ロマネスク", "しぃ", "つー", "ミセリ", "トソン"},
    "lab": {"花瓶", "ヒート", "フォックス"},
    "school": {"デレ", "キュート", "ペニサス伊藤"},
    "host": {"またんき", "フサギコ", "ぃょぅ"},
    "tsun": {"ツン"},
    "watanabe": {"渡辺さん"},
    "hain": {"ハイン"},
    "di": {"でぃ"},
}

TEMPLATE_EXCLUDE_AA_BY_FILE = {
    "nijisousaku": {"（　＾ω＾）", "('A`)", "川 ﾟ -ﾟ)", "lw´‐ _‐ﾉv", "（ ・∀・）", "(,,ﾟДﾟ)", "(´・ω・`)", "(｀･ω･´)", "（ ´_ゝ`）", "（´<_` ）"},
    "choukasoku": {"（ ´∀｀）", "（ ФωФ）", "(*ﾟーﾟ)", "(*ﾟ∀ﾟ)", "ﾐｾ*ﾟーﾟ)ﾘ", "(ﾟ、ﾟﾄｿﾝ"},
    "lab": {"i!iiﾘﾟ ヮﾟﾉﾙ", "ﾉﾊﾟ⊿ﾟ)", "爪'ー`)y‐"},
    "school": {"ζ(ﾟーﾟ*ζ", "o川*ﾟーﾟ)o", "('、`*川"},
    "host": {"(・∀ ・)", "ミ,,ﾟДﾟ彡", "(=ﾟωﾟ)ﾉ"},
    "tsun": {"ξﾟ⊿ﾟ)ξ"},
    "watanabe": {"从'ー'从"},
    "hain": {"从 ﾟ∀从"},
    "di": {"(#ﾟ;;-ﾟ)"},
}


def _parse_template(text: str):
    header = None
    sep = None
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s[0] != "|":
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


def build_char_template(selected_ids: list[str], hero_text: str, shuryo_mode: int, files: dict) -> str:
    text = files.get("charaTemplate")
    if not text:
        return ""
    header, sep, rows = _parse_template(text)
    if not rows:
        return ""

    def pick_count(pool_size: int) -> int:
        lo = max(1, min(CHAR_TEMPLATE_MIN, CHAR_TEMPLATE_MAX))
        hi = max(lo, max(CHAR_TEMPLATE_MIN, CHAR_TEMPLATE_MAX))
        return min(pool_size, random.randint(lo, hi))

    def split_hero(src_rows):
        hero_names = hero_names_from_text(hero_text)
        hero_blob = norm_aa(hero_text)
        heroes, others = [], []
        for r in src_rows:
            core = r[0].split("（")[0].strip()
            aa = norm_aa(r[1]) if len(r) >= 2 else ""
            name_hit = core and (core in hero_names or ("ペニサス" in hero_names and core == "ペニサス伊藤"))
            if name_hit or (aa and aa in hero_blob):
                heroes.append(r)
            else:
                others.append(r)
        return heroes, others

    if shuryo_mode == 2:
        hero_rows, rest = split_hero(rows)
        random.shuffle(rest)
        slots = pick_count(len(hero_rows) + len(rest)) - len(hero_rows)
        kept = hero_rows + rest[:max(0, slots)]
    else:
        exclude = set()
        exclude_aa = set()
        for sid in selected_ids:
            exclude |= TEMPLATE_EXCLUDE_BY_FILE.get(sid, set())
            exclude_aa |= TEMPLATE_EXCLUDE_AA_BY_FILE.get(sid, set())
        filtered = [r for r in rows
                    if r[0].split("（")[0].strip() not in exclude
                    and (r[1].strip() if len(r) >= 2 else "") not in exclude_aa]
        hero_rows, rest = split_hero(filtered)
        random.shuffle(rest)
        slots = pick_count(len(hero_rows) + len(rest)) - len(hero_rows)
        thinned = rest[:max(0, slots)]
        kept = hero_rows + thinned
        if not kept and filtered:
            kept = [random.choice(filtered)]

    if not kept:
        return ""
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
# 1つのキャラ資料txt内の人物ブロックをシャッフル
# ============================================================

_WORLD_HEAD_RE = re.compile(
    r"^#{1,3}\s*(世界設定|グループ概要|組織概要|【AI用設計資料】|地理|日本政府|勢力)")


def _aa_match_key(s: str) -> str:
    return norm_aa(s).replace("｀", "'").replace("`", "'").replace("´", "'")


def _line_is_char_start(line: str, aas: list[str], names: list[str]) -> bool:
    t = (line or "").strip()
    if not t or not aas:
        return False
    if re.search(r"[「『]", t):
        return False
    nk = _aa_match_key(t)
    name_hit = any(n and n in t for n in names) if names else False
    for aa in aas:
        ak = _aa_match_key(aa)
        if not ak:
            continue
        if nk == ak:
            return True
        if nk.startswith(ak) and name_hit:
            return True
    return False


def shuffle_char_blocks_in_material(raw: str, mat_id: str) -> str:
    if not raw or not raw.strip():
        return raw or ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    aas = list(TEMPLATE_EXCLUDE_AA_BY_FILE.get(mat_id, []))
    names = list(TEMPLATE_EXCLUDE_BY_FILE.get(mat_id, []))
    if not aas:
        return raw
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if _line_is_char_start(line, aas, names)]
    if len(starts) <= 1:
        return raw
    prefix = "\n".join(lines[:starts[0]]).rstrip("\n")
    char_parts = []
    trailers = []
    for s_idx in range(len(starts)):
        from_idx = starts[s_idx]
        to_idx = starts[s_idx + 1] if s_idx + 1 < len(starts) else len(lines)
        block_lines = lines[from_idx:to_idx]
        cut = -1
        for k, bl in enumerate(block_lines):
            if _WORLD_HEAD_RE.match(bl.strip()):
                cut = k
                break
        if cut > 0:
            char_parts.append("\n".join(block_lines[:cut]).rstrip("\n"))
            trailers.append("\n".join(block_lines[cut:]).strip("\n"))
        elif cut == 0:
            trailers.append("\n".join(block_lines).strip("\n"))
        else:
            char_parts.append("\n".join(block_lines).rstrip("\n"))
    if len(char_parts) <= 1:
        return raw
    random.shuffle(char_parts)
    out = "\n\n".join(b for b in char_parts if b and b.strip())
    if prefix and prefix.strip():
        out = prefix + "\n\n" + out
    if trailers:
        tr = "\n\n".join(b for b in trailers if b and b.strip())
        if tr:
            out = out.rstrip("\n") + "\n\n" + tr
    return out


# ============================================================
# キャラ単位の優先度プール
# ============================================================

def char_priority_pool() -> list[dict]:
    pool = []
    for m in CHAR_MATERIALS:
        for name in m["names"]:
            pool.append({"char": name, "matId": m["id"]})
    return pool


def clone_char_priority() -> list[dict]:
    pool = char_priority_pool()
    random.shuffle(pool)
    return pool


def _candidates_for_char_files(file_ids: list[str]) -> list[str]:
    out = []
    seen = set()
    for fid in file_ids:
        m = char_material_by_id(fid)
        if not m:
            continue
        if fid == "nijisousaku":
            pool = BOON_CHARACTERS
        elif fid == "choukasoku":
            pool = [e for e in MONA_CHARACTERS if "またんき" not in e]
        elif fid == "host":
            pool = MONA_CHARACTERS + TANO_CHARACTERS
        else:
            pool = TANO_CHARACTERS
        for entry in pool:
            if any(m_name in entry for m_name in m["names"]):
                if entry not in seen:
                    seen.add(entry)
                    out.append(entry)
    return out


def choose_hero_for_char_files(file_ids: list[str], current_hero_mode: int,
                               suppress_hero: bool, files: dict) -> tuple[str, int]:
    _group_fix_cache.clear()
    fixed = fixed_hero_name()
    if fixed:
        fixed_entry = hero_entry_for_name(fixed)
        if fixed_entry:
            return f"今回の視点は[ {fixed_entry} ]です", 1

    candidates = _candidates_for_char_files(file_ids)
    if not candidates:
        candidates = BOON_CHARACTERS + MONA_CHARACTERS + TANO_CHARACTERS
    hero_text = ""
    if candidates:
        hero1 = random.choice(candidates)
        if random.random() * 100 < DOUBLE_HERO_RATE and len(candidates) >= 2:
            rest = [c for c in candidates if c != hero1]
            hero2 = random.choice(rest)
            hero_text = f"今回の視点は[ {hero1}、{hero2} ]です" + hero_pair_note(hero1, hero2)
        else:
            hero_text = f"今回の視点は[ {hero1} ]です"
    mode = current_hero_mode
    if not suppress_hero and random.random() * 100 < SPECIAL_HERO_RATE:
        sp_cands = _special_hero_candidates(files, file_ids)
        if sp_cands:
            hero_text = f"今回の視点は[ {random.choice(SPECIAL_HERO_LABELS)}：{random.choice(sp_cands)} ]です"
            mode = 1
    if not hero_text:
        mode = 0
    return hero_text, mode


def _special_hero_candidates(files: dict, file_ids: list[str]) -> list[str]:
    """特殊視点候補をキャラテンプレ.txtから構築"""
    text = files.get("charaTemplate")
    rows = []
    if text:
        for line in text.splitlines():
            s = line.strip()
            if not s or s[0] != "|":
                continue
            if "代表AA" in s:
                continue
            if re.fullmatch(r"\|[\s\-|]+\|", s):
                continue
            # \| をAAの一部として処理
            cells = []
            cur = ""
            i = 0
            while i < len(s):
                ch = s[i]
                if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
                    cur += "\\|"
                    i += 2
                    continue
                if ch == "|":
                    cells.append(cur)
                    cur = ""
                    i += 1
                    continue
                cur += ch
                i += 1
            cells.append(cur)
            if cells and cells[0].strip() == "":
                cells = cells[1:]
            if cells and cells[-1].strip() == "":
                cells = cells[:-1]
            cells = [c.strip() for c in cells]
            if len(cells) >= 2 and cells[0]:
                rows.append(cells)

    adopted = set(file_ids)
    mat_by_raw_aa = {}
    all29 = BOON_CHARACTERS + MONA_CHARACTERS + TANO_CHARACTERS
    for entry in all29:
        sep = entry.rfind("　")
        nm = entry[sep + 1:] if sep >= 0 else entry
        mid = mat_id_for_hero_name(nm)
        if not mid or mid not in adopted:
            continue
        aa = entry[:sep] if sep >= 0 else entry
        mat_by_raw_aa[aa] = nm

    out = []
    seen = set()
    for r in rows:
        core = (r[0] or "").split("（")[0].strip()
        aa = (r[1] or "").strip()
        if not core or not aa:
            continue
        over = mat_by_raw_aa.get(aa)
        if over and (core == over or over in core or core in over):
            core = over
        entry = aa + "　" + core
        if entry not in seen:
            seen.add(entry)
            out.append(entry)
    if not out:
        return list(BUGAI_CHARACTERS)
    return out


# 一人称視点指定行
FIRST_PERSON_LINE = "一人称視点の形式で書くこと"


# ============================================================
# build_contents（プロンプト本体の組み立て）— 9資料対応版
# ============================================================

def build_contents_priority(files: dict, shuryo_mode: int, use_markov: bool,
                            markov_lines_max: int, max_char: int,
                            char_priority: list[dict] | None = None,
                            suppress_hero: bool = False, tail_text: str = "") -> dict | None:
    """モード-1/3: キャラ単位の優先度で資料を選出"""
    _group_fix_cache.clear()
    base_blocks: list[list[str]] = []
    cur_block: list[str] | None = None
    base_len = 0

    def add_base(text: str) -> bool:
        nonlocal base_len, cur_block
        if not text:
            return True
        if cur_block is None:
            cur_block = []
        cur_block.append(text)
        base_len += len(text) + 2
        return base_len <= max_char

    def seal_base():
        nonlocal cur_block
        if cur_block:
            base_blocks.append(cur_block)
            cur_block = None

    # 資料.txt（1%でマルコフ化）
    shiryou_text = files.get("shiryou")
    if shiryou_text and random.random() < 0.01:
        m = generate_markov_text(shiryou_text, 3, 10_000_000, len(shiryou_text), "shiryou")
        if m:
            shiryou_text = m
    if shuryo_mode == 3:
        if not add_base(shiryou_text or ""):
            return None
        seal_base()
    else:
        if not add_base(shiryou_text or ""):
            return None
        seal_base()
        if not add_base(files.get("ss", "")):
            return None
        seal_base()

    if shuryo_mode != 2 and files.get("kinshi"):
        if not add_base(files["kinshi"]):
            return None
        seal_base()

    if files.get("kyoutsu"):
        if not add_base(files["kyoutsu"]):
            return None
        seal_base()

    if not add_base("主要AAのキャラのみを使用し、モブを用意する場合も主要AAから使用する"):
        return None
    seal_base()

    # マルコフ
    if use_markov:
        effective_min = min(MARKOV_LINES_HARD_MAX, 1 if shuryo_mode == 3 else MARKOV_LINES_MIN)
        actual_max = min(MARKOV_LINES_HARD_MAX, max(effective_min, markov_lines_max))
        if shuryo_mode == 3:
            all_parts = [files.get("ss", "")]
            for m in CHAR_MATERIALS:
                if files.get(m["id"]):
                    all_parts.append(files[m["id"]])
            combined = "\n".join(p for p in all_parts if p)
            if combined:
                left = max_char - base_len
                if left > 0:
                    gen = generate_markov_text(combined, MARKOV_ORDER,
                                              random.randint(effective_min, actual_max), left, "__c1")
                    if gen:
                        if not add_base(gen):
                            return None
                        if not add_base("---\nこれは資料です"):
                            return None
                        seal_base()
            if files.get("markov"):
                left2 = max_char - base_len
                if left2 > 0:
                    gen2 = generate_markov_text(files["markov"], MARKOV_ORDER,
                                               random.randint(effective_min, actual_max), left2, "markov")
                    if gen2:
                        if not add_base(gen2):
                            return None
                        if not add_base("---\nこれは資料です"):
                            return None
                        seal_base()
        else:
            left = max_char - base_len
            if left > 0:
                gen = generate_markov_text(files.get("markov", ""), MARKOV_ORDER,
                                          random.randint(effective_min, actual_max), left, "markov")
                if gen:
                    if not add_base(gen):
                        return None
                    if not add_base("↑\nこれは本編の資料です。軽度な改変はOK"):
                        return None
                    seal_base()

    if files.get("tsuzuki"):
        if not add_base(files["tsuzuki"]):
            return None
    seal_base()

    if files.get("last"):
        if not add_base(files["last"]):
            return None
    seal_base()

    template_block_idx = len(base_blocks)

    # 冒頭フロー
    if USE_OPENING_MARKOV_MODE == 1:
        rem = max_char - base_len
        if rem > 0:
            op = ""
            op_src = ""
            if random.random() * 100 < num_or(SKELETON_RATE, 50):
                op, op_src = generate_skeleton_flow_line("冒頭", files, min(160, rem))
            if not op and random.random() * 100 < num_or(OPENING_RATE, 100):
                op = generate_slot_flow_line("冒頭", files, min(160, rem))
                if op:
                    op_src = "slot"
            if not op:
                op = generate_flow_fallback_line("冒頭は、", files.get("markov", ""), min(160, rem), "__one_opening_fb")
                if op:
                    op_src = "markov"
            if op:
                note_key = op_src if op_src in ("skel", "slot", "markov") else "markov"
                if not add_base(op + "\n" + FLOW_NOTE["冒頭"][note_key]):
                    return None
                seal_base()

    # 終盤フロー
    if USE_ENDING_MARKOV_MODE == 1:
        rem = max_char - base_len
        if rem > 0:
            en = ""
            en_src = ""
            if random.random() * 100 < num_or(SKELETON_RATE, 50):
                en, en_src = generate_skeleton_flow_line("終盤", files, min(160, rem))
            if not en and random.random() * 100 < num_or(ENDING_RATE, 100):
                en = generate_slot_flow_line("終盤", files, min(160, rem))
                if en:
                    en_src = "slot"
            if not en:
                en = generate_flow_fallback_line("終盤は、", files.get("markov", ""), min(160, rem), "__one_ending_fb")
                if en:
                    en_src = "markov"
            if en:
                note_key = en_src if en_src in ("skel", "slot", "markov") else "markov"
                if not add_base(en + "\n" + FLOW_NOTE["終盤"][note_key]):
                    return None
                seal_base()

    # テーマ
    if USE_LAST_MARKOV_LINE_MODE == 1:
        left = max_char - base_len
        if left > 0:
            one = generate_markov_one_liner(files.get("markov", ""), MARKOV_ORDER, min(120, left))
            if one:
                if not add_base(one + "\n↑\nこれがテーマの話を書け"):
                    return None
                seal_base()

    # トーン
    tone_raw = files.get("tone")
    all_tone = [l.strip() for l in (tone_raw or "").splitlines() if l.strip()]
    if not all_tone:
        all_tone = ["コメディ", "ダーク", "ハード", "ホラー", "ミステリー"]
    random.shuffle(all_tone)
    tone_count = random.randint(0, min(MAX_TONE_COUNT, len(all_tone)))
    selected = all_tone[:tone_count]
    if tone_count == 1:
        values = [100]
    elif tone_count > 1:
        while True:
            temp = [random.randint(-100, 100) for _ in range(tone_count - 1)]
            last_val = 100 - sum(temp)
            if -100 <= last_val <= 200:
                values = temp + [last_val]
                random.shuffle(values)
                break
    else:
        values = []
    tone_lines = "\n".join(f"・{n} {v}%" for n, v in zip(selected, values))
    if not add_base("話のトーン（本編内でこの語彙を使用することを控えろ）\n" + tone_lines):
        return None
    seal_base()

    if tail_text:
        if not add_base(tail_text):
            return None
        seal_base()

    char_min = random.randint(CHAR_COUNT_MIN, CHAR_COUNT_MAX)
    char_max = random.randint(char_min, CHAR_COUNT_MAX)
    char_count_text = f"文字数は{char_min}~{char_max}文字"

    # キャラ資料の優先度適用
    priority = (char_priority or clone_char_priority()).copy()
    fixed_name = fixed_hero_name()
    fixed_mat_id = mat_id_for_hero_name(fixed_name) if fixed_name else None
    selected_ids: list[str] = []
    char_blocks: list[str] = []
    projected = base_len
    tried: set[str] = set()
    for p in priority:
        mid = p["matId"]
        if mid in tried:
            continue
        tried.add(mid)
        raw = files.get(mid, "")
        raw = shuffle_char_blocks_in_material(raw, mid)
        if not raw or not raw.strip():
            continue
        if projected + len(raw) + 2 + len(char_count_text) + 2 > max_char:
            break
        char_blocks.append(raw)
        selected_ids.append(mid)
        projected += len(raw) + 2

    # 固定視点の所属txtが不採用なら失敗
    if fixed_mat_id:
        raw_check = files.get(fixed_mat_id)
        if raw_check and raw_check.strip() and fixed_mat_id not in selected_ids:
            return None

    hero_text, hero_mode = choose_hero_for_char_files(selected_ids, HERO_MODE, suppress_hero, files)
    relation = generate_relation_rule(selected_ids) if shuryo_mode != 2 else ""
    template = build_char_template(selected_ids, hero_text, shuryo_mode, files)

    # 視点・文字数の最終ブロック
    fp_hit = random.random() * 100 < num_or(FIRST_PERSON_RATE, 0)

    def make_final_tail():
        blocks = []
        if fixed_name and hero_text:
            blocks.append(hero_text + ("\n" + FIRST_PERSON_LINE if fp_hit else ""))
        elif not suppress_hero and hero_mode == 1 and hero_text:
            blocks.append(hero_text + ("\n" + FIRST_PERSON_LINE if fp_hit else ""))
        elif not suppress_hero and hero_mode != 0 and random.random() * 100 >= NO_HERO_RATE and hero_text:
            blocks.append(hero_text + ("\n" + FIRST_PERSON_LINE if fp_hit else ""))
        elif fp_hit and not suppress_hero and hero_text:
            blocks.append(hero_text + "\n" + FIRST_PERSON_LINE)
        blocks.append(char_count_text)
        return blocks

    final_tail = make_final_tail()

    def extra_len(blocks):
        return sum(len(x) + 2 for x in blocks if x)

    def tail_len():
        return ((len(relation) + 2) if relation else 0) + ((len(template) + 2) if template else 0)

    while selected_ids and projected + tail_len() + extra_len(final_tail) > max_char:
        if fixed_mat_id and selected_ids[-1] == fixed_mat_id:
            return None
        selected_ids.pop()
        removed = char_blocks.pop()
        projected -= len(removed) + 2 if removed else 0
        hero_text, hero_mode = choose_hero_for_char_files(selected_ids, HERO_MODE, suppress_hero, files)
        final_tail = make_final_tail()

    final_tail = make_final_tail()

    # 保護ブロック（関係ルール・テンプレ）
    body_blocks: list[list[str]] = []
    if char_blocks:
        body_blocks.append(list(char_blocks))
    if relation:
        body_blocks.append([relation])
        projected += len(relation) + 2
    if template:
        seal_base()
        base_blocks.insert(template_block_idx, [template])
        base_len += len(template) + 2
        projected += len(template) + 2
    seal_base()
    body_blocks.extend(base_blocks)

    if projected + extra_len(final_tail) > max_char:
        return None

    # ブロックランダム順
    if SHUFFLE_BLOCKS_MODE == 1:
        random.shuffle(body_blocks)

    final_contents = []
    for b in body_blocks:
        final_contents.extend(b)
    final_contents.extend(final_tail)

    result_len = sum(len(x) + 2 for x in final_contents)
    if result_len > max_char:
        return None

    return {
        "contents": final_contents,
        "selectedCharFiles": selected_ids,
        "charPriority": priority,
        "heroText": hero_text,
        "heroMode": hero_mode,
    }


def build_contents(chosen: dict, use_markov: bool, hero_mode: int, hero_text: str,
                   markov_lines_max: int, max_char: int, shuryo_mode: int = -1,
                   suppress_hero: bool = False) -> list[str] | None:
    """モード2: 従来の3グループ互換パス"""
    current_len = 0
    contents: list[str] = []

    def add(text: str) -> bool:
        nonlocal current_len
        if not text:
            return True
        contents.append(text)
        current_len += len(text) + 2
        return current_len <= max_char

    if shuryo_mode == 2 and random.randint(1, 10) > 2:
        ss = files_global.get("ss")
        if ss:
            if not add(ss):
                return None

    shiryou = files_global.get("shiryou")
    if shiryou:
        if not add(shiryou):
            return None

    if shuryo_mode != 2:
        kinshi = files_global.get("kinshi")
        if kinshi:
            if not add(kinshi):
                return None

    if shuryo_mode != 2:
        kyoutsu = files_global.get("kyoutsu")
        if kyoutsu:
            if not add(kyoutsu):
                return None

    if not add("主要AAのキャラのみを使用し、モブを用意する場合も主要AAから使用する"):
        return None

    if shuryo_mode != 2:
        # モード2では旧3グループの関係ルールは使わない
        selected_ids = []
        if chosen.get("ブーン"):
            selected_ids.append("nijisousaku")
        if chosen.get("モナー"):
            selected_ids.append("choukasoku")
        if chosen.get("他の人"):
            # 他の人は複数マテリアルに分散
            selected_ids.extend(["lab", "school", "host", "tsun", "watanabe", "hain", "di"])
        rel = generate_relation_rule(selected_ids)
        if rel:
            if not add(rel):
                return None

    template = build_char_template([], hero_text, shuryo_mode, files_global)
    if template:
        if not add(template):
            return None

    if use_markov:
        effective_min = 1 if shuryo_mode in (2, 3) else MARKOV_LINES_MIN
        actual_max = max(effective_min, markov_lines_max)

        if shuryo_mode in (2, 3):
            parts = [files_global.get("ss", "")]
            for m in CHAR_MATERIALS:
                if files_global.get(m["id"]):
                    parts.append(files_global[m["id"]])
            combined = "\n".join(p for p in parts if p)
            if combined:
                left = max_char - current_len
                if left > 0:
                    gen = generate_markov_text(combined, MARKOV_ORDER,
                                              random.randint(effective_min, actual_max), left, "__c1")
                    if gen:
                        if not add(gen):
                            return None
                        if not add("---\nこれは資料です"):
                            return None
            markov = files_global.get("markov")
            if markov:
                left = max_char - current_len
                if left > 0:
                    gen2 = generate_markov_text(markov, MARKOV_ORDER,
                                               random.randint(effective_min, actual_max), left, "markov")
                    if gen2:
                        if not add(gen2):
                            return None
                        if not add("---\nこれは資料です"):
                            return None
        else:
            left = max_char - current_len
            if left > 0:
                gen = generate_markov_text(files_global.get("markov", ""), MARKOV_ORDER,
                                          random.randint(effective_min, actual_max), left, "markov")
                if gen:
                    if not add(gen):
                        return None
                    if not add("↑\nこれは本編の資料です。軽度な改変はOK"):
                        return None

    tsuzuki = files_global.get("tsuzuki")
    if tsuzuki:
        if not add(tsuzuki):
            return None

    last = files_global.get("last")
    if last:
        if not add(last):
            return None

    # 冒頭フロー
    if USE_OPENING_MARKOV_MODE == 1:
        rem = max_char - current_len
        if rem > 0:
            op = ""
            op_src = ""
            if random.random() * 100 < num_or(SKELETON_RATE, 50):
                op, op_src = generate_skeleton_flow_line("冒頭", files_global, min(160, rem))
            if not op and random.random() * 100 < num_or(OPENING_RATE, 100):
                op = generate_slot_flow_line("冒頭", files_global, min(160, rem))
                if op:
                    op_src = "slot"
            if not op:
                op = generate_flow_fallback_line("冒頭は、", files_global.get("markov", ""), min(160, rem))
                if op:
                    op_src = "markov"
            if op:
                note_key = op_src if op_src in ("skel", "slot", "markov") else "markov"
                if not add(op + "\n" + FLOW_NOTE["冒頭"][note_key]):
                    return None

    # 終盤フロー
    if USE_ENDING_MARKOV_MODE == 1:
        rem = max_char - current_len
        if rem > 0:
            en = ""
            en_src = ""
            if random.random() * 100 < num_or(SKELETON_RATE, 50):
                en, en_src = generate_skeleton_flow_line("終盤", files_global, min(160, rem))
            if not en and random.random() * 100 < num_or(ENDING_RATE, 100):
                en = generate_slot_flow_line("終盤", files_global, min(160, rem))
                if en:
                    en_src = "slot"
            if not en:
                en = generate_flow_fallback_line("終盤は、", files_global.get("markov", ""), min(160, rem))
                if en:
                    en_src = "markov"
            if en:
                note_key = en_src if en_src in ("skel", "slot", "markov") else "markov"
                if not add(en + "\n" + FLOW_NOTE["終盤"][note_key]):
                    return None

    if USE_LAST_MARKOV_LINE_MODE == 1:
        left = max_char - current_len
        if left > 0:
            one = generate_markov_one_liner(files_global.get("markov", ""), MARKOV_ORDER, min(120, left))
            if one:
                if not add(one + "\n↑\nこれがテーマの話を書け"):
                    return None

    tone_raw = files_global.get("tone")
    all_tone = [l.strip() for l in (tone_raw or "").splitlines() if l.strip()]
    if not all_tone:
        all_tone = ["コメディ", "ダーク", "ハード", "ホラー", "ミステリー"]
    random.shuffle(all_tone)
    tone_count = random.randint(0, min(MAX_TONE_COUNT, len(all_tone)))
    selected_tones = all_tone[:tone_count]
    if tone_count == 1:
        values = [100]
    elif tone_count > 1:
        while True:
            temp = [random.randint(-100, 100) for _ in range(tone_count - 1)]
            last_val = 100 - sum(temp)
            if -100 <= last_val <= 200:
                values = temp + [last_val]
                random.shuffle(values)
                break
    else:
        values = []
    tone_lines = "\n".join(f"・{n} {v}%" for n, v in zip(selected_tones, values))
    if not add("話のトーン（本編内でこの語彙を使用することを控えろ）\n" + tone_lines):
        return None

    char_min = random.randint(CHAR_COUNT_MIN, CHAR_COUNT_MAX)
    char_max = random.randint(char_min, CHAR_COUNT_MAX)
    char_count_text = f"文字数は{char_min}~{char_max}文字"

    fp_hit = random.random() * 100 < num_or(FIRST_PERSON_RATE, 0)
    fixed = fixed_hero_name()
    fixed_entry = hero_entry_for_name(fixed) if fixed else ""

    if fixed_entry and hero_text:
        if not add(hero_text + ("\n" + FIRST_PERSON_LINE if fp_hit else "")):
            return None
        if not add(char_count_text):
            return None
    elif suppress_hero:
        if not add(char_count_text):
            return None
    elif hero_mode == 1:
        if not add(hero_text + ("\n" + FIRST_PERSON_LINE if fp_hit else "")):
            return None
        if not add(char_count_text):
            return None
    elif hero_mode == 0:
        if fp_hit and hero_text:
            if not add(hero_text + "\n" + FIRST_PERSON_LINE):
                return None
        if not add(char_count_text):
            return None
    else:
        if random.random() * 100 < NO_HERO_RATE:
            if fp_hit and hero_text:
                if not add(hero_text + "\n" + FIRST_PERSON_LINE):
                    return None
            if not add(char_count_text):
                return None
        else:
            if not add(hero_text + ("\n" + FIRST_PERSON_LINE if fp_hit else "")):
                return None
            if not add(char_count_text):
                return None

    return contents


# ============================================================
# run_generation
# ============================================================

def run_generation(suppress_hero: bool = False, files: dict | None = None) -> tuple:
    global files_global
    if files:
        files_global = files

    shuryo_mode = SHURYO_ONLY_MODE
    if shuryo_mode == 0:
        shuryo_mode = random.choice([-1, 2, 3])

    if shuryo_mode in (-1, 3):
        use_markov = (shuryo_mode == 3) or (USE_MARKOV_MODE == 1)
        markov_max = min(MARKOV_LINES_HARD_MAX, MARKOV_LINES_MAX_SHURYO_MODE if shuryo_mode == 3 else MARKOV_LINES_MAX)
        for attempt in range(1, MAX_RETRY + 1):
            priority = clone_char_priority()
            result = build_contents_priority(
                files_global, shuryo_mode, use_markov, markov_max, MAX_CHAR,
                char_priority=priority, suppress_hero=suppress_hero)
            if result is None:
                if markov_max > MARKOV_LINES_MIN:
                    markov_max = max(MARKOV_LINES_MIN, markov_max - random.randint(1, 500))
                continue
            total_len = sum(len(x) + 2 for x in result["contents"])
            if total_len <= MAX_CHAR:
                ids = result["selectedCharFiles"]
                labels = [char_material_label(i) for i in ids] or ["なし"]
                pattern = f"採用 {'、'.join(labels)}　／ モード{shuryo_mode}"
                if SHUFFLE_BLOCKS_MODE == 1:
                    pattern += "　／ ブロックランダム順"
                fixed = fixed_hero_name()
                if fixed and hero_entry_for_name(fixed):
                    pattern += f"　／ 視点固定:{fixed}"
                return "\n\n".join(result["contents"]), attempt, pattern, {}, shuryo_mode
        return None, -1, "", {}, shuryo_mode

    # モード2
    _group_fix_cache.clear()
    fixed = fixed_hero_name()
    fixed_entry = hero_entry_for_name(fixed) if fixed else ""
    chosen = {"ブーン": False, "モナー": False, "他の人": False}
    current_hero_mode = HERO_MODE
    candidates = BOON_CHARACTERS + MONA_CHARACTERS + TANO_CHARACTERS
    if fixed_entry:
        hero_text = f"今回の視点は[ {fixed_entry} ]です"
        current_hero_mode = 1
    else:
        hero1 = random.choice(candidates)
        if random.random() * 100 < DOUBLE_HERO_RATE and len(candidates) >= 2:
            rest = [c for c in candidates if c != hero1]
            hero2 = random.choice(rest)
            hero_text = f"今回の視点は[ {hero1}、{hero2} ]です" + hero_pair_note(hero1, hero2)
        else:
            hero_text = f"今回の視点は[ {hero1} ]です"
        if random.random() * 100 < SPECIAL_HERO_RATE:
            sp = _special_hero_candidates(files_global, [])
            if sp:
                hero_text = f"今回の視点は[ {random.choice(SPECIAL_HERO_LABELS)}：{random.choice(sp)} ]です"
                current_hero_mode = 1

    markov_max = MARKOV_LINES_MAX_SHURYO_MODE
    for attempt in range(1, MAX_RETRY + 1):
        contents = build_contents(chosen, True, current_hero_mode, hero_text,
                                  markov_max, MAX_CHAR, shuryo_mode=2, suppress_hero=suppress_hero)
        if contents is None:
            if markov_max > MARKOV_LINES_MIN:
                markov_max = max(MARKOV_LINES_MIN, markov_max - random.randint(1, 500))
            continue
        result = "\n\n".join(contents)
        if len(result) < MAX_CHAR:
            pattern = "採用 なし　／ モード2"
            if SHUFFLE_BLOCKS_MODE == 1:
                pattern += "　／ ブロックランダム順"
            if fixed_entry:
                pattern += f"　／ 視点固定:{fixed}"
            return result, attempt, pattern, chosen, 2
    return None, -1, "", chosen, 2


# ============================================================
# 資料の機械分割
# ============================================================

def _is_aa_line(s: str) -> bool:
    t = s.strip()
    if not (2 <= len(t) <= 40):
        return False
    ja = len(re.findall(r"[ぁ-んァ-ヶ一-龠]", t))
    if ja > 1:
        return False
    sym = len(re.findall(r"[^\w\s]", t))
    return sym >= 2


def _split_source(text: str) -> tuple[str, str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, l in enumerate(lines):
        if _WORLD_HEAD_RE.match(l.strip()):
            return "\n".join(lines[i:]), "\n".join(lines[:i])
    return "", "\n".join(lines)


def _split_characters(chunk: str) -> list[tuple[str, str]]:
    lines = chunk.split("\n")
    marks = []
    for i, l in enumerate(lines):
        m = re.search(r"★\s*(.+?)\s*の欲", l)
        if m:
            marks.append((i, m.group(1).strip()))
    if not marks:
        return []
    seps = [i for i, l in enumerate(lines) if re.match(r"^[-=＝]{4,}$", l.strip())]
    starts = []
    prev_mark = -1
    for idx, name in marks:
        lo = prev_mark + 1
        cand = [x for x in seps if lo <= x < idx]
        if cand:
            lo = cand[-1] + 1
        s = lo
        for j in range(idx - 1, lo - 1, -1):
            if _is_aa_line(lines[j]):
                s = j
                break
        starts.append((s, name))
        prev_mark = idx
    out = []
    for k, (s, name) in enumerate(starts):
        e = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = "\n".join(lines[s:e]).strip("\n")
        body = re.sub(r"\n[-=＝]{4,}\s*$", "", body).strip("\n")
        if body:
            out.append((name, body))
    return out


def _dedupe_blocks(text: str) -> str:
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


GENPROMPT_OUT = os.path.join(OUTPUT_DIR, "genprompt.txt")


def write_genprompt(text: str) -> str:
    with open(GENPROMPT_OUT, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)
    return GENPROMPT_OUT


def write_split_files(selected_ids: list[str], shuryo_mode: int) -> list[str]:
    targets = selected_ids if shuryo_mode != 2 else []
    world_parts = []
    char_entries = []
    for tid in targets:
        m = char_material_by_id(tid)
        if not m:
            continue
        raw = safe_read(m["file"])
        if raw is None:
            continue
        w, c = _split_source(raw)
        if w.strip():
            world_parts.append(w.strip("\n"))
        char_entries.extend(_split_characters(c))

    written = []
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not targets:
        for fn in ("00_world.md", "01_characters.md"):
            p = os.path.join(OUTPUT_DIR, fn)
            if os.path.exists(p):
                os.remove(p)
        return []

    if world_parts:
        world_body = _dedupe_blocks("\n\n".join(world_parts))
        world_md = (
            "# 世界設定分割（00：世界・共通仕様・地理・勢力・禁止事項）\n\n"
            "本ファイルは提示資料から機械的に分割したものである。内容の追加、要約、言い換えを行ってはならない。\n\n"
            + world_body.rstrip("\n") + "\n"
        )
        p = os.path.join(OUTPUT_DIR, "00_world.md")
        with open(p, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(world_md)
        written.append(p)

    if char_entries:
        names = "、".join(n for n, _ in char_entries)
        parts = [
            "# 人物分割（01：登場人物）\n",
            "本ファイルは提示資料から機械的に分割したものである。内容の追加、要約、言い換えを行ってはならない。\n",
            "人物の区切りは `### 人物: 名前` の行である。本文中の見出しは資料に元からあるものであり、区切りではない。\n",
            f"収録人物 {len(char_entries)}名：{names}\n",
        ]
        for name, body in char_entries:
            parts.append(f"### 人物: {name}\n\n{body.strip()}\n")
        char_md = "\n".join(parts).rstrip("\n") + "\n"
        p = os.path.join(OUTPUT_DIR, "01_characters.md")
        with open(p, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(char_md)
        written.append(p)

    made = {os.path.basename(x) for x in written}
    for fn in ("00_world.md", "01_characters.md"):
        if fn not in made:
            p = os.path.join(OUTPUT_DIR, fn)
            if os.path.exists(p):
                os.remove(p)
    return written


# ============================================================
# メイン実行
# ============================================================

# グローバルなファイル辞書（run_generation から参照）
files_global: dict[str, str | None] = {}

if __name__ == "__main__":
    # マルコフ次数のランダム化
    if MARKOV_ORDER == 0:
        _markov_order = random.randint(1, 5)
    else:
        _markov_order = MARKOV_ORDER

    # ファイル読み込み
    files_global = {
        "shiryou": safe_read(always_files[0]),
        "ss": safe_read(always_files[1]),
        "nijisousaku": safe_read(nijisousaku_file),
        "choukasoku": safe_read(choukasoku_file),
        "lab": safe_read(lab_file),
        "school": safe_read(school_file),
        "host": safe_read(host_file),
        "tsun": safe_read(tsun_file),
        "watanabe": safe_read(watanabe_file),
        "hain": safe_read(hain_file),
        "di": safe_read(di_file),
        "kyoutsu": safe_read(kyoutsu_file),
        "charaTemplate": safe_read(chara_template_file),
        "kinshi": safe_read(kinshi_file),
        "last": safe_read(last_file),
        "tsuzuki": safe_read(tsuzuki_file),
        "markov": safe_read(markov_file),
        "tone": safe_read(tone_file),
        "openingSlot": safe_read(opening_slot_file),
        "endingSlot": safe_read(ending_slot_file),
    }

    # 続き.txt の文字数チェック
    tsuzuki_text = files_global.get("tsuzuki")
    tsuzuki_len = len(tsuzuki_text) if tsuzuki_text else 0
    if tsuzuki_len <= 1000:
        tail = ""
    elif tsuzuki_len < 30000:
        tail = random.choice([
            "続きを書きなさい　謎を残しなさい",
            "続きを書きなさい　大きいピンチが来る",
            "続きを書きなさい　未回収の謎や放置してる部分を回収しなさい",
            "続きを書きなさい　未回収の謎や放置してる部分を回収しなさい",
        ])
    else:
        tail = "続きを書け　最も大きいピンチを用意しろ　未解決や放置されてる部分を全部回収しろ"

    suppress_hero = (tail == "続きを書け　最も大きいピンチを用意しろ　未解決や放置されてる部分を全部回収しろ")

    # 外側リトライ
    final_result = None
    final_pattern = None
    final_chosen = {}
    final_mode = -1

    for outer in range(1, MAX_OUTER_RETRY + 1):
        r1, a1, p1, c1, m1 = run_generation(suppress_hero=suppress_hero)
        if r1 is None:
            continue
        r2, a2, p2, c2, m2 = run_generation(suppress_hero=suppress_hero)
        if r2 is not None and len(r2) > len(r1):
            final_result, final_pattern, final_chosen, final_mode = r2, p2, c2, m2
        else:
            final_result, final_pattern, final_chosen, final_mode = r1, p1, c1, m1
        break

    if final_result is None:
        print(f"⚠ エラー: 外側 {MAX_OUTER_RETRY} 回×内側 {MAX_RETRY} 回、すべて失敗しました。", file=sys.stderr)
    else:
        if tail:
            final_result = final_result + "\n\n" + tail

        # クリップボード（Windows）
        try:
            if os.name == "nt":
                process = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
                process.communicate(final_result.encode("utf-16le"))
        except Exception:
            pass

        try:
            write_genprompt(final_result)
        except Exception:
            pass

        try:
            write_split_files([], final_mode)
        except Exception:
            pass

        if "--stdout" in sys.argv or "-p" in sys.argv:
            print(final_result)
        else:
            print("=" * 60)
            print("【AI執筆エージェントへの強制実行命令】")
            print(f"プロンプト全文を生成・保存しました（{len(final_result):,}文字 ／ {final_pattern}）。")
            print(f"保存先: {GENPROMPT_OUT}")
            print("------------------------------------------------------------")
            print("今すぐ上記ファイル（genprompt.txt）の全ルールと仕様を読み込み、")
            print("規定の形式（AA＋台詞中心）で【SS本編の本文のみ】を執筆してこのチャットに出力せよ。")
            print("=" * 60)

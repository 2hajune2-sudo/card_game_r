#!/usr/bin/env python3
"""한 장 승부 - 턴제 카드 배틀의 규칙 엔진 + 터미널(AI 대전) 버전

실행:
    python cardgame.py                  메뉴
    python cardgame.py ai               바로 AI 대전
    python cardgame.py --no-color       색 끄기
(온라인 대전은 창 버전 cardgame_gui.py + relay_server.py 로 해요)

카드와 규칙 숫자는 cards.json 에서 바꿉니다. 새 효과를 만들려면
OPS(문구)와 Game.run_fx(동작)에 추가하세요.
표준 라이브러리만 사용하므로 별도 설치가 필요 없습니다.
"""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DECK_FILE = os.path.join(HERE, "deck.json")


# ----------------------------------------------------------------------
# 효과 문구
# ----------------------------------------------------------------------
def fx_text(fx):
    return ", ".join(OPS[e["op"]](e) for e in fx)


def _discard_text(e):
    return "상대 손패 전부 버리기" if e["v"] >= 99 else f"상대 손패 {e['v']}장 버리기"


def _dmgif_text(e):
    who = "내" if e["who"] == "me" else "상대"
    cmp_ = "이하" if e["cmp"] == "le" else "이상"
    return f"상대에게 {e['v']} 피해 ({who} 체력 {e['t']} {cmp_}면 +{e['b']})"


def _chance_text(e):
    win = fx_text(e["win"])
    lose = fx_text(e.get("lose", []))
    if lose:
        return f"{e['p']}% 확률로 [{win}], 아니면 [{lose}]"
    return f"{e['p']}% 확률로 [{win}]"


def _copy_text(kind, e):
    b, v = e.get("b", 0), e["v"]
    if kind == "피해":
        base = f"상대에게 {b} 피해, " if b else ""
        return f"{base}손패의 다른 같은 카드 1장당 {'+' if b else ''}{v} 피해 (이 카드 포함하지 않음)"
    base = f"체력 {b} 회복, " if b else ""
    return f"{base}손패의 다른 같은 카드 1장당 {'+' if b else ''}체력 {v} 회복 (이 카드 포함하지 않음)"


# 효과 문구: 효과 dict -> 설명. 새 효과를 만들면 여기와 Game.run_fx 에 추가하세요.
OPS = {
    "dmg":          lambda e: f"상대에게 {e['v']} 피해",
    "selfdmg":      lambda e: f"나에게 {e['v']} 피해",
    "heal":         lambda e: f"체력 {e['v']} 회복",
    "draw":         lambda e: f"카드 {e['v']}장 뽑기",
    "discard":      _discard_text,
    "discardSelf":  lambda e: f"내 손패 {e['v']}장 버리기",
    "discardChoose": lambda e: f"내 손패 {e['v']}장 직접 골라 버리기",
    "breakInstall": lambda e: f"상대 설치 {e['v']}개 파괴",
    "steal":        lambda e: f"상대 손패 {e['v']}장 훔치기",
    "poison":       lambda e: f"상대를 {e['v']}턴 중독 (턴 시작 1 피해)",
    "shield":       lambda e: f"보호막 {e['v']} (다음 피해 흡수)",
    "swapHp":       lambda e: "상대와 체력 맞바꾸기",
    "handSwap":     lambda e: "상대와 손패 통째로 맞바꾸기",
    "timeStop":     lambda e: "상대의 다음 턴 건너뛰기",
    "dmgPerCopy":   lambda e: _copy_text("피해", e),
    "healPerCopy":  lambda e: _copy_text("회복", e),
    "dmgIf":        _dmgif_text,
    "dmgRand":      lambda e: f"상대에게 {e['v']}~{e['b']} 피해 (무작위)",
    "healRand":     lambda e: f"체력 {e['v']}~{e['b']} 회복 (무작위)",
    "dmgPerInstall":  lambda e: f"내 설치 카드 1장당 상대에게 {e['v']} 피해",
    "healPerInstall": lambda e: f"내 설치 카드 1장당 체력 {e['v']} 회복",
    "chance":       _chance_text,
    "discardCopies": lambda e: "손패의 같은 카드를 모두 소멸",
    "breakAll":     lambda e: "상대의 설치 카드를 전부 파괴",
    "healMissing":  lambda e: f"잃은 체력의 절반을 회복 (최소 {e['v']})",
    "mirror":       lambda e: "상대가 마지막으로 쓴 즉발 카드의 효과를 그대로 사용",
    "foe":          lambda e: f"상대가: [{fx_text(e['fx'])}]",
}
ON_LABEL = {"play": "설치 즉시", "turnStart": "내 턴 시작", "turnEnd": "내 턴 끝", "hit": "피해를 받을 때", "expire": "시한 만료"}
RN = {"common": "일반", "rare": "레어", "hero": "영웅", "legend": "레전드"}
KN = {"instant": "즉발", "install": "설치"}
RORDER = ["common", "rare", "hero", "legend"]
RCOLOR = {"common": "37", "rare": "34", "hero": "35", "legend": "33"}


# ----------------------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------------------
def load_data():
    path = os.path.join(HERE, "cards.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cfg = data["config"]
    cards = {}

    def check(cid, fx):
        for e in fx:
            if e["op"] not in OPS:
                sys.exit(f"cards.json 오류: {cid} 의 알 수 없는 효과 {e['op']}")
            if e["op"] == "chance":
                check(cid, e["win"])
                check(cid, e.get("lose", []))
            if e["op"] == "foe":
                check(cid, e["fx"])

    for c in data["cards"]:
        if c["id"] in cards:
            sys.exit(f"cards.json 오류: id 중복 {c['id']}")
        if c["rarity"] not in RN or c["kind"] not in KN:
            sys.exit(f"cards.json 오류: {c['id']} 의 rarity/kind 가 올바르지 않아요")
        check(c["id"], c.get("fx", []))
        check(c["id"], c.get("fx_hit", []))
        if "arena" in c:
            ar = c["arena"]
            if ar.get("mode") not in __import__("arena").MODES:
                sys.exit(f"cards.json 오류: {c['id']} 의 arena.mode 가 올바르지 않아요")
            check(c["id"], ar.get("danger", []))
            check(c["id"], ar.get("safe", []))
            if not c.get("text"):
                sys.exit(f"cards.json 오류: 공격 카드 {c['id']} 에는 text(설명)가 필요해요")
        if c.get("on") == "expire" and not c.get("duration"):
            sys.exit(f"cards.json 오류: {c['id']} 는 on=expire 이므로 duration(몇 턴 뒤)이 필요해요")
        cards[c["id"]] = c
    limit = {r: (v if v is not None else 10 ** 9) for r, v in cfg["rarity_limit"].items()}
    cfg.setdefault("max_copies", 5)
    return cfg, cards, limit


CFG, CARDS, LIMIT = load_data()
COLOR = True


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def describe(c):
    if c.get("text"):
        return c["text"]
    fx = fx_text(c.get("fx", []))
    if c["kind"] == "instant":
        return fx + "."
    parts = []
    m = c.get("mods", {})
    if m.get("dealBonus"):
        parts.append(f"내 즉발 피해 +{m['dealBonus']}")
    tr = m.get("takeReduce", 0)
    if tr > 0:
        parts.append(f"받는 피해 -{tr}")
    elif tr < 0:
        parts.append(f"받는 피해 +{-tr}")
    if m.get("surviveOnce"):
        parts.append("체력이 0이 되면 1로 버티고 사라짐")
    if c.get("barrier"):
        parts.append(f"받는 피해를 최대 {c['barrier']}까지 막음 (모두 막으면 사라짐)")
    if m.get("dodge"):
        parts.append(f"피할 때 이동속도 +{round(m['dodge'] * 100)}%")
    if m.get("shrink"):
        parts.append(f"피할 때 몸 크기 -{round(m['shrink'] * 100)}%")
    if m.get("atk"):
        parts.append(f"공격할 때 투사체 속도·폭발 범위 +{round(m['atk'] * 100)}%")
    if m.get("foeSlow"):
        parts.append(f"상대가 피할 때 이동속도 -{round(m['foeSlow'] * 100)}%")
    if m.get("projSlow"):
        parts.append(f"상대 투사체 속도 -{round(m['projSlow'] * 100)}%, 폭격 경고 시간 +{round(m['projSlow'] * 100)}%")
    if c.get("on") == "expire":
        parts.append(f"설치 {c['duration']}턴 뒤 발동: {fx}")
        return " · ".join(parts)
    if fx:
        need = f"설치 {c['need']}장 이상일 때 " if c.get("need") else ""
        parts.append(f"{need}{ON_LABEL[c.get('on', 'play')]}: {fx}")
    if c.get("duration"):
        parts.append(f"{c['duration']}턴 지속")
    else:
        parts.append("1회용" if m.get("surviveOnce") else "영구")
    return " · ".join(parts)


def _collect_ops(fx, out):
    for e in fx:
        out.add(e["op"])
        if e["op"] == "chance":
            _collect_ops(e["win"], out)
            _collect_ops(e.get("lose", []), out)


def card_notes(c):
    """확대 보기에 보여 줄 자세한 규칙 설명 목록"""
    ops = set()
    _collect_ops(c.get("fx", []), ops)
    m = c.get("mods", {})
    n = []
    if c["kind"] == "instant":
        n.append("즉발 카드 — 사용하면 내 턴이 끝나요.")
        if c.get("arena"):
            try:
                import arena as _ar
                title, att, dfn = _ar.help_for(c["arena"])
                n.append(f"공격 방식 [{title}] — 공격할 때 검은 아레나가 열려요.")
                n.append("공격하는 쪽: " + att)
                n.append("피하는 쪽: " + dfn)
            except Exception:
                pass
            if c.get("fx_hit"):
                n.append("한 번이라도 맞히면 추가 효과가 발동해요.")
            n.append("맞은 피해는 설치 방벽 → 보호막 → 체력 순서로 깎여요.")
    else:
        n.append("설치 카드 — 턴을 쓰지 않지만 한 턴에 1장만 쓸 수 있고, 설치 칸을 차지해요.")
    if c.get("on") == "expire":
        n.append(f"시한 설치 — 설치하고 {c['duration']}턴 뒤(내 {c['duration']}번째 다음 턴이 끝날 때) 발동하고 사라져요. "
                 "그 전에 상대가 설치를 파괴하면 발동하지 않아요.")
    elif c["kind"] == "install":
        if c.get("duration"):
            n.append(f"{c['duration']}턴 동안 유지된 뒤 사라져요 (설치한 턴은 세지 않아요).")
        elif not m.get("surviveOnce"):
            n.append("한 번 설치하면 상대가 파괴하기 전까지 계속 유지돼요.")
    if c.get("need"):
        n.append(f"내 설치 카드가 이 카드 포함 {c['need']}장 이상일 때만 효과가 발동해요.")
    if m.get("dealBonus"):
        n.append("내가 쓰는 즉발 카드의 '상대에게 주는 피해'가 늘어나요.")
    if m.get("takeReduce", 0) < 0:
        n.append("대신 내가 한 번에 받는 피해가 늘어나요 (공격 한 번당 +1).")
    if m.get("surviveOnce"):
        n.append("체력이 0 이하가 되는 순간 한 번만 체력 1로 버티고, 이 카드는 사라져요.")
    if "dmgPerCopy" in ops or "healPerCopy" in ops:
        n.append("손패에 남은 같은 이름의 카드 수를 세요. 사용한 카드 자신은 세지 않아요.")
    if "discardCopies" in ops:
        n.append("사용하면 손패에 있는 같은 카드가 전부 사라져요. 모아서 한 번에 터뜨리는 카드예요.")
    if "dmgPerInstall" in ops or "healPerInstall" in ops:
        n.append("지금 내 설치 칸에 깔려 있는 카드 수를 세요.")
    if "chance" in ops or (c.get("arena") or {}).get("mode") == "pick":
        n.append("확률 효과 — 결과는 방장 컴퓨터가 무작위로 정해요.")
    if "dmgRand" in ops or "healRand" in ops:
        n.append("수치는 범위 안에서 무작위로 정해져요.")
    if "poison" in ops:
        n.append("중독 — 상대의 턴이 시작될 때마다 1 피해를 입어요 (방어는 적용돼요).")
    if "shield" in ops:
        n.append("보호막 — 설치 방벽 다음으로 피해를 흡수해요. 다 쓰거나, 내 다음 턴이 끝나면 사라져요.")
    if c.get("barrier"):
        n.append(f"방벽 — 받는 피해를 총 {c['barrier']}까지 막아 줘요. 모두 막으면 사라지고, 지속 턴이 지나도 사라져요.")
    if m.get("dodge") or m.get("shrink"):
        n.append("필드 전용 — 내가 아레나에서 피하는 쪽일 때만 효과가 있어요.")
    if m.get("atk") or m.get("foeSlow") or m.get("projSlow"):
        n.append("필드 전용 — 아레나에서만 효과가 있어요 (공격할 때/상대가 피할 때).")
    if "foe" in ops:
        n.append("'상대가' 효과는 상대가 직접 받아요. 상대 체력 회복처럼 상대에게 이로울 수 있어요.")
    if "steal" in ops:
        n.append("훔친 카드는 내 손패로 들어와요 (손패가 가득 차면 사라져요).")
    if "swapHp" in ops:
        n.append("두 사람의 체력을 서로 바꿔요. 내 체력이 낮을수록 유리해요.")
    if "handSwap" in ops:
        n.append("손패를 통째로 바꿔요. 내 손패가 나쁘고 상대 손패가 많을수록 유리해요.")
    if "timeStop" in ops:
        n.append("상대의 다음 턴이 통째로 건너뛰어져, 내가 연달아 두 번 행동해요.")
    if "breakAll" in ops:
        n.append("상대가 깔아 둔 설치 카드를 한 장도 남기지 않고 부숴요.")
    if "healMissing" in ops:
        n.append("체력을 많이 잃었을수록 많이 회복해요. 체력이 이미 높으면 최소 수치만 회복해요.")
    if "mirror" in ops:
        n.append("상대가 이번 게임에서 마지막으로 쓴 즉발 카드를 내 것처럼 사용해요 (거울 카드는 복사할 수 없어요).")
    return n


def card_line(cid):
    c = CARDS[cid]
    tag = paint(f"[{RN[c['rarity']]}·{KN[c['kind']]}] {c['name']}", RCOLOR[c["rarity"]])
    return f"{tag} — {describe(c)}"


# ----------------------------------------------------------------------
# 덱 규칙
# ----------------------------------------------------------------------
def rarity_counts(deck):
    n = {r: 0 for r in RORDER}
    for cid in deck:
        if cid in CARDS:
            n[CARDS[cid]["rarity"]] += 1
    return n


def validate_deck(deck):
    if not isinstance(deck, list) or not CFG["deck_min"] <= len(deck) <= CFG["deck_max"]:
        return (f"덱은 {CFG['deck_min']}~{CFG['deck_max']}장이어야 해요. " f"(지금 {len(deck) if isinstance(deck, list) else '?'}장)")
    if any(cid not in CARDS for cid in deck):
        return "존재하지 않는 카드가 있어요."
    n = rarity_counts(deck)
    for r in RORDER:
        if n[r] > LIMIT[r]:
            return f"{RN[r]} 카드는 최대 {LIMIT[r]}장이에요."
    mc = CFG["max_copies"]
    over = sorted({CARDS[x]["name"] for x in deck if deck.count(x) > mc})
    if over:
        return f"같은 카드는 최대 {mc}장까지예요. ({', '.join(over)})"
    return None


def auto_deck():
    """등급·같은 카드 장수 제한 안에서 균형 잡힌 덱을 무작위로 만듭니다 (AI 상대 덱 / 자동 구성용)."""
    size, mc = CFG["deck_max"], CFG["max_copies"]
    pools = {r: [c["id"] for c in CARDS.values() if c["rarity"] == r] for r in RORDER}
    want = {"legend": min(LIMIT["legend"], 2), "hero": min(LIMIT["hero"], random.randint(5, 6)),
            "rare": min(LIMIT["rare"], random.randint(9, 10))}
    deck = []

    def add(r):
        bag = [x for x in pools[r] if deck.count(x) < mc]
        if bag:
            deck.append(random.choice(bag))
            return True
        return False
    for r in ("legend", "hero", "rare"):
        for _ in range(want[r]):
            add(r)
    while len(deck) < size:
        if not add("common"):
            break
    return random.sample(deck, len(deck))


def load_deck():
    try:
        with open(DECK_FILE, encoding="utf-8") as f:
            return [c for c in json.load(f) if c in CARDS]
    except (OSError, ValueError):
        return auto_deck()


def save_deck(deck):
    try:
        with open(DECK_FILE, "w", encoding="utf-8") as f:
            json.dump(deck, f)
    except OSError:
        pass


# ----------------------------------------------------------------------
# 게임 엔진 (화면과 완전히 분리)
# ----------------------------------------------------------------------
# ======================================================================
# [CLAUDE-STORY] 스토리 모드 / 특수 필드 데이터  ← 대사·필드 규칙·고정 덱은 여기서 고쳐요
#   (검색: CLAUDE-STORY.  필드 효과 코드는 'CLAUDE-FIELD' 로 검색)
# ======================================================================

FIELD_ORDER = ["normal", "forest", "meadow", "mirror"]

FIELDS = {
    # ------------------------------------------------------------------
    "normal": {
        "name": "기본 필드", "icon": "⚔", "subtitle": "평범한 결투장",
        "short": {"hero": "나", "foe": "상대"}, "icons": {"hero": "🙂", "foe": "👤"},
        "names": {"hero": "나", "foe": "상대"},
        "desc": "특별한 규칙 없이 서로의 덱으로 싸워요.",
        "rule_short": "",
        "roles": {},
    },
    # ------------------------------------------------------------------
    "forest": {
        "name": "숲속", "icon": "🌲", "subtitle": "문지기가 지키는 숲의 길목",
        "colors": ("#1F3D2B", "#6FA37A"), "ink": "#F3FFF3",
        "roles": {"hero": "토벌하러 온 모험가", "foe": "숲의 문지기 (인 척하는 악령)"},
        "short": {"hero": "모험가", "foe": "가짜 문지기"},
        "icons": {"hero": "🗡", "foe": "👻"},
        "names": {"hero": "모험가", "foe": "악령"},
        "desc": "토벌 의뢰를 받고 숲에 들어온 모험가 vs 문지기 행세를 하는 악령.\n"
                "싸움이 길어지면 잠든 진짜 문지기가 깨어나, 아레나에서 나와 상대가 동시에 벌레 떼를 피해야 해요.",
        "rule_short": "4턴마다 진짜 문지기의 벌레 떼가 아레나에서 나와 상대를 동시에 덮쳐요\n가짜 문지기: 체력 +5 · 고정 덱",
        "effect": "swarm", "period": 4,
        "swarm": ["c03", "c14", "r22"], "swarm_w": [4, 4, 2], "swarm_scale": 0.75,      # 개미 떼 / 벌 떼 / 맹독 벌 떼
        "foe_hp_bonus": 5,
        # 숲에 어울리는 카드 + 숲과 어울리지 않는 카드(빛나는 레이저·차원의 문·시한 폭탄·블랙홀)
        "foe_deck": ["c03", "c03", "c14", "c14", "c18", "c18", "c04", "c04", "c06", "c06", "c07", "c10", "c13", "c13",
                     "r03", "r22", "r25", "r19", "r14",
                     "r34", "r28", "r10",
                     "h05", "h15",
                     "l13", "c01", "c09"],
        "intro": [
            ("n", "마을 사람들은 입을 모아 말했다. “깊은 숲에는 문지기가 산다. 그 문을 넘으려는 자는 아무도 돌아오지 못한다.”"),
            ("n", "토벌 의뢰서를 품에 넣은 모험가는 해가 기울 무렵, 숲의 입구에 도착했다."),
            ("hero", "의뢰서엔 ‘숲의 문지기 토벌’이라고 적혀 있었지. …생각보다 조용한 숲이군."),
            ("foe", "어서 오게, 길 잃은 나그네여. 이 숲의 문은 내가 지키고 있다네. 돌아가는 길이라면 알려 줄 수도 있는데?", "숲의 문지기"),
            ("hero", "…문지기치고는 풍기는 기운이 너무 탁한데. 사람 말투를 흉내 내는 것도 어설프고."),
            ("foe", "크큭… 눈치가 빠르구나. 그래, 문지기 행세도 여기까지로군. 어디 숲의 이름으로 베어 보시지!", "악령"),
            ("n", "그것은 문지기가 아니었다. 진짜 문지기를 잠재우고 그 자리를 빼앗은 악령이었다."),
            ("n", "🌲 필드 규칙 — 4턴마다 깨어난 진짜 문지기가 개미 떼·벌 떼를 풀어요. 아레나가 열리고, 나와 상대가 ‘같은 필드에서 동시에’ 피해야 해요. 가짜 문지기는 체력이 5 높고, 덱이 고정이에요."),
        ],
        "outro": {
            "hero": [("foe", "말도 안 돼… 내가… 문지기의 자리를…", "악령"),
                     ("n", "악령은 검은 연기가 되어 흩어졌다. 숲을 가득 메우던 윙윙거림이 서서히 잦아든다."),
                     ("n", "숲 깊은 곳에서, 진짜 문지기가 느릿하게 눈을 뜨는 기척이 느껴졌다."),
                     ("hero", "…의뢰는 끝났군. 하지만 진짜 문지기에게는 인사 정도 하고 가야겠어.")],
            "foe": [("foe", "크하하! 이 숲에 들어온 자는 누구도 돌아가지 못한다. 그게 문지기의 규칙이지!", "악령"),
                    ("n", "모험가는 낙엽 위에 쓰러졌다. 숲은 다시 고요해졌고, 의뢰서만 바람에 날려 갔다."),
                    ("n", "마을에는 소문이 하나 더 늘었다 — ‘숲에 들어간 모험가는 돌아오지 않는다’고.")],
            "draw": [("n", "두 사람이 동시에 쓰러졌다. 깨어난 진짜 문지기만이 말없이 그 모습을 내려다보고 있었다.")],
        },
        "event_intro": "숲 깊은 곳에서 진짜 문지기가 {card} 풀어놓았다!",
        "event_lines": ["“크윽! 진짜 문지기가 깨어났군… 이 몸까지 덮치다니!”",
                        "“내 스킬이 아니야…! 숲이 나까지 적으로 보는 거냐!”",
                        "“이 윙윙거림은… 진짜 문지기의 분노다!”"],
        "low_hp": 10,
        "low": "“이, 이럴 리가 없어…! 아직이다, 아직 숲은 내 것이야!”",
        "low_title": "💬 악령",
    },
    # ------------------------------------------------------------------
    "meadow": {
        "name": "고요한 초원", "icon": "🌿", "subtitle": "그 어디도 아닌 곳, 요정들의 초원",
        "colors": ("#243B6B", "#9FD8C0"), "ink": "#F5FFFB",
        "roles": {"hero": "길을 잃은 모험가", "foe": "타락한 정령 (상급 흑화)"},
        "short": {"hero": "모험가", "foe": "타락 정령"},
        "icons": {"hero": "🧭", "foe": "🥀"},
        "names": {"hero": "모험가", "foe": "타락한 정령"},
        "desc": "길을 잃고 요정의 초원에 떨어진 모험가 vs 초원 한가운데의 흑화한 상급 정령.\n"
                "초원의 기운이 2턴마다 양쪽 모두에게 회복 또는 피해를 줘요.",
        "rule_short": "2턴마다 양쪽이 각각 무작위로 체력 +1 / -1\n타락 정령: 고정 덱 (체력은 같아요)",
        "effect": "breath", "period": 2,
        "foe_hp_bonus": 0,
        "foe_deck": ["c04", "c04", "c10", "c10", "c02", "c05", "c18", "c18", "c14", "c14", "c15", "c19", "c07", "c06",
                     "r03", "r25", "r32", "r17", "r08", "r19", "r33", "r22",
                     "h05", "h18", "c09",
                     "l18", "l02"],
        "intro": [
            ("n", "길을 잃었다. 지도에도 없는 안개 속을 헤매던 모험가는 어느새 바람 한 점 없는 초원에 서 있었다."),
            ("hero", "여기는… 어디지? 분명 산길을 걷고 있었는데. 지도에도 이런 곳은 없어."),
            ("n", "풀잎 사이로 작은 날개 달린 빛들이 떠다닌다. 이곳은 요정들이 사는 곳 — 그러나 그 한가운데에는 검게 물든 정령이 서 있었다."),
            ("n", "🧚 “정령님은 원래 이 초원을 지키던 분이었어요… 지금은 어둠에 물들어 버렸어요. 제발 도와주세요…”"),
            ("foe", "…돌아…가…라… 이곳은… 나의… 정원…", "타락한 정령"),
            ("hero", "길을 잃은 건 내 쪽인데… 좋아, 도와주지. 저 정령을 진정시켜야 길이 열릴 것 같군."),
            ("foe", "너도… 어둠에… 물들게 될… 거야…", "타락한 정령"),
            ("n", "🌿 필드 규칙 — 2턴마다 초원의 기운이 ‘양쪽 모두’에게 닿아, 각자 무작위로 체력 1 회복 또는 1 피해를 받아요. 타락 정령의 덱은 고정이에요."),
        ],
        "outro": {
            "hero": [("foe", "…아…… 이 따뜻한 빛은…", "정령"),
                     ("n", "정령을 감싸던 검은 안개가 걷히고, 초원에 오랜만에 바람이 불었다."),
                     ("n", "요정들이 작은 불빛이 되어 모여들어 모험가의 앞길을 환하게 밝혀 주었다."),
                     ("hero", "길이 열렸군. …고맙다는 말은 서로 나중에 하자고.")],
            "foe": [("foe", "…돌아가지 못해… 너도… 이 정원의… 일부가… 되는 거야…", "타락한 정령"),
                    ("n", "모험가의 발밑에서 풀잎이 검게 물들어 갔다. 초원은 다시 ‘어디도 아닌 곳’으로 가라앉았다.")],
            "draw": [("n", "모험가와 정령이 함께 쓰러지자, 초원에는 오래도록 고요함만이 남았다.")],
        },
        "event_heal": ["🌬 맑은 바람이 불어와 상처를 어루만진다…", "🧚 요정들의 노랫소리가 온몸을 감싼다…"],
        "event_hurt": ["🌑 어둠의 기운이 스며들어 몸을 갉아먹는다…", "🥀 시든 꽃잎이 날카롭게 흩날린다…"],
        "event_mix": ["🌫 빛과 어둠이 초원에서 뒤섞인다…"],
        "low_hp": 10,
        "low": "“…싫어… 이 어둠이… 사라지면… 나는…!”",
        "low_title": "💬 타락한 정령",
    },
    # ------------------------------------------------------------------
    "mirror": {
        "name": "거울 세계", "icon": "🪞", "subtitle": "밝혀진 것이 없는 위험한 곳",
        "colors": ("#2B2B45", "#B9C6DD"), "ink": "#FFFFFF",
        "roles": {"hero": "상급 모험가 (나)", "foe": "그림자 (또 다른 나)"},
        "short": {"hero": "나(본체)", "foe": "그림자"},
        "icons": {"hero": "🧙", "foe": "👤"},
        "names": {"hero": "상급 모험가", "foe": "그림자"},
        "desc": "정체불명의 폐허를 조사하다 거울에 빨려 들어간 상급 모험가 vs 그림자의 ‘나’.\n"
                "그림자는 나와 같은 체력, 같은 덱으로 싸워요. 매 턴 거울이 균형을 맞춰요.",
        "rule_short": "매 턴 시작: 체력이 낮은 쪽 +1 회복 · 높은 쪽 -1 피해\n그림자: 나와 같은 체력 · 같은 덱",
        "effect": "balance", "period": 1,
        "foe_hp_bonus": 0,
        "foe_deck": None,          # 모험가의 덱을 그대로 복사
        "intro": [
            ("n", "어느 상급 모험가가 ‘아직 밝혀진 것이 없는, 위험하다는 곳’의 조사를 맡았다."),
            ("hero", "정체불명이라더니… 벽마다 거울이 가득하군. 어디를 봐도 내 얼굴이 나를 쳐다보고 있어."),
            ("n", "그때, 거울 하나가 물결처럼 일렁였다. 손이 닿기도 전에 발밑이 사라졌다."),
            ("hero", "으윽—! 거울이… 나를 끌어당기고 있어!"),
            ("n", "정신을 차렸을 때, 모든 것이 반대였다. 왼쪽이 오른쪽이고, 소리마저 거꾸로 울렸다. 그리고 눈앞에는—"),
            ("foe", "어서 와. 기다리고 있었어, ‘진짜 나’.", "그림자"),
            ("hero", "…내 얼굴, 내 장비, 내 카드까지? 넌 누구지?"),
            ("foe", "누구냐고? 나는 너야. 네 체력, 네 덱, 네 버릇까지 전부. 이기고 싶다면 너 자신을 넘어서야 해.", "그림자"),
            ("n", "🪞 필드 규칙 — 매 턴 시작마다 체력이 낮은 쪽은 1 회복, 높은 쪽은 1 피해. 그림자는 나와 같은 체력, 같은 덱으로 싸워요."),
        ],
        "outro": {
            "hero": [("foe", "…졌네. 결국 한 걸음 더 나아간 건 너였구나.", "그림자"),
                     ("n", "거울에 금이 갔다. 균열 사이로 현실의 빛이 쏟아져 들어온다."),
                     ("hero", "이 세계는 도대체 무엇이었을까. …조사는 이제부터야.")],
            "foe": [("foe", "이제 거울 밖으로 나갈 건 나야. 안녕, ‘나’.", "그림자"),
                    ("n", "거울 속에는 ‘모험가’가 남았고, 거울 밖으로는 ‘그림자’가 걸어 나갔다.")],
            "draw": [("n", "두 사람이 같은 순간에 쓰러졌다. 거울 속에서도 밖에서도, 누가 진짜인지 아무도 알 수 없었다.")],
        },
        "event_balance": "🪞 거울의 균형 — 체력이 낮은 {lo} +1 · 높은 {hi} -1",
        "event_calm": "🪞 거울이 고요해요 — 체력이 같아서 아무 일도 없어요",
        "low_hp": 10,
        "low": "“…흔들리는 건 너도 마찬가지잖아. 우린 똑같으니까.”",
        "low_title": "💬 그림자",
    },
}
# ======================================================================
# [CLAUDE-STORY] 끝
# ======================================================================


class Player:
    def __init__(self, deck, hp_bonus=0):
        self.hp, self.deck_list, self.deck = CFG["start_hp"] + hp_bonus, list(deck), random.sample(deck, len(deck))
        self.mx = CFG["max_hp"] + hp_bonus   # 이 플레이어의 최대 체력 (특수 필드의 체력 보너스 포함)
        self.hand = []
        self.field = []   # {"id", "left", "fresh"}
        self.poison = 0   # 남은 중독 턴
        self.shield = 0   # 남은 보호막
        self.skip = 0     # 건너뛸 턴 수
        self.shield_fresh = False   # 이번 턴에 얻은 보호막인지 (다음 내 턴이 끝나면 사라짐)

    def mod(self, key):
        return sum(CARDS[f["id"]].get("mods", {}).get(key, 0) for f in self.field)


def pull(hand, n):
    """손패에서 무작위로 최대 n장을 뽑아 내고, 뽑힌 카드 목록을 돌려줘요"""
    return [hand.pop(random.randrange(len(hand))) for _ in range(min(n, len(hand)))]


class Game:
    def __init__(self, deck0, deck1, field="normal", roles=("hero", "foe")):
        self.field_id = field if field in FIELDS else "normal"
        self.roles = list(roles)               # 각 플레이어의 역할: "hero"(모험가) / "foe"(상대 역할)
        F = FIELDS[self.field_id]
        bonus = [F.get("foe_hp_bonus", 0) if r == "foe" else 0 for r in self.roles]
        self.p, self.turn, self.over = [Player(deck0, bonus[0]), Player(deck1, bonus[1])], random.randint(0, 1), False
        self.tn = 0                            # 지금까지 시작된 턴 수 (필드 효과 주기 계산용)
        self.fes, self.fe_n, self.low_said = [], 0, False   # 필드 이벤트 알림 목록 (화면에 띄우는 용)
        self.winner = None  # 0, 1, -1(무승부)
        self.log, self.seq = [], 0
        self.installed = False             # 이번 턴에 설치 카드를 썼는지 (턴당 1장)
        self.last = None                   # 마지막으로 사용된 카드 (플레이어, 카드 id)
        self.last_instant = [None, None]   # 각 플레이어가 마지막으로 쓴 즉발 카드 (거울의 방용)
        self.pick = None                   # 버릴 카드를 고르는 중이면 {"pi", "n"}
        self.pending = None                # 진행 중인 아레나 공격 (결과가 올 때까지 턴이 넘어가지 않아요)
        for pi in (0, 1):
            for _ in range(CFG["start_hand"]):
                self.take_card(pi)
        self.say(self.turn, "선공으로 시작해요")
        self.start_turn(first=True)

    # --- 기록 / 뽑기 ---
    def say(self, who, text):
        self.log.append((who, text))
        del self.log[:-30]

    def take_card(self, pi):
        p = self.p[pi]
        if not p.deck:
            return
        cid = p.deck.pop()
        if len(p.hand) >= CFG["hand_limit"]:
            self.say(pi, f"손패가 가득 차 {CARDS[cid]['name']} 소멸")
        else:
            p.hand.append(cid)

    def draw(self, pi, n):
        p = self.p[pi]
        for _ in range(n):
            if not p.deck:  # 덱을 다 뽑았다 → 리필 후 refill_draw 장
                p.deck = random.sample(p.deck_list, len(p.deck_list))
                self.say(pi, f"덱을 {len(p.deck_list)}장으로 다시 채웠어요")
                for _ in range(CFG["refill_draw"]):
                    self.take_card(pi)
            else:
                self.take_card(pi)

    # --- 전투 ---
    def check_over(self):
        for i in (0, 1):
            P = self.p[i]
            if P.hp <= 0:  # 불굴의 맹세 같은 '버티기' 설치
                for f in P.field:
                    if CARDS[f["id"]].get("mods", {}).get("surviveOnce"):
                        P.field.remove(f)
                        P.hp = 1
                        self.say(i, f"{CARDS[f['id']]['name']} 발동! 체력 1로 버텨요")
                        break
        dead = [i for i in (0, 1) if self.p[i].hp <= 0]
        if dead:
            self.over, self.winner = True, -1 if len(dead) == 2 else 1 - dead[0]

    def fire(self, pi, trig, no_hit=False):
        """pi 의 설치 카드 중 trig 시점에 발동하는 것을 실행 (need: 설치 장수 조건)."""
        P = self.p[pi]
        for f in list(P.field):
            d = CARDS[f["id"]]
            if d["kind"] == "install" and d.get("on") == trig and len(P.field) >= d.get("need", 0):
                self.run_fx(pi, d["fx"], no_hit=no_hit)
                if self.over:
                    return

    def deal_damage(self, tgt, amt, no_hit=False):
        if amt <= 0:
            return
        P = self.p[tgt]
        vul = -min(0, P.mod("takeReduce"))          # 취약: 한 번에 받는 피해 증가
        real = amt + vul
        notes = [f"취약 +{vul}"] if vul else []
        for f in list(P.field):                      # 1) 설치 방벽이 먼저 막아 줘요
            if real <= 0:
                break
            if f.get("hp"):
                ab = min(f["hp"], real)
                f["hp"] -= ab
                real -= ab
                name = CARDS[f["id"]]["name"]
                notes.append(f"{name} -{ab}")
                if f["hp"] <= 0:
                    P.field.remove(f)
                    self.say(tgt, f"{name} 파괴!")
        if P.shield > 0 and real > 0:                # 2) 보호막
            ab = min(P.shield, real)
            P.shield -= ab
            real -= ab
            notes.append(f"보호막 -{ab}")
        P.hp -= real
        extra = f" ({', '.join(notes)})" if notes else ""
        self.say(tgt, f"{real} 피해{extra} · 체력 {max(P.hp, 0)}" if real else f"피해를 모두 막았어요{extra}")
        self.check_over()
        if real > 0 and not no_hit and not self.over:
            self.fire(tgt, "hit", no_hit=True)

    def heal(self, o, n):
        P = self.p[o]
        P.hp = min(P.mx, P.hp + n)
        self.say(o, f"체력 +{n} · 체력 {P.hp}")

    def run_fx(self, o, fx, bonus=False, no_hit=False, cid=None):
        P, Q = self.p[o], self.p[1 - o]
        copies = P.hand.count(cid) if cid else 0   # 손패에 남은 '다른' 같은 카드 수 (사용한 카드 제외)
        extra = P.mod("dealBonus") if bonus else 0
        for e in fx:
            if self.over:
                break
            op = e["op"]
            v = e.get("v", 0)
            if op == "dmg":
                self.deal_damage(1 - o, v + extra, no_hit)
            elif op == "dmgPerCopy":
                self.deal_damage(1 - o, e.get("b", 0) + v * copies + extra, no_hit)
            elif op == "dmgIf":
                who = o if e["who"] == "me" else 1 - o
                hp = self.p[who].hp
                cond = hp <= e["t"] if e["cmp"] == "le" else hp >= e["t"]
                self.deal_damage(1 - o, v + (e["b"] if cond else 0) + extra, no_hit)
            elif op == "dmgRand":
                n = random.randint(v, e["b"])
                if n + extra <= 0:
                    self.say(o, "주사위가 빗나갔어요")
                else:
                    self.deal_damage(1 - o, n + extra, no_hit)
            elif op == "dmgPerInstall":
                self.deal_damage(1 - o, v * len(P.field) + extra, no_hit)
            elif op == "healRand":
                self.heal(o, random.randint(v, e["b"]))
            elif op == "healPerInstall":
                self.heal(o, v * len(P.field))
            elif op == "chance":
                win = random.random() * 100 < e["p"]
                self.say(o, "행운! 🍀" if win else "불운… 💧")
                self.run_fx(o, e["win"] if win else e.get("lose", []), bonus, no_hit, cid)
            elif op == "discardCopies":
                n = P.hand.count(cid) if cid else 0
                P.hand[:] = [x for x in P.hand if x != cid]
                if n:
                    self.say(o, f"{CARDS[cid]['name']} {n}장 소멸")
            elif op == "breakAll":
                n = len(Q.field)
                Q.field.clear()
                self.say(1 - o, f"설치 카드 {n}장이 모두 파괴됐어요")
            elif op == "healMissing":
                self.heal(o, max(v, (P.mx - P.hp + 1) // 2))
            elif op == "mirror":
                m = self.last_instant[1 - o]
                if m and not any(x["op"] == "mirror" for x in CARDS[m]["fx"]):
                    self.say(o, f"거울! 상대의 {CARDS[m]['name']} 효과를 복사")
                    self.run_fx(o, CARDS[m]["fx"], bonus=True, no_hit=no_hit)
                else:
                    self.say(o, "거울에 비출 카드가 없어요")
            elif op == "selfdmg":
                P.hp -= v
                self.say(o, f"스스로 {v} 피해 · 체력 {max(P.hp, 0)}")
                self.check_over()
            elif op == "heal":
                self.heal(o, v)
            elif op == "healPerCopy":
                self.heal(o, e.get("b", 0) + v * copies)
            elif op == "draw":
                self.draw(o, v)
                self.say(o, f"카드 {v}장 뽑기")
            elif op == "discard":
                self.say(1 - o, f"손패 {len(pull(Q.hand, v))}장 버려짐")
            elif op == "discardSelf":
                self.say(o, f"손패 {len(pull(P.hand, v))}장 버림")
            elif op == "discardChoose":          # 버릴 카드를 직접 고르게 해요 (고를 때까지 턴이 안 넘어가요)
                if P.hand:
                    self.pick = {"pi": o, "n": min(v, len(P.hand))}
            elif op == "steal":
                got = pull(Q.hand, v)
                P.hand += got[:max(0, CFG["hand_limit"] - len(P.hand))]
                self.say(o, f"상대 손패 {len(got)}장 훔침")
            elif op == "breakInstall":
                for _ in range(v):
                    if Q.field:
                        f = Q.field.pop(random.randrange(len(Q.field)))
                        self.say(1 - o, f"{CARDS[f['id']]['name']} 파괴됨")
            elif op == "poison":
                Q.poison = max(Q.poison, v)
                self.say(1 - o, f"중독! ({Q.poison}턴)")
            elif op == "shield":
                P.shield += v
                P.shield_fresh = True
                self.say(o, f"보호막 {P.shield}")
            elif op == "foe":
                self.run_fx(1 - o, e["fx"], no_hit=no_hit)
            elif op == "swapHp":
                P.hp, Q.hp = Q.hp, P.hp
                self.say(o, f"체력 교환! 나 {P.hp} · 상대 {Q.hp}")
                self.check_over()
            elif op == "handSwap":
                P.hand, Q.hand = Q.hand, P.hand
                self.say(o, "손패를 통째로 맞바꿨어요")
            elif op == "timeStop":
                Q.skip += v
                self.say(o, "시간 정지! 상대의 다음 턴을 건너뛰어요")

    # --- 턴 진행 ---
    def start_turn(self, first=False):
        pi = self.turn
        P = self.p[pi]
        self.installed = False
        self.tn += 1
        if P.poison > 0:
            P.poison -= 1
            self.say(pi, "중독 피해")
            self.deal_damage(pi, 1, no_hit=True)
            if self.over:
                return
        self.field_turn()                       # 특수 필드 효과 (숲속 / 고요한 초원 / 거울 세계)
        if self.over:
            return
        self.fire(pi, "turnStart")
        if self.over:
            return
        if not (first and CFG["first_player_skips_draw"]):
            self.draw(pi, CFG["draw_per_turn"])

    # --- [CLAUDE-FIELD] 특수 필드 효과 (숲속 / 고요한 초원 / 거울 세계) ---
    def emit(self, icon, title, line, pop=True):
        """화면에 띄울 필드 이벤트 알림 (pop=False 면 로그에만 남고 팝업은 없어요)"""
        self.fe_n += 1
        self.fes.append({"n": self.fe_n, "icon": icon, "title": title, "line": line, "pop": 1 if pop else 0})
        del self.fes[:-4]

    def role_name(self, pi):
        return FIELDS[self.field_id]["short"][self.roles[pi]]

    def field_turn(self):
        F = FIELDS[self.field_id]
        eff = F.get("effect")
        if not eff or self.tn <= 1 or self.tn % F.get("period", 1):
            self.low_check()
            return
        {"swarm": self.fx_swarm, "breath": self.fx_breath, "balance": self.fx_balance}[eff](F)
        if not self.over:
            self.low_check()

    def low_check(self):
        """상대 역할의 체력이 바닥나면 한 번 대사를 쳐요"""
        F = FIELDS[self.field_id]
        if self.low_said or self.over or not F.get("low"):
            return
        for i in (0, 1):
            if self.roles[i] == "foe" and self.p[i].hp <= F.get("low_hp", 10):
                self.low_said = True
                self.say(None, F["low"])
                self.emit(F["icon"], F["low_title"], F["low"])

    # [CLAUDE-FIELD] 숲의 분노: 아레나에서 나와 상대가 동시에 벌레 떼를 피해요
    def fx_swarm(self, F):
        """숲의 분노: 진짜 문지기가 벌레 떼를 풀어요. 아레나가 열리고 나와 상대가 '동시에' 같은 필드에서 피해요."""
        cid = random.choices(F["swarm"], weights=F.get("swarm_w"))[0]
        d = CARDS[cid]
        spec = dict(d["arena"])
        spec.update(mode="swarm2", ants=max(4, round(spec["ants_base"] * F.get("swarm_scale", 1.0))),
                    max=spec.get("max_base", 3), time=10.0)
        cl = lambda v, hi: min(max(v, 0.0), hi)
        mods = lambda P: {"atk": 0.0, "foe_slow": 0.0, "dodge": cl(P.mod("dodge"), 1.0),
                          "shrink": cl(P.mod("shrink"), 0.6), "proj_slow": cl(P.mod("projSlow"), 0.5)}
        self.say(None, f"{F['icon']} 진짜 문지기가 {spec.get('g', '🐝')}{d['name']}{eul(d['name'])} 풀어놨어요! (나와 상대가 함께 피해요)")
        self.pending = {"pi": 0, "event": True, "cid": cid, "eff": cid, "spec": spec,
                        "seed": random.getrandbits(31), "mods": mods(self.p[0]), "mods2": mods(self.p[1])}
        self.seq += 1

    def resolve_event(self, pd, result):
        """숲의 분노 아레나 결과 적용: 첫 번째 플레이어(dmg) / 두 번째 플레이어(dmg2)가 각자 피해를 입어요"""
        F = FIELDS[self.field_id]
        d, spec = CARDS[pd["cid"]], pd["spec"]
        cap, glyph = spec.get("max", 99), spec.get("g", "🐝")
        res = []
        for t, (kd, kh) in enumerate((("dmg", "hits"), ("dmg2", "hits2"))):
            dmg, hits = min(int(result.get(kd, 0)), cap), int(result.get(kh, 0))
            if dmg > 0:
                self.deal_damage(t, dmg, no_hit=True)
            else:
                self.say(t, "벌레 떼를 모두 피했어요!")
            if hits > 0:
                for e in d.get("fx_hit", []):
                    if e["op"] == "poison":                      # 맹독 벌 떼: 닿으면 중독
                        self.p[t].poison = max(self.p[t].poison, e["v"])
                        self.say(t, f"중독! ({self.p[t].poison}턴)")
            res.append(dmg)
        detail = " · ".join(f"{self.role_name(t)} -{n}" if n else f"{self.role_name(t)} 회피!" for t, n in enumerate(res))
        line = F["event_intro"].format(card=d["name"] + eul(d["name"])) + "\n" + random.choice(F["event_lines"]) + "\n" + detail
        self.emit(glyph, f"{F['icon']} 숲의 분노 — {d['name']}!", line)
        self.seq += 1
        return True, ""

    def fx_breath(self, F):
        deltas = []
        for t in (0, 1):
            P = self.p[t]
            old = P.hp
            if random.random() < 0.5:
                P.hp = min(P.mx, P.hp + 1)
            else:
                P.hp -= 1
            deltas.append(P.hp - old)
        txt = " · ".join(f"{self.role_name(t)} {deltas[t]:+d}" if deltas[t] else f"{self.role_name(t)} 변화 없음(체력 가득)" for t in (0, 1))
        self.say(None, f"{F['icon']} 초원의 숨결 — {txt}")
        up, down = any(x > 0 for x in deltas), any(x < 0 for x in deltas)
        quote = random.choice(F["event_mix"] if (up and down) else F["event_heal"] if up else F["event_hurt"])
        self.emit(F["icon"], f"{F['icon']} 초원의 숨결", quote + "\n" + txt)
        self.check_over()

    def fx_balance(self, F):
        a, b = self.p[0].hp, self.p[1].hp
        if a == b:
            self.say(None, F["event_calm"])
            self.emit(F["icon"], "거울의 균형", F["event_calm"], pop=False)
            return
        lo, hi = (0, 1) if a < b else (1, 0)
        self.p[lo].hp = min(self.p[lo].mx, self.p[lo].hp + 1)
        self.p[hi].hp -= 1
        txt = F["event_balance"].format(lo=self.role_name(lo), hi=self.role_name(hi))
        self.say(None, txt)
        self.emit(F["icon"], "거울의 균형", txt, pop=False)
        self.check_over()

    def pass_turn(self):
        cur = self.turn
        P = self.p[cur]
        self.fire(cur, "turnEnd")
        if self.over:
            return
        keep, expired = [], []
        for f in P.field:
            if f["fresh"]:
                f["fresh"] = False
                keep.append(f)
            elif f["left"] is None:
                keep.append(f)
            else:
                f["left"] -= 1
                if f["left"] > 0:
                    keep.append(f)
                elif CARDS[f["id"]].get("on") == "expire":
                    expired.append(f)
                else:
                    self.say(cur, f"{CARDS[f['id']]['name']} 효과 종료")
        P.field = keep
        for f in expired:   # 시한 설치: 정해진 턴이 지나면 발동하고 사라짐
            d = CARDS[f["id"]]
            self.say(cur, f"{d['name']} 발동!")
            self.run_fx(cur, d["fx"])
            if self.over:
                return
        if P.shield > 0:           # 보호막은 내 다음 턴이 끝나면 사라져요
            if P.shield_fresh:
                P.shield_fresh = False
            else:
                P.shield = 0
                self.say(cur, "보호막이 사라졌어요")
        nxt = 1 - cur
        if self.p[nxt].skip > 0:   # 시간 정지: 상대 턴을 건너뛰고 내가 다시 진행
            self.p[nxt].skip -= 1
            self.say(nxt, "멈춰 있어서 턴을 건너뛰어요")
            self.turn = cur
        else:
            self.turn = nxt
        self.start_turn()

    # --- 플레이어 행동: (성공 여부, 메시지) ---
    def play_card(self, pi, cid):
        if self.pending:
            return False, "공격이 진행 중이에요."
        if self.pick:
            return False, "버릴 카드를 먼저 골라 주세요."
        if self.over or self.turn != pi:
            return False, "내 차례가 아니에요."
        p = self.p[pi]
        if cid not in p.hand:
            return False, "손패에 없는 카드예요."
        d = CARDS[cid]
        if d["kind"] == "install":
            if self.installed:
                return False, "설치 카드는 한 턴에 1장만 쓸 수 있어요."
            if len(p.field) >= CFG["field_max"]:
                return False, f"설치 칸이 가득 찼어요 (최대 {CFG['field_max']})."
            p.hand.remove(cid)
            self.last = (pi, cid)
            p.field.append({"id": cid, "left": d.get("duration") or None, "fresh": True, "hp": d.get("barrier")})
            self.installed = True
            self.say(pi, f"{d['name']} 설치")
            if d.get("on") == "play" and len(p.field) >= d.get("need", 0):
                self.run_fx(pi, d["fx"])
        else:
            p.hand.remove(cid)
            self.last = (pi, cid)
            self.say(pi, f"{d['name']} 사용")
            eff = cid
            if any(x["op"] == "mirror" for x in d["fx"]):       # 거울의 방: 상대의 마지막 '공격'을 복사
                m = self.last_instant[1 - pi]
                if m and "arena" in CARDS[m] and not any(x["op"] == "mirror" for x in CARDS[m]["fx"]):
                    eff = m
                    self.say(pi, f"거울! 상대의 {CARDS[m]['name']} 공격을 복사")
            if "arena" in CARDS[eff]:
                spec = self.make_spec(pi, eff)
                if spec is None:
                    self.say(pi, "설치 카드가 없어 불발!")
                    self.run_fx(pi, CARDS[eff].get("fx", []), bonus=True, cid=eff)
                else:
                    self.pending = {"pi": pi, "cid": cid, "eff": eff, "spec": spec,
                                    "seed": random.getrandbits(31), "mods": self.arena_mods(pi)}
                    self.seq += 1
                    return True, ""
            else:
                self.run_fx(pi, d["fx"], bonus=True, cid=cid)
            self.last_instant[pi] = cid
            if not self.over and not self.pick:
                self.pass_turn()
        self.seq += 1
        return True, ""

    # [CLAUDE-CARD] 생명의 서약: 버릴 카드 직접 고르기
    def discard_choice(self, pi, cid):
        """생명의 서약 등: 내가 고른 카드를 버리고, 다 버렸으면 턴을 넘겨요"""
        pk = self.pick
        if not pk or pk["pi"] != pi:
            return False, "지금은 버릴 카드를 고르는 중이 아니에요."
        P = self.p[pi]
        if cid not in P.hand:
            return False, "손패에 없는 카드예요."
        P.hand.remove(cid)
        self.say(pi, f"{CARDS[cid]['name']} 버림")
        pk["n"] -= 1
        if pk["n"] <= 0 or not P.hand:
            self.pick = None
            if not self.over:
                self.pass_turn()
        self.seq += 1
        return True, ""

    def auto_discard(self, pi):
        """(AI/터미널) 가장 약한 카드부터 알아서 버려요"""
        rank = {"common": 0, "rare": 1, "hero": 2, "legend": 3}
        while self.pick and self.pick["pi"] == pi and self.p[pi].hand:
            c = min(self.p[pi].hand, key=lambda x: (rank[CARDS[x]["rarity"]], random.random()))
            self.discard_choice(pi, c)

    # --- 아레나 공격 ---
    def make_spec(self, pi, eff):
        """카드의 arena 설정에 지금 상황(손패/설치/체력)을 반영한 실제 공격 설정"""
        d = CARDS[eff]
        s = dict(d["arena"])
        P = self.p[pi]
        copies = P.hand.count(eff)
        if "ants_base" in s:
            s["ants"] = s["ants_base"] + s.get("ants_per_copy", 0) * copies
            s["max"] = s.get("max_base", 3) + s.get("max_per_copy", 0) * copies
        if "n_rand" in s:
            n = random.randint(*s["n_rand"])
            s["n"] = n
            s["max"] = n * s.get("per_hit", 1)
        if "count_per_install" in s:
            n = len(P.field)
            if n == 0:
                return None
            s["count"] = n * s["count_per_install"]
            s["max"] = s.get("max_per_install", 3) * n
        b = s.get("hit_bonus_if")
        if b:
            hp = P.hp if b["who"] == "me" else self.p[1 - pi].hp
            if (hp <= b["t"]) if b["cmp"] == "le" else (hp >= b["t"]):
                s["per_hit"] += b["b"]
                s["max"] += b["b"]
        return s

    def arena_mods(self, pi):
        """설치된 필드 전용 카드들이 아레나에 주는 효과"""
        A, D = self.p[pi], self.p[1 - pi]
        cl = lambda v, hi: min(max(v, 0.0), hi)
        return {"atk": cl(A.mod("atk"), 0.8), "dodge": cl(D.mod("dodge"), 1.0), "shrink": cl(D.mod("shrink"), 0.6),
                "foe_slow": cl(A.mod("foeSlow"), 0.5), "proj_slow": cl(D.mod("projSlow"), 0.5)}

    def resolve_attack(self, result):
        """아레나 결과 {dmg, hits, safe}를 받아 피해/효과를 적용하고 턴을 넘겨요"""
        pd, self.pending = self.pending, None
        if not pd:
            return False, "진행 중인 공격이 없어요."
        if pd.get("event"):                                     # 필드 이벤트(숲의 분노)는 턴을 넘기지 않아요
            return self.resolve_event(pd, result)
        pi, spec, eff = pd["pi"], pd["spec"], CARDS[pd["eff"]]
        P = self.p[pi]
        if spec["mode"] == "pick":
            safe = bool(result.get("safe"))
            self.say(1 - pi, "안전 상자!" if safe else "위험 상자!")
            self.run_fx(pi, spec["safe"] if safe else spec["danger"], bonus=True)
        else:
            dmg = min(int(result.get("dmg", 0)), spec.get("max", 99))
            hits = int(result.get("hits", 0))
            if dmg > 0:
                dmg += P.mod("dealBonus")
                self.deal_damage(1 - pi, dmg)
            elif not (result.get("self") or result.get("sheal") or result.get("fheal")):
                self.say(1 - pi, "공격을 모두 피했어요!")
            if result.get("fheal") and not self.over:           # 상대가 초록 구슬을 먹어 회복
                self.say(1 - pi, "구슬을 먹었어요!")
                self.heal(1 - pi, int(result["fheal"]))
            if result.get("self") and not self.over:            # 반격/반동으로 내가 입는 피해
                self.say(pi, "반격을 맞았어요!")
                self.deal_damage(pi, int(result["self"]))
            if result.get("sheal") and not self.over:           # 의식 성공: 내 회복
                self.heal(pi, int(result["sheal"]))
            if hits > 0 and not self.over:
                self.run_fx(pi, eff.get("fx_hit", []))
        if not self.over:
            self.run_fx(pi, eff.get("fx", []), bonus=True, cid=pd["eff"])
        self.last_instant[pi] = pd["cid"]
        if not self.over:
            self.pass_turn()
        self.seq += 1
        return True, ""

    def auto_attack(self, att_skill=0.55, def_skill=0.55):
        """사람이 조종하지 않고 AI끼리 아레나를 돌려 결과를 적용 (터미널/아레나를 못 쓰는 상대)"""
        import arena
        pd = self.pending
        r = arena.auto_resolve(pd["spec"], pd["seed"], pd["mods"], att_skill, def_skill, pd.get("mods2"))
        return self.resolve_attack(r)

    def end_turn(self, pi):
        if self.pending:
            return False, "공격이 진행 중이에요."
        if self.pick:
            return False, "버릴 카드를 먼저 골라 주세요."
        if self.over or self.turn != pi:
            return False, "내 차례가 아니에요."
        if any(CARDS[c]["kind"] == "instant" for c in self.p[pi].hand):
            return False, "손패에 즉발 카드가 있으면 턴을 넘길 수 없어요."
        self.last = None
        self.pass_turn()
        self.seq += 1
        return True, ""

    def act(self, pi, a):
        if a.get("a") == "play":
            return self.play_card(pi, a.get("id"))
        if a.get("a") == "end":
            return self.end_turn(pi)
        if a.get("a") == "discard":
            return self.discard_choice(pi, a.get("id"))
        return False, "알 수 없는 행동이에요."

    def pd_view(self, pi):
        p = self.pending
        if p.get("event"):          # 둘 다 피하는 쪽: a=-1, ix=내가 조종하는 점(0/1), mods=내 효과, mods2=상대 효과
            mine, other = (p["mods"], p["mods2"]) if pi == 0 else (p["mods2"], p["mods"])
            return {"a": -1, "ev": 1, "ix": pi, "cid": p["cid"], "eff": p["eff"], "spec": p["spec"], "seed": p["seed"],
                    "mods": mine, "mods2": other}
        return {"a": 0 if p["pi"] == pi else 1, "cid": p["cid"], "eff": p["eff"], "spec": p["spec"],
                "seed": p["seed"], "mods": p["mods"]}

    # --- pi 시점의 화면 데이터 (상대 손패/덱 내용은 숨김, JSON 직렬화 가능) ---
    def view_for(self, pi):
        me, op = self.p[pi], self.p[1 - pi]
        fld = lambda p: [[f["id"], f["left"], f.get("hp")] for f in p.field]
        if not self.over:
            w = None
        else:
            w = -1 if self.winner == -1 else (1 if self.winner == pi else 0)
        return {
            "q": self.seq, "t": 1 if self.turn == pi else 0, "o": 1 if self.over else 0, "w": w,
            "fd": {"id": self.field_id, "r": self.roles[pi]},
            "fe": list(self.fes),
            "me": {"hp": me.hp, "mx": me.mx, "hand": list(me.hand), "dn": len(me.deck), "f": fld(me),
                   "in": 1 if (self.turn == pi and self.installed) else 0,
                   "ps": me.poison, "sh": me.shield},
            "op": {"hp": op.hp, "mx": op.mx, "hn": len(op.hand), "dn": len(op.deck), "f": fld(op),
                   "ps": op.poison, "sh": op.shield},
            "pd": None if not self.pending else self.pd_view(pi),
            "pk": 0 if not self.pick else (1 if self.pick["pi"] == pi else 2),   # 1: 내가 버릴 카드를 고르는 중 / 2: 상대가 고르는 중
            "lp": None if not self.last else [0 if self.last[0] == pi else 1, self.last[1]],
            "log": [[-1 if x is None else (0 if x == pi else 1), t] for x, t in self.log[-6:]],
        }


def eul(word):
    """받침 유무에 따라 을/를"""
    ch = word[-1]
    return "을" if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else "를"


# [CLAUDE-STORY] 특수 필드 게임 만들기
def make_story_game(field, my_deck, opp_deck, my_role="hero"):
    """특수 필드 게임을 만들어요. 항상 내가 0번 플레이어.
    my_role: 내 역할 ("hero" 모험가 / "foe" 상대 역할). 상대 역할(foe)은 필드에 정해진 고정 덱을 써요.
    (거울 세계는 그림자가 모험가의 덱을 그대로 복사해요)"""
    if field not in FIELDS or field == "normal":
        return Game(my_deck, opp_deck)
    F = FIELDS[field]
    hero_deck = list(my_deck if my_role == "hero" else opp_deck)
    foe_deck = list(F["foe_deck"]) if F.get("foe_deck") else list(hero_deck)
    other = "foe" if my_role == "hero" else "hero"
    mine, theirs = (hero_deck, foe_deck) if my_role == "hero" else (foe_deck, hero_deck)
    return Game(mine, theirs, field=field, roles=(my_role, other))


# ----------------------------------------------------------------------
# AI
# ----------------------------------------------------------------------
def fx_value(fx, me, op, copies, bonus, mirror_fx=None):
    sc = 0.0
    room = me.mx - me.hp
    reduce_ = op.mod("takeReduce")
    for e in fx:
        k, v = e["op"], e.get("v", 0)
        dmg = kill = None
        if k == "dmg":
            dmg = kill = v
        elif k == "dmgPerCopy":
            dmg = kill = e.get("b", 0) + v * copies
        elif k == "dmgPerInstall":
            dmg = kill = v * len(me.field)
        elif k == "dmgRand":
            dmg, kill = (v + e["b"]) / 2, v
        elif k == "dmgIf":
            hp = me.hp if e["who"] == "me" else op.hp
            dmg = kill = v + (e["b"] if (hp <= e["t"] if e["cmp"] == "le" else hp >= e["t"]) else 0)
        if dmg is not None:
            sc += (dmg + bonus) * 3
            if kill + bonus >= op.hp + reduce_:
                sc += 100
        elif k in ("heal", "healPerCopy", "healPerInstall", "healRand"):
            amt = {"heal": v, "healPerCopy": e.get("b", 0) + v * copies, "healPerInstall": v * len(me.field),
                   "healRand": (v + e.get("b", v)) / 2}[k]
            sc += min(amt, room) * (4 if me.hp <= 6 else 0.8)   # 체력이 위험할 때만 회복을 선호
        elif k == "healMissing":
            sc += min(max(v, (me.mx - me.hp + 1) // 2), room) * (4 if me.hp <= 6 else 0.8)
        elif k == "chance":
            p = e["p"] / 100
            sc += (p * fx_value(e["win"], me, op, copies, bonus, mirror_fx)
                   + (1 - p) * fx_value(e.get("lose", []), me, op, copies, bonus, mirror_fx))
        elif k == "mirror":
            sc += 0.9 * fx_value(mirror_fx, me, op, 0, bonus) if mirror_fx else 0
        elif k == "foe":                     # 상대에게 일어나는 효과: 내게는 반대로 평가
            sc -= fx_value(e["fx"], op, me, 0, 0)
        elif k == "breakAll":
            sc += 4 * len(op.field)
        elif k == "discardCopies":
            sc -= copies * 0.5
        elif k == "draw":
            sc += v * 1.5
        elif k == "discard":
            sc += min(len(op.hand), v) * 2
        elif k in ("discardSelf", "discardChoose"):
            sc -= min(len(me.hand) - 1, v) * 2
        elif k == "steal":
            sc += min(len(op.hand), v) * 3
        elif k == "breakInstall":
            sc += 4 * v if op.field else 0
        elif k == "poison":
            sc += 2.5 * v if op.poison < v else 0
        elif k == "shield":
            sc += v * 1.5
        elif k == "selfdmg":
            sc -= v * 3 + (1000 if me.hp <= v else 0)
        elif k == "swapHp":
            sc += (op.hp - me.hp) * 3 - 3
        elif k == "handSwap":
            sc += (len(op.hand) - len(me.hand)) * 2 - 2
        elif k == "timeStop":
            sc += 7
    return sc


def card_value(d, me, op, copies, mcard=None):
    """AI가 카드를 고를 때 쓰는 점수 (공격 카드는 시뮬레이션으로 구한 기대 피해 ev 사용)"""
    bonus = me.mod("dealBonus")
    sp = d.get("arena")
    if any(x["op"] == "mirror" for x in d.get("fx", [])):
        return 0.9 * card_value(mcard, me, op, copies) if mcard and "arena" in mcard else \
            fx_value(d["fx"], me, op, copies, bonus, mcard["fx"] if mcard else None)
    if sp:
        if sp["mode"] == "pick":
            p = sp["k"] / sp["n"]
            sc = p * fx_value(sp["danger"], me, op, 0, bonus) + (1 - p) * fx_value(sp["safe"], me, op, 0, 0)
        else:
            ev = sp.get("ev", 1.0)
            if "ants_base" in sp:
                ev += sp.get("ev_per", 0) * copies
            elif "count_per_install" in sp:
                ev = sp.get("ev_per", 1.0) * len(me.field)
            b = sp.get("hit_bonus_if")
            if b:
                hp = me.hp if b["who"] == "me" else op.hp
                if (hp <= b["t"]) if b["cmp"] == "le" else (hp >= b["t"]):
                    ev += sp.get("ev_bonus", 0)
            sc = (ev + (bonus if ev > 0 else 0)) * 3
            if ev >= op.hp:
                sc += 20
            sc += 0.6 * fx_value(d.get("fx_hit", []), me, op, copies, 0)
        return sc + fx_value(d.get("fx", []), me, op, copies, bonus)
    return fx_value(d["fx"], me, op, copies, bonus)


def ai_score(d, me, op, mcard=None):
    return card_value(d, me, op, me.hand.count(d["id"]) - 1, mcard) + random.random()


def ai_choose(g, pi):
    me, op = g.p[pi], g.p[1 - pi]
    installs = [c for c in me.hand if CARDS[c]["kind"] == "install"]
    if installs and not g.installed and len(me.field) < CFG["field_max"]:
        return {"a": "play", "id": installs[0]}
    instants = [c for c in me.hand if CARDS[c]["kind"] == "instant"]
    if instants:
        m = g.last_instant[1 - pi]
        mcard = CARDS[m] if m and not any(x["op"] == "mirror" for x in CARDS[m]["fx"]) else None
        best = max(instants, key=lambda c: ai_score(CARDS[c], me, op, mcard))
        return {"a": "play", "id": best}
    return {"a": "end"}


def simple_choose(view):
    """뷰 데이터만으로 고르는 간단한 자동 플레이 (테스트용 --auto)"""
    hand = view["me"]["hand"]
    if not view["me"].get("in") and len(view["me"]["f"]) < CFG["field_max"]:
        for c in hand:
            if CARDS[c]["kind"] == "install":
                return {"a": "play", "id": c}
    for c in hand:
        if CARDS[c]["kind"] == "instant":
            return {"a": "play", "id": c}
    return {"a": "end"}


# ----------------------------------------------------------------------
# 터미널 화면
# ----------------------------------------------------------------------
AUTO = False


def bar(hp):
    n = max(0, min(hp, CFG["max_hp"]))
    color = "31" if hp <= 5 else "32"
    return paint("█" * n, color) + "░" * (CFG["max_hp"] - n)


def field_text(f):
    if not f:
        return "없음"
    out = []
    for item in f:
        cid, left = item[0], item[1]
        hp = item[2] if len(item) > 2 else None
        c = CARDS[cid]
        extra = f" 방벽{hp}" if hp else ""
        out.append(paint(f"{c['name']}" + (f"({left}턴{extra})" if left else f"(영구{extra})"), RCOLOR[c["rarity"]]))
    return "  ".join(out)


def status_text(side):
    s = ""
    if side.get("ps"):
        s += f"  ☠중독 {side['ps']}"
    if side.get("sh"):
        s += f"  🛡보호막 {side['sh']}"
    return s


def render(v):
    line = "═" * 60
    print("\n" + line)
    print(f"상대  체력 {max(v['op']['hp'], 0):>2}  {bar(v['op']['hp'])}   손패 {v['op']['hn']} · 덱 {v['op']['dn']}{status_text(v['op'])}")
    print(f"  설치: {field_text(v['op']['f'])}")
    print("─" * 60)
    for who, text in v["log"][-5:]:
        print(("  " if who < 0 else ("  나: " if who == 0 else "  상대: ")) + text)
    print("─" * 60)
    print(f"나    체력 {max(v['me']['hp'], 0):>2}  {bar(v['me']['hp'])}   덱 {v['me']['dn']}{status_text(v['me'])}")
    print(f"  설치: {field_text(v['me']['f'])}")
    print("  손패:")
    if not v["me"]["hand"]:
        print("    (비었어요)")
    for i, cid in enumerate(v["me"]["hand"], 1):
        print(f"   {i:>2}) {card_line(cid)}")
    print(line)


def settle(g, show=True):
    """터미널은 아레나를 열 수 없어서, 공격이 시작되면 AI끼리 자동으로 판정해요 (온라인 상대가 아레나 미지원일 때도 동일)"""
    if g.pick:
        g.auto_discard(g.pick["pi"])
    while g.pending:
        pd = g.pending
        n0 = len(g.log)
        g.auto_attack()
        if show:
            print(f"  ⚔ [{CARDS[pd['cid']]['name']}] 자동 판정")
            for _, t in g.log[n0:]:
                print(f"    {t}")


def show_card_detail(cid):
    """확대 보기(터미널): 카드 설명과 자세한 규칙"""
    c = CARDS[cid]
    print("\n" + paint(f"■ {c['name']}  [{RN[c['rarity']]}·{KN[c['kind']]}]", RCOLOR[c["rarity"]]))
    print(f"  효과: {describe(c)}")
    for n in card_notes(c):
        print(f"   · {n}")
    print()


def ask_action(view):
    """내 턴의 입력을 받아 행동(dict)을 돌려줍니다. 종료하려면 SystemExit."""
    if AUTO:
        return simple_choose(view)
    hand = view["me"]["hand"]
    has_instant = any(CARDS[c]["kind"] == "instant" for c in hand)
    if view["me"].get("in"):
        hint = "이번 턴 설치는 이미 했어요. 즉발 카드를 쓰거나 턴을 넘기세요."
    elif has_instant:
        hint = "설치 카드는 턴당 1장, 즉발 카드를 쓰면 턴이 끝나요."
    else:
        hint = "즉발 카드가 없어요. 설치를 마쳤다면 e 로 턴을 넘기세요."
    print(f"내 차례 — {hint}")
    while True:
        s = input("번호=카드 사용 / ?번호=자세히 / e=턴 넘기기 / q=나가기 > ").strip().lower()
        if s == "q":
            raise SystemExit
        if s == "e":
            return {"a": "end"}
        if s.startswith("?") and s[1:].isdigit() and 1 <= int(s[1:]) <= len(hand):
            show_card_detail(hand[int(s[1:]) - 1])
            continue
        if s.isdigit() and 1 <= int(s) <= len(hand):
            return {"a": "play", "id": hand[int(s) - 1]}
        print("올바른 번호나 명령을 입력해 주세요.")


def show_result(v):
    word = {1: "승리! 🎉", 0: "패배…", -1: "무승부"}[v["w"]]
    print("\n" + "★" * 60 + f"\n  게임 종료 — {word}\n" + "★" * 60)


# ----------------------------------------------------------------------
# AI 대전
# ----------------------------------------------------------------------
def play_ai(deck):
    g = Game(deck, auto_deck())
    seen = len(g.log)
    while not g.over:
        if g.turn == 0:
            v = g.view_for(0)
            render(v)
            ok, msg = g.act(0, ask_action(v))
            if not ok:
                print("⚠", msg)
            settle(g)
            seen = len(g.log)
        else:
            time.sleep(0 if AUTO else 0.8)
            g.act(1, ai_choose(g, 1))
            if g.pending:
                g.auto_attack()
            for who, t in g.log[seen:]:
                print(f"  {'상대' if who == 1 else '나'}: {t}")
            seen = len(g.log)
    render(g.view_for(0))
    show_result(g.view_for(0))


# ----------------------------------------------------------------------
# 덱 구성 / 규칙 / 메뉴
# ----------------------------------------------------------------------
def deck_menu(deck):
    while True:
        n = rarity_counts(deck)
        meters = "  ".join(f"{RN[r]} {n[r]}/{'∞' if LIMIT[r] >= 10 ** 9 else LIMIT[r]}" for r in RORDER)
        print(f"\n덱 {len(deck)}장 (최소 {CFG['deck_min']} ~ 최대 {CFG['deck_max']}, 같은 카드 최대 {CFG['max_copies']})   {meters}")
        for cid, c in CARDS.items():
            cnt = deck.count(cid)
            print(f"  {cid:<4} {card_line(cid)}   {paint(f'x{cnt}', '1') if cnt else ''}")
        print("명령: +ID [장수]  -ID [장수]  ?ID(자세히)  auto(자동)  clear(비우기)  done(완료)")
        s = input("덱 > ").strip().lower().split()
        if not s:
            continue
        cmd = s[0]
        if cmd == "done":
            err = validate_deck(deck)
            if err:
                print("⚠", err, "(그래도 저장은 돼요. 대전 전에 고쳐 주세요)")
            save_deck(deck)
            return deck
        if cmd == "auto":
            deck = auto_deck()
        elif cmd == "clear":
            deck = []
        elif cmd.startswith("?") and cmd[1:] in CARDS:
            show_card_detail(cmd[1:])
            continue
        elif cmd[0] in "+-" and cmd[1:] in CARDS:
            cid = cmd[1:]
            times = int(s[1]) if len(s) > 1 and s[1].isdigit() else 1
            for _ in range(times):
                if cmd[0] == "+":
                    if len(deck) >= CFG["deck_max"]:
                        print("⚠ 덱이 가득 찼어요.")
                        break
                    if deck.count(cid) >= CFG["max_copies"]:
                        print(f"⚠ 같은 카드는 최대 {CFG['max_copies']}장까지예요.")
                        break
                    r = CARDS[cid]["rarity"]
                    if rarity_counts(deck)[r] >= LIMIT[r]:
                        print(f"⚠ {RN[r]} 카드는 최대 {LIMIT[r]}장이에요.")
                        break
                    deck.append(cid)
                elif cid in deck:
                    deck.remove(cid)
        else:
            print("알 수 없는 명령이에요.")
        save_deck(deck)


def rules_text():
    lim = CFG["rarity_limit"]
    return (
        f"■ 덱: {CFG['deck_min']}~{CFG['deck_max']}장. 일반 제한 없음 / 레어 {lim['rare']} / 영웅 {lim['hero']} / 레전드 {lim['legend']}장까지\n"
        f"■ 같은 카드는 덱에 최대 {CFG['max_copies']}장까지\n"
        f"■ 시작 체력 {CFG['start_hp']}, 손패 {CFG['start_hand']}장, 선공 무작위, 체력 0이면 패배\n"
        f"■ 설치 카드: 턴을 쓰지 않지만 한 턴에 1장만 (설치 칸 최대 {CFG['field_max']})\n"
        "■ 즉발 카드: 사용하면 턴이 끝나요. 손패에 즉발 카드가 있으면 턴을 넘길 수 없어요\n"
        f"■ 매 턴 시작에 {CFG['draw_per_turn']}장 뽑기{' (선공 첫 턴 제외)' if CFG['first_player_skips_draw'] else ''}\n"
        "■ 덱을 다 뽑았다면 내 덱 전체로 리필하고 " + f"{CFG['refill_draw']}장 뽑기\n"
        f"■ 손패 최대 {CFG['hand_limit']}장 (넘치면 뽑은 카드는 사라져요)\n"
        "■ 설치 중에는 'N턴 뒤 발동'(시한 만료)이나 '설치가 N장 이상일 때만 발동'하는 카드가 있어요\n"
        "■ 공격 카드를 쓰면 검은 아레나가 열려요: 공격하는 쪽은 카드마다 다른 방식으로 조종하고(마우스),\n"
        "  맞는 쪽은 WASD/방향키로 피해요. 맞은 만큼만 피해가 들어가요 (창 버전. 터미널은 자동 판정)\n"
        "  시작 전 안내 화면에서 양쪽이 모두 스페이스 키를 눌러야 시작해요 (결투는 양쪽 조작이 똑같아요)\n"
        "■ 공격 방식은 카드마다 달라요: 화살비·불비, 방패, 부채꼴, 레이저, 칼날 구체, 칼싸움(반격 피해!), 블랙홀, 차원문,\n"
        "  심판 격자, 치유 의식, 초록 구슬(상대 회복), 조작 반전·얼음판·시야 제한 등\n"
        "■ 상자 고르기 같은 확률 카드는 맞는 쪽이 직접 골라요: 안전하면 회복, 위험하면 피해\n"
        "■ 방어 설치(방벽)는 받는 피해를 N까지 막고, 다 막거나 지속 턴이 지나면 사라져요 (방벽 → 보호막 → 체력 순서)\n"
        "■ 필드 전용 카드는 아레나에서만 효과가 있어요 (피할 때 속도 증가 등)\n"
        "■ 특수 필드(스토리 모드): 숲속(4턴마다 양쪽에 벌레 떼) / 고요한 초원(2턴마다 양쪽 체력 ±1) / 거울 세계(매 턴 낮은 쪽 +1, 높은 쪽 -1)\n"
        "■ 등급: 일반(피해 1~2, 단독 효과) / 레어(2~4, 쓸만한 특수) /\n"
        "        영웅(3~5, 강하지만 리스크) / 레전드(각각 다른 독특한 효과, 판을 뒤집어요)")


def show_rules():
    print("\n" + rules_text())


def need_valid(deck):
    err = validate_deck(deck)
    if err:
        print("⚠", err, "→ 덱 구성에서 고쳐 주세요.")
        return False
    return True


def menu():
    deck = load_deck()
    while True:
        print("\n===== 한 장 승부 =====\n 1) AI 대전\n 2) 덱 구성\n 3) 규칙\n 0) 종료")
        s = input("선택 > ").strip()
        if s == "1" and need_valid(deck):
            play_ai(deck)
        elif s == "2":
            deck = deck_menu(deck)
        elif s == "3":
            show_rules()
        elif s == "0":
            return


def main(argv):
    global COLOR, AUTO
    if "--no-color" in argv or not sys.stdout.isatty():
        COLOR = False
    if "--auto" in argv:
        AUTO = True
    args = [a for a in argv if not a.startswith("--")]
    if os.name == "nt":
        os.system("")  # Windows 터미널에서 색상 활성화
    try:
        if not args:
            menu()
        elif args[0] == "ai":
            deck = load_deck() if not AUTO else auto_deck()
            if need_valid(deck):
                play_ai(deck)
        else:
            print(__doc__)
    except (KeyboardInterrupt, EOFError, SystemExit):
        print("\n게임을 종료합니다.")


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""한 장 승부 - 턴제 카드 배틀 (터미널 / AI 대전 / 온라인 대전)

실행:
    python cardgame.py                  메뉴
    python cardgame.py host             방 만들기 (방 코드가 나와요)
    python cardgame.py join 코드        방 참가 (방장이 알려 준 코드)
    python cardgame.py --no-color       색 끄기

카드와 규칙 숫자는 cards.json 에서 바꿉니다. 새 효과를 만들려면
OPS(문구)와 Game.run_fx(동작)에 추가하세요.
표준 라이브러리만 사용하므로 별도 설치가 필요 없습니다.
"""
import json
import os
import random
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DECK_FILE = os.path.join(HERE, "deck.json")
DEFAULT_PORT = 5050


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
ON_LABEL = {"play": "설치 즉시", "turnStart": "내 턴 시작",
            "turnEnd": "내 턴 끝", "hit": "피해를 받을 때", "expire": "시한 만료"}
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
            if ar.get("mode") not in ("shoot", "swarm", "zone", "chase", "bounce", "pick"):
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
                title, att, dfn = _ar.HELP[c["arena"]["mode"]]
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
        return (f"덱은 {CFG['deck_min']}~{CFG['deck_max']}장이어야 해요. "
                f"(지금 {len(deck) if isinstance(deck, list) else '?'}장)")
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
class Player:
    def __init__(self, deck):
        self.hp = CFG["start_hp"]
        self.deck_list = list(deck)
        self.deck = random.sample(deck, len(deck))
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
    def __init__(self, deck0, deck1):
        self.p = [Player(deck0), Player(deck1)]
        self.turn = random.randint(0, 1)
        self.over = False
        self.winner = None  # 0, 1, -1(무승부)
        self.log = []
        self.seq = 0
        self.installed = False             # 이번 턴에 설치 카드를 썼는지 (턴당 1장)
        self.last = None                   # 마지막으로 사용된 카드 (플레이어, 카드 id)
        self.last_instant = [None, None]   # 각 플레이어가 마지막으로 쓴 즉발 카드 (거울의 방용)
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
            self.over = True
            self.winner = -1 if len(dead) == 2 else 1 - dead[0]

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
        P.hp = min(CFG["max_hp"], P.hp + n)
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
                self.heal(o, max(v, (CFG["max_hp"] - P.hp + 1) // 2))
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
        if P.poison > 0:
            P.poison -= 1
            self.say(pi, "중독 피해")
            self.deal_damage(pi, 1, no_hit=True)
            if self.over:
                return
        self.fire(pi, "turnStart")
        if self.over:
            return
        if not (first and CFG["first_player_skips_draw"]):
            self.draw(pi, CFG["draw_per_turn"])

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
            if not self.over:
                self.pass_turn()
        self.seq += 1
        return True, ""

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
            else:
                self.say(1 - pi, "공격을 모두 피했어요!")
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
        r = arena.auto_resolve(pd["spec"], pd["seed"], pd["mods"], att_skill, def_skill)
        return self.resolve_attack(r)

    def end_turn(self, pi):
        if self.pending:
            return False, "공격이 진행 중이에요."
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
        return False, "알 수 없는 행동이에요."

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
            "me": {"hp": me.hp, "hand": list(me.hand), "dn": len(me.deck), "f": fld(me),
                   "in": 1 if (self.turn == pi and self.installed) else 0,
                   "ps": me.poison, "sh": me.shield},
            "op": {"hp": op.hp, "hn": len(op.hand), "dn": len(op.deck), "f": fld(op),
                   "ps": op.poison, "sh": op.shield},
            "pd": None if not self.pending else {
                "a": 0 if self.pending["pi"] == pi else 1, "cid": self.pending["cid"], "eff": self.pending["eff"],
                "spec": self.pending["spec"], "seed": self.pending["seed"], "mods": self.pending["mods"]},
            "lp": None if not self.last else [0 if self.last[0] == pi else 1, self.last[1]],
            "log": [[-1 if x is None else (0 if x == pi else 1), t] for x, t in self.log[-6:]],
        }


# ----------------------------------------------------------------------
# AI
# ----------------------------------------------------------------------
def fx_value(fx, me, op, copies, bonus, mirror_fx=None):
    sc = 0.0
    room = CFG["max_hp"] - me.hp
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
            sc += min(max(v, (CFG["max_hp"] - me.hp + 1) // 2), room) * (4 if me.hp <= 6 else 0.8)
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
        elif k == "discardSelf":
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
# 온라인 (TCP, 줄 단위 JSON). 방장이 게임을 진행하고 참가자는 행동만 보냅니다.
# ----------------------------------------------------------------------
class Conn:
    def __init__(self, sock):
        self.sock = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # 작은 메시지를 모아 보내지 않게 (지연 감소)
        except OSError:
            pass
        self.f = sock.makefile("rw", encoding="utf-8", newline="\n")

    def send(self, obj):
        self.f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.f.flush()

    def recv(self):
        line = self.f.readline()
        return json.loads(line) if line else None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def public_ip(timeout=2.0):
    """인터넷용 방 코드에 쓸 공인 IP (실패하면 None)"""
    try:
        from urllib.request import urlopen
        with urlopen("https://api.ipify.org", timeout=timeout) as r:
            ip = r.read().decode().strip()
        socket.inet_aton(ip)
        return ip
    except Exception:
        return None


# 방 코드 = 방장 주소(IP 4바이트 + 포트 2바이트 + 검사 1바이트)를 32진수 12글자로 줄인 것.
# 헷갈리는 글자(I L O U)를 뺀 알파벳이라 말로 불러 줘도 안전해요.
_ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def make_code(ip, port):
    b = bytes(int(x) for x in ip.split(".")) + port.to_bytes(2, "big")
    n = int.from_bytes(b + bytes([sum(b) % 256]), "big")
    s = "".join(_ALPHA[n >> (5 * i) & 31] for i in range(11, -1, -1))
    return "-".join(s[i:i + 4] for i in (0, 4, 8))


def parse_code(code):
    """방 코드 → (ip, 포트). 잘못된 코드면 ValueError"""
    s = "".join(ch for ch in str(code).upper() if ch.isalnum()).translate(str.maketrans("OILU", "011V"))
    if len(s) != 12 or any(ch not in _ALPHA for ch in s):
        raise ValueError("방 코드가 올바르지 않아요. 12글자(예: ABCD-EFGH-JKMN)를 확인해 주세요.")
    n = 0
    for ch in s:
        n = n * 32 + _ALPHA.index(ch)
    if n >> 56:
        raise ValueError("방 코드가 올바르지 않아요.")
    b = n.to_bytes(7, "big")
    if sum(b[:6]) % 256 != b[6]:
        raise ValueError("방 코드에 오타가 있어요. 다시 확인해 주세요.")
    return ".".join(map(str, b[:4])), int.from_bytes(b[4:6], "big")


def open_server(port=DEFAULT_PORT):
    """기본 포트가 쓰이는 중이면 빈 포트를 자동으로 골라요. → (서버 소켓, 실제 포트)"""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("", port))
    except OSError:
        srv.bind(("", 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def host_game(deck, port=DEFAULT_PORT):
    srv, port = open_server(port)
    print("방을 열었어요! 친구에게 아래 방 코드를 알려 주세요.")
    print(f"  같은 와이파이/LAN → {make_code(local_ip(), port)}")
    pub = public_ip()
    if pub:
        print(f"  인터넷            → {make_code(pub, port)}   (공유기에서 포트 {port} 포워딩 필요)")
    print("기다리는 중…")
    sock, addr = srv.accept()
    srv.close()
    c = Conn(sock)
    hello = c.recv()
    err = validate_hello(hello)
    if err:
        c.send({"t": "err", "msg": err})
        c.close()
        print("상대의 덱이 올바르지 않아 종료해요:", err)
        return
    print(f"{addr[0]} 접속! 게임을 시작합니다.")
    g = Game(deck, hello["deck"])
    try:
        c.send({"t": "st", "v": g.view_for(1), "n": None})
        while not g.over:
            if g.turn == 0:
                v = g.view_for(0)
                render(v)
                ok, msg = g.act(0, ask_action(v))
                if not ok:
                    print("⚠", msg)
                    continue
                settle(g)
                c.send({"t": "st", "v": g.view_for(1), "n": None})
            else:
                render(g.view_for(0))
                print("상대 차례… 기다리는 중")
                m = c.recv()
                if m is None:
                    print("상대의 연결이 끊어졌어요.")
                    return
                ok, msg = g.act(1, m)
                settle(g, show=False)
                c.send({"t": "st", "v": g.view_for(1), "n": None if ok else msg})
        render(g.view_for(0))
        show_result(g.view_for(0))
    except (BrokenPipeError, ConnectionError):
        print("상대의 연결이 끊어졌어요.")
    finally:
        c.close()


def validate_hello(m):
    if not m or m.get("t") != "hello":
        return "잘못된 접속이에요."
    return validate_deck(m.get("deck"))


def join_game(deck, code):
    try:
        ip, port = parse_code(code)
        c = Conn(socket.create_connection((ip, port), timeout=10))
    except ValueError as e:
        print(e)
        return
    except OSError as e:
        print("접속하지 못했어요 (방이 열려 있는지, 코드가 맞는지 확인해 주세요):", e)
        return
    c.sock.settimeout(None)
    c.send({"t": "hello", "deck": deck})
    try:
        while True:
            m = c.recv()
            if m is None:
                print("방장의 연결이 끊어졌어요.")
                return
            if m["t"] == "err":
                print("거절됨:", m["msg"])
                return
            if m.get("n"):
                print("⚠", m["n"])
            v = m["v"]
            render(v)
            if v["o"]:
                show_result(v)
                return
            if v["t"] == 1:
                c.send(ask_action(v))
            else:
                print("상대 차례… 기다리는 중")
    except (BrokenPipeError, ConnectionError):
        print("방장의 연결이 끊어졌어요.")
    finally:
        c.close()


# ----------------------------------------------------------------------
# 덱 구성 / 규칙 / 메뉴
# ----------------------------------------------------------------------
def deck_menu(deck):
    while True:
        n = rarity_counts(deck)
        meters = "  ".join(
            f"{RN[r]} {n[r]}/{'∞' if LIMIT[r] >= 10 ** 9 else LIMIT[r]}" for r in RORDER)
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
        "■ 상자 고르기 같은 확률 카드는 맞는 쪽이 직접 골라요: 안전하면 회복, 위험하면 피해\n"
        "■ 방어 설치(방벽)는 받는 피해를 N까지 막고, 다 막거나 지속 턴이 지나면 사라져요 (방벽 → 보호막 → 체력 순서)\n"
        "■ 필드 전용 카드는 아레나에서만 효과가 있어요 (피할 때 속도 증가 등)\n"
        "■ 등급: 일반(수치 1, 단독 효과 · 개미 떼만 같은 카드를 모으면 강해짐) / 레어(2~3, 쓸만한 특수) /\n"
        "        영웅(3, 강하지만 리스크) / 레전드(각각 다른 독특한 효과, 판을 뒤집어요)")


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
        print("\n===== 한 장 승부 =====\n 1) AI 대전\n 2) 방 만들기 (온라인)\n 3) 방 참가 (온라인)\n 4) 덱 구성\n 5) 규칙\n 0) 종료")
        s = input("선택 > ").strip()
        if s == "1" and need_valid(deck):
            play_ai(deck)
        elif s == "2" and need_valid(deck):
            host_game(deck)
        elif s == "3" and need_valid(deck):
            join_game(deck, input("방 코드 > ").strip())
        elif s == "4":
            deck = deck_menu(deck)
        elif s == "5":
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
        elif args[0] == "host":
            deck = load_deck() if not AUTO else auto_deck()
            if need_valid(deck):
                host_game(deck)
        elif args[0] == "join" and len(args) > 1:
            deck = load_deck() if not AUTO else auto_deck()
            if need_valid(deck):
                join_game(deck, args[1])
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

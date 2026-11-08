#!/usr/bin/env python3
"""한 장 승부 - tkinter 창 버전 (AI 대전 / 온라인 대전 / 덱 구성)

cardgame.py, cards.json 과 같은 폴더에 두고 실행하세요.
    python cardgame_gui.py

- 카드를 한 번 클릭하면 선택, 더블클릭하면 바로 사용
- 게임 규칙·AI는 cardgame.py 를 그대로 사용합니다.

온라인 대전 (창 버전끼리만):
  1) 한 명이 relay_server.py 를 켜 둬요:   python relay_server.py      (포트 5051)
  2) 모두 게임의 '온라인' 화면에서 '서버 주소'에 그 컴퓨터의 주소:포트 를 적어요 (한 번만, 저장돼요)
  3) 방장이 '방 만들기' → 5자리 방 번호가 나와요 → 친구가 그 번호로 '참가'
  4) 대기실에서 덱을 바꾸고, 둘 다 '준비완료'를 누르면 시작해요. 끝나면 대기실로 돌아와 다시 할 수 있어요
  (터미널 버전의 온라인은 예전 방식이라 창 버전과는 서로 연결되지 않아요)
"""
import json
import math
import os
import time
import queue
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import wave
from array import array
import tkinter as tk
from tkinter import ttk, messagebox

import arena as AR
from cardgame import (CARDS, CFG, RN, KN, RORDER, Game, ai_choose,
                      auto_deck, describe, load_deck, save_deck, validate_deck,
                      rarity_counts, LIMIT, card_notes, rules_text)

# ─── 색상 팔레트 ────────────────────────────────────────
BG_TOP, BG_BOTTOM = "#FFD58A", "#FFF6E5"
CARD_BG, CARD_SHADOW = "#FFFDF8", "#E8C07A"
TEXT_DARK, TEXT_MUTED = "#3A2B1A", "#9C8B72"
PRIMARY, PRIMARY_H, PRIMARY_P = "#FF7A30", "#FF9252", "#E85F12"
SECONDARY, SECONDARY_H, SECONDARY_P = "#5B8DEF", "#7AA3F5", "#3E6FD1"
TEAL, TEAL_DARK = "#2EC4B6", "#1FA89B"
SUCCESS_BG, SUCCESS_BD, SUCCESS_TXT = "#E3F9EC", "#3CCB7F", "#1F8A4C"
FAIL_BG, FAIL_BD, FAIL_TXT = "#FFE7E7", "#FF5C5C", "#D6334A"
NEUTRAL_BG, NEUTRAL_BD = "#FFF1DC", "#FFD9A6"
PAPER, PAPER_INK = "#F6EEDB", "#2A2118"
RC = {"common": "#8A7F66", "rare": "#3A6DB0", "hero": "#7B4EA6", "legend": "#C8921E"}
FONT = "맑은 고딕"
ARENA_BG = "#0B0B10"
AI_SKILL = 0.55              # AI가 조종할 때의 실력 (0~1)
ARENA_INTRO = 2.6            # 아레나 시작 전 안내 시간(초)
HANGUL_KEYS = {"ㅈ": "w", "ㅁ": "a", "ㄴ": "s", "ㅇ": "d"}   # 한글 입력 상태에서도 WASD가 먹히게
# 투사체 이모지 → 몸통 색. 이모지는 폰트/배경에 따라 안 보일 수 있어서, 몸통(색깔 도형)을 꼭 같이 그려요
GCOL = {"arrow": "#F2E2B0", "🔥": "#FF8A3D", "☄": "#FF8A3D", "⚡": "#FFE14D", "❄": "#9FE3FF", "🪨": "#A8A090", "🐝": "#F5C842",
        "🐜": "#E0803A", "🕷": "#B0A0C8", "💀": "#FF5C5C", "🍎": "#FF5C5C", "🗡": "#D0D8E8", "🪓": "#D0D8E8", "⚔": "#D0D8E8",
        "🪚": "#D0D8E8", "💨": "#BFD9FF", "🦇": "#B070FF", "🐍": "#5ADB7A", "💰": "#FFD166", "☠": "#9BE59D", "💣": "#FF8A3D",
        "💥": "#FFB020", "🖐": "#FFD0A0", "🪞": "#BFEFFF", "🎲": "#F5F5F5"}
MODE_ICON = {"shoot": "🎯", "swarm": "🐜", "zone": "🔥", "chase": "🗡", "bounce": "🎲", "pick": "🎁", "rain": "🏹",
             "orbit": "🌪", "duel": "⚔", "shield": "🛡", "cone": "🔥", "gamble": "💚", "channel": "✚", "knock": "💨",
             "vortex": "🌀", "warp": "🚪", "beam": "⚡", "grid": "⚖"}
W, H = 1300, 672


# ─── 헬퍼 ───────────────────────────────────────────────
def rrp(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(canvas, x1, y1, x2, y2, c1, c2, steps=80):
    r1, g1, b1 = canvas.winfo_rgb(c1)
    r2, g2, b2 = canvas.winfo_rgb(c2)
    h = y2 - y1
    for i in range(steps):
        t = i / steps
        col = "#%02x%02x%02x" % (int(r1 + (r2 - r1) * t) >> 8, int(g1 + (g2 - g1) * t) >> 8,
                                 int(b1 + (b2 - b1) * t) >> 8)
        canvas.create_rectangle(x1, y1 + h * i / steps, x2, y1 + h * (i + 1) / steps + 1, fill=col, outline=col)


def panel(canvas, x, y, w, h, r=20, pad=14, bg=CARD_BG):
    canvas.create_polygon(rrp(x + 5, y + 5, x + w + 5, y + h + 5, r), smooth=True, fill=CARD_SHADOW, outline="")
    canvas.create_polygon(rrp(x, y, x + w, y + h, r), smooth=True, fill=bg, outline="")
    f = tk.Frame(canvas, bg=bg)
    canvas.create_window(x + pad, y + pad, anchor="nw", window=f, width=w - 2 * pad, height=h - 2 * pad)
    return f


def glyph(c):
    if c.get("icon"):
        return c["icon"]
    if c.get("arena"):
        return MODE_ICON.get(c["arena"]["mode"], "⚔")
    m = c.get("mods", {})
    if not c.get("fx"):
        if m.get("surviveOnce"):
            return "✨"
        if m.get("dealBonus"):
            return "⚔"
        return "🛡"
    op = c["fx"][0]["op"]
    if c.get("on") == "expire":
        return "💣" if op == "dmg" else "🎁"
    return {"dmgRand": "🎲", "healRand": "🎲", "chance": "🎲", "dmgPerInstall": "💥",
            "healPerInstall": "🌱", "dmg": "⚔", "dmgPerCopy": "🐜", "dmgIf": "⚔", "heal": "💚", "healPerCopy": "🌿",
            "draw": "📜", "discard": "✂", "discardSelf": "🩸", "breakInstall": "💥",
            "selfdmg": "🩸", "steal": "🗝", "poison": "☠", "shield": "🛡", "swapHp": "🔄",
            "handSwap": "🔀", "timeStop": "⏳"}.get(op, "✦")


# ─── 커스텀 위젯 ─────────────────────────────────────────
THEMES = {"primary": (PRIMARY, PRIMARY_H, PRIMARY_P), "blue": (SECONDARY, SECONDARY_H, SECONDARY_P),
          "teal": (TEAL, "#3ED9CA", TEAL_DARK), "tan": ("#C9A876", "#D9BA8C", "#B5905F"), "gray": ("#8A9BB8", "#9EAECA", "#6F82A3")}


class RBtn(tk.Canvas):
    def __init__(self, parent, text, cmd=None, w=120, h=40, r=14, bg=CARD_BG, theme="primary", tc="#FFF", font=(FONT, 10, "bold")):
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0)
        fc, hc, pc = THEMES[theme] if isinstance(theme, str) else theme
        self.cmd, self.w, self.h, self.fc, self.hc, self.pc, self.tc = cmd, w, h, fc, hc, pc, tc
        self.on, self._sh = True, self.create_polygon(rrp(2, 2, w - 2, h - 2, r), smooth=True, fill=fc, outline="")
        self._tx = self.create_text(w / 2, h / 2, text=text, fill=tc, font=font)
        self.bind("<Enter>", lambda e: self.on and (self.itemconfig(self._sh, fill=self.hc), self.config(cursor="hand2")))
        self.bind("<Leave>", lambda e: self.on and self.itemconfig(self._sh, fill=self.fc))
        self.bind("<ButtonPress-1>", lambda e: self.on and self.itemconfig(self._sh, fill=self.pc))
        self.bind("<ButtonRelease-1>", self._rel)

    def _rel(self, e):
        if not self.on:
            return
        self.itemconfig(self._sh, fill=self.hc)
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h and self.cmd:
            self.cmd()

    def enable(self, v):
        self.on = v
        self.itemconfig(self._sh, fill=self.fc if v else "#D9D2C5")
        self.itemconfig(self._tx, fill=self.tc if v else "#A89C89")
        self.config(cursor="arrow")

    def set_text(self, t):
        self.itemconfig(self._tx, text=t)


class HPBar(tk.Canvas):
    def __init__(self, parent, bg=CARD_BG, w=360, h=18):
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0)
        self.w, self.h, self._bar = w, h, None
        self.create_polygon(rrp(0, 0, w, h, h / 2), smooth=True, fill="#F1E6D2", outline="")

    def set(self, hp, mx):
        if getattr(self, "_last", None) == (hp, mx):
            return
        self._last = (hp, mx)
        if self._bar:
            self.delete(self._bar)
            self._bar = None
        bw = self.w * max(0, min(1, hp / mx))
        col = FAIL_BD if hp <= 5 else TEAL
        if bw > self.h:
            self._bar = self.create_polygon(rrp(0, 0, bw, self.h, self.h / 2), smooth=True, fill=col, outline="")
        elif bw > 0:
            self._bar = self.create_oval(0, 0, self.h, self.h, fill=col, outline="")


class CardView(tk.Canvas):
    def __init__(self, parent, cid, w=130, h=182, bg=CARD_BG, selected=False, cmd=None, dbl=None, rcmd=None):
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0)
        c = CARDS[cid]
        rc = RC[c["rarity"]]
        s = w / 130
        self.create_polygon(rrp(5, 5, w - 1, h - 1, 12), smooth=True, fill=CARD_SHADOW, outline="")
        outline = SUCCESS_BD if selected else rc
        self.create_polygon(rrp(2, 2, w - 5, h - 5, 12), smooth=True, fill=PAPER, outline=outline,
                            width=5 if selected else 3)
        if c["rarity"] == "legend":
            self.create_polygon(rrp(6, 6, w - 9, h - 9, 9), smooth=True, fill="", outline="#F3D58A", width=1)
        hh = int(26 * s)
        self.create_polygon(rrp(6, 6, w - 9, 6 + hh, 9), smooth=True, fill=rc, outline="")
        avail = w - 14 - int(34 * s) - 12 - 12          # 이름이 들어갈 수 있는 폭
        fs = int(max(7, min(10 * s, avail / (len(c["name"]) * 1.45))))
        self.create_text(12, 6 + hh / 2, text=c["name"], anchor="w", font=(FONT, fs, "bold"), fill="#FFF")
        tw, th = int(34 * s), int(16 * s)
        inst = c["kind"] == "instant"
        self.create_polygon(rrp(w - 14 - tw, 6 + hh / 2 - th / 2, w - 14, 6 + hh / 2 + th / 2, 8), smooth=True,
                            fill="#FFF" if inst else rc, outline="#FFF")
        self.create_text(w - 14 - tw / 2, 6 + hh / 2, text=KN[c["kind"]], font=(FONT, max(7, int(8 * s)), "bold"),
                         fill=rc if inst else "#FFF")
        ay, ah = 6 + hh + 5, int(h * 0.28)
        self.create_rectangle(9, ay, w - 12, ay + ah, fill=mix(rc, PAPER, 0.82), outline="")
        self.create_text((w - 3) / 2, ay + ah / 2, text=glyph(c), font=(FONT, int(24 * s)))
        desc = describe(c)
        dfs = 8.5 if len(desc) <= 34 else 7.5 if len(desc) <= 52 else 7
        self.create_text(11, ay + ah + 5, anchor="nw", text=desc, width=w - 26,
                         font=(FONT, max(6, int(dfs * s))), fill=PAPER_INK)
        self.create_text(w - 13, h - 15, anchor="e", text=RN[c["rarity"]], font=(FONT, max(7, int(8 * s)), "bold"), fill=rc)
        if cmd:
            self.bind("<Button-1>", lambda e: cmd())
            self.config(cursor="hand2")
        if dbl:
            self.bind("<Double-Button-1>", lambda e: dbl())
        if rcmd:
            self.bind("<Button-3>", lambda e: rcmd())
            self.bind("<Button-2>", lambda e: rcmd())


def field_chip(parent, cid, left, on_click=None, hp=None):
    c = CARDS[cid]
    f = tk.Frame(parent, bg=PAPER, highlightbackground=RC[c["rarity"]], highlightthickness=2)
    a = tk.Label(f, text=f"{glyph(c)} {c['name']}  " + (f"({left}턴)" if left else "(영구)")
                 + (f"  🛡 {hp}/{c.get('barrier', hp)}" if hp else ""),
                 font=(FONT, 9, "bold"), bg=PAPER, fg=PAPER_INK)
    a.pack(anchor="w", padx=6, pady=(3, 0))
    b = tk.Label(f, text=describe(c), font=(FONT, 8), bg=PAPER, fg=TEXT_MUTED, wraplength=215, justify="left")
    b.pack(anchor="w", padx=6, pady=(0, 3))
    if on_click:                      # 클릭하면 카드 확대
        for w in (f, a, b):
            w.bind("<Button-1>", lambda e: on_click())
            w.config(cursor="hand2")
    return f


# ─── 네트워크 (줄 단위 JSON, cardgame.py 터미널 버전과 같은 규약) ─────
ONLINE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "online.json")
DEFAULT_SERVER = os.environ.get("HANJANG_SERVER", "127.0.0.1:5051")


def load_server():
    """저장된 중계 서버 주소 (없으면 기본값)"""
    try:
        with open(ONLINE_FILE, encoding="utf-8") as f:
            return json.load(f).get("server") or DEFAULT_SERVER
    except (OSError, ValueError, AttributeError):
        return DEFAULT_SERVER


def save_server(addr):
    try:
        with open(ONLINE_FILE, "w", encoding="utf-8") as f:
            json.dump({"server": addr}, f, ensure_ascii=False)
    except OSError:
        pass


def parse_server(text):
    """'주소:포트' → (주소, 포트). 포트를 안 적으면 5051"""
    t = text.strip()
    if not t:
        raise ValueError("서버 주소를 적어 주세요 (예: 192.168.0.12:5051)")
    host, port = t.rsplit(":", 1) if ":" in t else (t, "5051")
    if not host.strip() or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError("서버 주소 형식이 이상해요 (예: 192.168.0.12:5051)")
    return host.strip(), int(port)


class Net:
    """온라인 연결. 중계 서버(relay_server.py)에 접속해서 5자리 방 번호로 상대와 이어져요.
    이어진 뒤에는 서버가 메시지를 그대로 전달만 하고, 게임 계산은 방장(방을 만든 쪽) 컴퓨터가 해요.
    받은 것은 q 에 (종류, ...) 로 쌓이고 화면 쪽이 주기적으로 꺼내 가요:
      room(번호) / paired(역할) / msg(게임 메시지) / left(상대 퇴장) / error(문구) / disc(연결 끊김)"""

    def __init__(self):
        self.q, self.sock, self.closed, self.role = queue.Queue(), None, False, None
        self.ready = False          # (방장) 게임이 시작돼서 상태를 보내도 되는지

    def _reader(self, sock):
        buf = b""
        try:
            while not self.closed:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._dispatch(json.loads(line.decode("utf-8")))
        except (OSError, ValueError):
            pass
        if not self.closed:
            self.q.put(("disc",))

    def _dispatch(self, m):
        t = m.get("t") if isinstance(m, dict) else None
        if t == "r_room":
            self.q.put(("room", m.get("code", "")))
        elif t == "r_paired":
            self.q.put(("paired", m.get("role")))
        elif t == "r_err":
            self.q.put(("error", m.get("msg", "오류가 났어요.")))
        elif t == "r_left":
            self.q.put(("left",))
        else:
            self.q.put(("msg", m))

    def send(self, obj):
        if self.sock:
            try:
                self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass

    def _open(self, server, first):
        def run():
            try:
                sock = socket.create_connection(server, timeout=8)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(None)
            except OSError as e:
                self.q.put(("error", f"서버에 연결하지 못했어요. 서버 주소가 맞는지, 서버가 켜져 있는지 확인해 주세요. ({e})"))
                return
            if self.closed:
                sock.close()
                return
            self.sock = sock
            self.send(first)
            self._reader(sock)

        threading.Thread(target=run, daemon=True).start()

    def create(self, server):
        self.role = "host"
        self._open(server, {"t": "r_create"})

    def join(self, server, code):
        self.role = "guest"
        self._open(server, {"t": "r_join", "code": code})

    def close(self):
        self.closed = True
        if self.sock:
            for fn in (lambda: self.sock.shutdown(socket.SHUT_RDWR), self.sock.close):
                try:                       # shutdown 을 먼저 해야 읽는 중인 스레드도 깨고 상대(서버)에게 끊김이 전달돼요
                    fn()
                except OSError:
                    pass


# ─── 소리 (효과음을 직접 만들어서 재생) ─────────────────────
class Sound:
    """WAV 효과음을 코드로 합성해 재생합니다 (Windows: winsound / macOS: afplay / Linux: paplay·aplay·play).
    합성은 백그라운드 스레드에서 하고, 한 번 만든 파일은 임시 폴더에 캐시해서 다음 실행부터는 바로 씁니다.
    (예전에는 시작할 때 메인 스레드에서 8개를 전부 합성해서 창이 뜨기 전에 랙이 걸렸어요)
    재생 수단이 없으면 중요한 순간에만 시스템 '삑' 소리를 냅니다."""
    RATE = 22050
    VER = 2                                  # 소리 정의를 바꾸면 올려서 캐시를 갱신해요
    # 이름: ([(시작, 주파수(0=잡음), 길이, 음량, 감쇠)...], 전체 길이) — 자주 쓰는 소리를 앞에
    DEFS = {
        "play":     ([(0, 520, .07, .5, 8), (.03, 780, .09, .4, 8)], .15),
        "hit":      ([(0, 0, .12, .6, 7), (0, 140, .20, .9, 6), (0, 90, .22, .7, 5)], .25),
        "turn_me":  ([(0, 660, .16, .5, 4), (.12, 880, .30, .55, 4)], .45),
        "turn_opp": ([(0, 330, .22, .5, 5), (.12, 247, .30, .45, 5)], .45),
        "heal":     ([(0, 523, .12, .5, 3), (.10, 659, .12, .5, 3), (.20, 784, .12, .5, 3), (.30, 1047, .30, .5, 3)], .65),
        "win":      ([(0, 523, .2, .5, 3), (.18, 659, .2, .5, 3), (.36, 784, .2, .5, 3), (.54, 1047, .7, .6, 2.5)], 1.3),
        "lose":     ([(0, 392, .3, .5, 3), (.25, 330, .3, .5, 3), (.5, 262, .3, .5, 3), (.75, 196, .8, .5, 2.5)], 1.6),
        "legend":   ([(0, 0, .10, .5, 6), (0, 262, .9, .4, 2.5), (.08, 523, .6, .5, 3), (.20, 659, .6, .5, 3),
                      (.32, 784, .6, .5, 3), (.44, 1047, .9, .6, 2.5), (.58, 1319, 1.0, .5, 2.5),
                      (.58, 1568, 1.0, .3, 3)], 1.7),
    }

    def __init__(self, root):
        self.root, self.on, self.files, self.cmd, self.win, self.last = root, True, {}, None, None, {}
        if sys.platform.startswith("win"):
            try:
                import winsound
                self.win = winsound
            except ImportError:
                pass
        elif sys.platform == "darwin":
            self.cmd = ["afplay"]
        else:
            self.cmd = next(([c[0]] + c[1:] for c in (["paplay"], ["aplay", "-q"], ["play", "-q"]) if shutil.which(c[0])), None)
        self.dir = os.path.join(tempfile.gettempdir(), f"hanjang_snd_v{self.VER}")
        threading.Thread(target=self._build, daemon=True).start()

    def _render(self, parts, total):
        R, sin, exp, pi = self.RATE, math.sin, math.exp, math.pi
        n = int(R * total)
        buf = [0.0] * n
        rng = random.Random(1)
        for start, freq, dur, vol, decay in parts:        # freq 0 = 잡음(타격음)
            s0, m = int(start * R), int(dur * R)
            att, k = 0.004 * R, decay / m
            w = 2 * pi * freq / R
            for i in range(min(m, n - s0)):
                env = vol * min(1.0, i / att) * exp(-k * i)
                buf[s0 + i] += env * (rng.uniform(-1, 1) if freq == 0 else sin(w * i) + 0.35 * sin(2 * w * i))
        g = 0.9 * 32767 / max(1.0, max(map(abs, buf)))
        out = array("h", [int(max(-32767, min(32767, x * g))) for x in buf])
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()

    def _build(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            for name, (parts, total) in self.DEFS.items():
                path = os.path.join(self.dir, name + ".wav")
                if not os.path.exists(path):
                    tmp = path + ".tmp"
                    with wave.open(tmp, "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(self.RATE)
                        w.writeframes(self._render(parts, total))
                    os.replace(tmp, path)
                self.files[name] = path
                time.sleep(0.01)                  # 화면 그리기에 CPU를 양보
        except Exception:
            pass

    def play(self, name):
        if not self.on:
            return
        now = time.perf_counter()
        last = self.last.get(name, 0.0)
        if now - last < (0.10 if name in ("fire", "play", "hit", "heal") else 0.0):
            return
        self.last[name] = now
        path = self.files.get(name)
        try:
            if self.win and path:
                self.win.PlaySound(path, self.win.SND_FILENAME | self.win.SND_ASYNC)
                return
            if self.cmd and path:
                subprocess.Popen(self.cmd + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        except Exception:
            pass
        if name in ("turn_me", "legend"):
            try:
                self.root.bell()
            except tk.TclError:
                pass


class ArenaRenderer:
    """아레나 화면 그리기. 요소를 한 번만 만들고, 매 프레임에는 좌표/색이 바뀐 것만 갱신해요.
    (예전에는 매 프레임 전부 지우고 20~30개를 새로 만들어서 렉의 원인이었어요)
    카드의 arena.g 로 투사체 그림을 정해요: "arrow"=화살 모양 / 이모지(🔥🪨🐝 …)=그 글자 / 없으면 동그라미."""
    S = AR.SIZE
    hover = (0.0, 0.0)

    def __init__(self, cv, spec, me_att, cid, pick_rects):
        self.cv, self.spec, self.mode, self.me_def, self.me_att = cv, spec, spec["mode"], not me_att, me_att
        self.impl = "shoot" if self.mode in AR.SHOOTLIKE else self.mode
        self.cache, self.pools, self.flash = {}, {}, False
        self.g, self.gs, self.fog_r = spec.get("g"), spec.get("gs", 16), spec.get("fog", 0)
        self.pcol = spec.get("col") or GCOL.get(self.g) or ("#38D66B" if self.mode == "swarm" else "#E8D9B0")
        self.dpos = (0.0, 0.0)
        S = self.S
        for i in range(1, 6):                                   # 바닥 격자 (정적)
            cv.create_line(i * 100, 0, i * 100, S, fill="#14141C")
            cv.create_line(0, i * 100, S, i * 100, fill="#14141C")
        if self.mode == "knock":                                # 가시 벽
            cv.create_rectangle(4, 4, S - 4, S - 4, outline="#FF3B3B", width=4, dash=(10, 6))
        self.d_oval = cv.create_oval(0, 0, 0, 0, fill="#3DD6F5", outline="#FFFFFF", width=2, state="hidden")
        self.d_tag = cv.create_text(0, 0, text="나" if self.me_def else "상대", fill="#BFEFFF",
                                    font=(FONT, 9, "bold"), state="hidden")
        self.bar = cv.create_rectangle(0, 0, 0, 5, fill="#FFB020", outline="")
        self.hud = cv.create_text(10, 22, text="", anchor="w", fill="#E6E6F0", font=(FONT, 11, "bold"))
        self.tw_txt = cv.create_text(S / 2, 48, text="", fill="#FFD166", font=(FONT, 13, "bold"), state="hidden")
        self.fog_ring = cv.create_oval(0, 0, 0, 0, outline="#C8C8E0", width=2, dash=(3, 6), state="hidden")
        if self.mode == "shield":
            self.sh_arc = cv.create_arc(0, 0, 0, 0, style="arc", outline="#7FD1FF", width=6, start=0, extent=90, state="hidden")
        getattr(self, "_i_" + self.impl)(pick_rects)
        # 안내 / 결과 오버레이 (처음부터 만들어 두고 보였다 숨겼다만 해요)
        title, att_txt, def_txt = AR.help_for(spec)
        cx = S / 2
        self.intro = [
            cv.create_rectangle(40, 190, S - 40, 420, fill="#101018", outline="#FFD166", width=2, state="hidden"),
            cv.create_text(cx, 235, text=CARDS[cid]["name"], fill="#FFD166", font=(FONT, 30, "bold"), state="hidden"),
            cv.create_text(cx, 280, text="⚔ 당신이 공격!" if me_att else "🏃 당신이 피하세요!",
                           fill="#FF6B6B" if me_att else "#3DD6F5", font=(FONT, 20, "bold"), state="hidden"),
            cv.create_text(cx, 340, text=att_txt if me_att else def_txt, fill="#E6E6F0", font=(FONT, 12), width=480,
                           state="hidden"),
        ]
        self.count = cv.create_text(cx, 397, text="", fill="#FFFFFF", font=(FONT, 28, "bold"), state="hidden")
        self.res = [cv.create_rectangle(50, 225, S - 50, 375, fill="#101018", outline="#FFD166", width=2, state="hidden"),
                    cv.create_text(cx, 300, text="", fill="#FFFFFF", font=(FONT, 20, "bold"), width=470,
                                   justify="center", state="hidden")]
        self.intro_on = self.res_on = False

    # ── 도우미: 바뀐 것만 갱신 ──
    def cfg(self, item, **kw):
        last = self.cache.setdefault(item, {})
        diff = {k: v for k, v in kw.items() if last.get(k) != v}
        if diff:
            last.update(diff)
            self.cv.itemconfigure(item, **diff)

    def xy(self, item, *c):
        c = tuple(round(v, 1) for v in c)
        last = self.cache.setdefault(item, {})
        if last.get("xy") != c:
            last["xy"] = c
            self.cv.coords(item, *c)

    def show(self, item, on=True):
        self.cfg(item, state="normal" if on else "hidden")

    def show_all(self, items, on=True):
        for it in items:
            self.show(it, on)

    def show_group(self, g, on):
        for it in (g if isinstance(g, tuple) else (g,)):
            self.show(it, on)

    def vis(self, x, y):
        """시야 제한(fog): 내 점에서 멀리 있는 건 안 보여요"""
        return not self.fog_r or math.hypot(x - self.dpos[0], y - self.dpos[1]) <= self.fog_r

    def pool(self, name, data, make, place):
        lst = self.pools.setdefault(name, [])
        for i, d in enumerate(data):
            if i >= len(lst):
                lst.append(make())
            elif self.vis(d[0], d[1]):
                self.show_group(lst[i], True)
            place(lst[i], d)
            if not self.vis(d[0], d[1]):
                self.show_group(lst[i], False)
        for i in range(len(data), len(lst)):
            self.show_group(lst[i], False)

    def _low(self, g):
        for it in (g if isinstance(g, tuple) else (g,)):
            self.cv.tag_lower(it, self.d_oval)          # 새 요소는 플레이어 점 아래에
        return g

    # ── 투사체 그림 (화살 / 글자 / 동그라미) ──
    def mk_proj(self, color=None, size=None):
        """투사체 하나 = (색깔 몸통, 이모지 글자). 몸통은 항상 보이고, 이모지는 그 위에 흰색으로 얹어요"""
        cv, g = self.cv, self.g
        col = color or self.pcol
        if g == "arrow":
            body = cv.create_line(0, 0, 0, 0, fill=col, width=4, arrow="last", arrowshape=(13, 16, 6))
        else:
            body = cv.create_oval(0, 0, 0, 0, fill=col, outline=mix(col, "#FFFFFF", 0.45), width=1)
        lab = cv.create_text(0, 0, text="" if g == "arrow" else (g or ""), fill="#FFFFFF", font=(FONT, int(size or self.gs)))
        return self._low((body, lab))

    def put_proj(self, grp, x, y, r, ang=math.pi / 2, color=None, text=None):
        body, lab = grp
        if self.g == "arrow":
            L = max(24, r * 3.2)
            c, s = math.cos(ang) * L / 2, math.sin(ang) * L / 2
            self.xy(body, x - c, y - s, x + c, y + s)
        else:
            self.xy(body, x - r, y - r, x + r, y + r)
        if color:
            self.cfg(body, fill=color)
        self.xy(lab, x, y)
        if text is not None:
            self.cfg(lab, text=text)

    def aim_cross(self, a, b, ax, ay, size=7):
        self.xy(a, ax - size, ay, ax + size, ay)
        self.xy(b, ax, ay - size, ax, ay + size)
        self.show_all((a, b))

    def mk_cross(self, color):
        cv = self.cv
        return (cv.create_line(0, 0, 0, 0, fill=color, state="hidden"), cv.create_line(0, 0, 0, 0, fill=color, state="hidden"))

    @staticmethod
    def wedge(ox, oy, ang, half, L, n=10):
        pts = [ox, oy]
        for i in range(n + 1):
            a = ang - half + 2 * half * i / n
            pts += [ox + math.cos(a) * L, oy + math.sin(a) * L]
        return pts

    # ── 한 프레임 갱신 ──
    def update(self, s, ar, now):
        cv, S = self.cv, self.S
        fl = now < ar["flash"]
        if fl != self.flash:
            self.flash = fl
            cv.config(highlightbackground="#FF3B3B" if fl else "#2A2A38")
        if s:
            if self.mode != "pick":
                dx, dy = s["d"]
                r = s["dr"]
                self.dpos = (dx, dy)
                self.xy(self.d_oval, dx - r, dy - r, dx + r, dy + r)
                self.xy(self.d_tag, dx, dy - r - 9)
                self.cfg(self.d_oval, fill="#7A8BFF" if s.get("dst") == 3 else "#3DD6F5")
                self.show(self.d_oval)
                self.show(self.d_tag)
                if self.fog_r:
                    self.xy(self.fog_ring, dx - self.fog_r, dy - self.fog_r, dx + self.fog_r, dy + self.fog_r)
                    self.show(self.fog_ring)
            self.xy(self.bar, 0, 0, S * max(0.0, 1.0 - s["t"] / max(s["T"], 0.1)), 5)
            tw = s.get("tw")
            self.cfg(self.tw_txt, text=AR.TWIST_TXT.get(tw, ""), state="normal" if tw else "hidden")
            getattr(self, "_m_" + self.impl)(s)
        intro = ar["phase"] == "intro"
        if intro != self.intro_on:
            self.intro_on = intro
            for it in self.intro + [self.count]:
                self.show(it, intro)
                if intro:
                    cv.tag_raise(it)
        if intro:
            self.cfg(self.count, text=str(int(max(0.0, ARENA_INTRO - (now - ar["t0"]))) + 1))
        res = ar["phase"] == "result" and ar["result"] is not None
        if res != self.res_on:
            self.res_on = res
            for it in self.res:
                self.show(it, res)
                if res:
                    cv.tag_raise(it)
        if res:
            self.cfg(self.res[1], text=self.result_text(ar["result"]))

    def result_text(self, r):
        if self.mode == "pick":
            return "안전한 상자! 🍀" if r.get("safe") else "위험한 상자! 💥"
        d, me, sd, sh, fh = r["dmg"], self.me_att, r.get("self", 0), r.get("sheal", 0), r.get("fheal", 0)
        t = [(f"💥 {d} 피해를 입혔어요!" if d else "😤 못 맞혔어요…") if me else (f"💢 {d} 피해를 입었어요!" if d else "😎 모두 피했어요!")]
        if sd:
            t.append(f"⚔ 반격당해 {sd} 피해를 입었어요!" if me else f"⚔ 반격 성공! 상대가 {sd} 피해!")
        if sh:
            t.append(f"💚 체력 {sh} 회복!" if me else f"💚 상대가 {sh} 회복했어요…")
        if fh:
            t.append(f"💚 구슬을 먹어 {fh} 회복!" if not me else f"😖 상대가 {fh} 회복했어요…")
        return "\n".join(t)

    # ══════ 방식별 그리기 ══════
    # ── shoot / shield / gamble / knock ──
    def _i_shoot(self, _):
        cv = self.cv
        self.aim = cv.create_line(0, 0, 0, 0, fill="#FF3B3B", width=2, dash=(7, 5), state="hidden")
        self.tur = cv.create_rectangle(0, 0, 0, 0, fill="#8A8FA8", outline="#FF3B3B", width=2, state="hidden")

    def _m_shoot(self, s):
        tx, ty = s["tur"]
        self.xy(self.tur, tx - 9, ty - 9, tx + 9, ty + 9)
        self.show(self.tur)
        if s["left"] > 0:
            ax, ay = s["aim"]
            dx, dy = ax - tx, ay - ty
            L = math.hypot(dx, dy) or 1.0
            ux, uy = dx / L, dy / L
            t = 1e9
            if ux > 1e-9:
                t = min(t, (self.S - tx) / ux)
            elif ux < -1e-9:
                t = min(t, (0 - tx) / ux)
            if uy > 1e-9:
                t = min(t, (self.S - ty) / uy)
            elif uy < -1e-9:
                t = min(t, (0 - ty) / uy)
            self.xy(self.aim, tx, ty, tx + ux * t, ty + uy * t)
            self.show(self.aim)
        else:
            self.show(self.aim, False)
        br = s["br"]
        gamble, kinds = self.mode == "gamble", {0: "#FF5C5C", 1: "#38D66B", 2: "#B070FF"}
        base = "#FF5C5C" if gamble else self.pcol
        kinds[0] = base
        self.pool("b", s["b"], lambda: self.mk_proj(base),
                  lambda it, d: self.put_proj(it, d[0], d[1], br, d[3],
                                              kinds.get(d[2], base) if (d[2] or gamble) else None,
                                              self.gk_text(d[2])))
        if "sh" in s:                                           # 방패
            ang, half, sr, on, hp = s["sh"]
            dx, dy = s["d"]
            if self.me_def:                                     # 내 방패는 내 마우스를 바로 따라가요
                ang = math.atan2(s["da"][1] - dy, s["da"][0] - dx)
            da = math.degrees(-ang)
            self.xy(self.sh_arc, dx - sr, dy - sr, dx + sr, dy + sr)
            self.cfg(self.sh_arc, start=round(da - math.degrees(half), 1), extent=round(2 * math.degrees(half), 1),
                     outline=("#7FD1FF" if hp > 0.5 else "#FFD166" if hp > 0.25 else "#FF8A5C") if on else "#3A3A55",
                     width=6 if on else 2)
            self.show(self.sh_arc)
        self.cfg(self.hud, text=f"남은 {'구슬' if gamble else '발'} {s['left']}", fill="#E8D9B0")

    def gk_text(self, kind):
        return {1: "💚", 2: "🔮"}.get(kind, self.g if self.g != "arrow" else None)

    # ── swarm ──
    def _i_swarm(self, _):
        cv = self.cv
        self.ring = cv.create_oval(0, 0, 0, 0, outline="#38D66B", width=2, dash=(3, 3), state="hidden")
        self.cx1, self.cx2 = self.mk_cross("#38D66B")

    def _m_swarm(self, s):
        ax, ay = s["aim"]
        self.xy(self.ring, ax - 14, ay - 14, ax + 14, ay + 14)
        self.show(self.ring)
        self.aim_cross(self.cx1, self.cx2, ax, ay, 6)
        r = s["ar"]
        self.pool("a", s["a"], lambda: self.mk_proj(None, 11), lambda it, d: self.put_proj(it, d[0], d[1], r))
        self.cfg(self.hud, text=f"남은 {s['left']}마리", fill="#38D66B")

    # ── zone ──
    def _i_zone(self, _):
        cv = self.cv
        self.prev = cv.create_oval(0, 0, 0, 0, outline="#FF6B6B", width=2, dash=(6, 4), state="hidden")
        self.arc = cv.create_arc(0, 0, 0, 0, start=90, extent=0, style="arc", outline="#FFD166", width=3, state="hidden")
        self.dot = cv.create_oval(0, 0, 0, 0, fill="#FF6B6B", outline="", state="hidden")

    def _m_zone(self, s):
        items = (self.prev, self.arc, self.dot)
        if s["left"] > 0:
            ax, ay = s["aim"]
            r = s["r"]
            self.xy(self.prev, ax - r, ay - r, ax + r, ay + r)
            self.xy(self.arc, ax - r - 6, ay - r - 6, ax + r + 6, ay + r + 6)
            self.cfg(self.arc, extent=round(-359.9 * s["ch"], 1))
            self.xy(self.dot, ax - 3, ay - 3, ax + 3, ay + 3)
            self.show_all(items)
        else:
            self.show_all(items, False)
        warn = max(s["warn"], 0.01)
        g = self.g

        def make():
            cv = self.cv
            return self._low((cv.create_oval(0, 0, 0, 0, fill="#4A1212", outline="#FF3B3B", width=2),
                              cv.create_oval(0, 0, 0, 0, fill="#B81D1D", outline=""),
                              cv.create_oval(0, 0, 0, 0, outline="#FFD166", dash=(2, 3)),
                              cv.create_text(0, 0, text=g or "", font=(FONT, 20), fill="#FFFFFF")))

        def place(grp, z):
            x, y, r, st, t = z
            outer, inner, ring, txt = grp
            self.xy(outer, x - r, y - r, x + r, y + r)
            if st == 0:
                k = min(1.0, t / warn)
                self.cfg(outer, fill="#4A1212", outline="#FF3B3B")
                self.xy(inner, x - r * k, y - r * k, x + r * k, y + r * k)
                self.xy(ring, x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4)
                self.show_all((inner, ring))
                self.show(txt, False)
            else:
                self.cfg(outer, fill="#FFB020" if st == 1 else "#1B4D27", outline="#FFFFFF" if st == 1 else "#9BE59D")
                self.show_all((inner, ring), False)
                if g:
                    self.xy(txt, x, y)
                    self.cfg(txt, font=(FONT, max(14, int(r * 0.8))))
                self.show(txt, bool(g))
        self.pool("z", s["z"], make, place)
        self.cfg(self.hud, text=f"남은 폭격 {s['left']}", fill="#FF6B6B")

    # ── rain: 위에서 쏟아짐 ──
    def _i_rain(self, _):
        self._i_zone(_)

    def _m_rain(self, s):
        items = (self.prev, self.arc, self.dot)
        if s["left"] > 0 and not s["auto"]:
            ax, ay = s["aim"]
            r = s["r"]
            self.xy(self.prev, ax - r, ay - r, ax + r, ay + r)
            self.xy(self.arc, ax - r - 6, ay - r - 6, ax + r + 6, ay + r + 6)
            self.cfg(self.arc, extent=round(-359.9 * s["ch"], 1))
            self.xy(self.dot, ax - 3, ay - 3, ax + 3, ay + 3)
            self.show_all(items)
        else:
            self.show_all(items, False)
        rr, slant, g = s["rr"], s["slant"], self.g

        def make():
            cv = self.cv
            body, lab = self.mk_proj(None, 15)                                                          # 떨어지는 것
            return self._low((cv.create_oval(0, 0, 0, 0, outline="#FF3B3B", width=2, dash=(3, 3)),     # 착탄 표식
                              body, lab,
                              cv.create_oval(0, 0, 0, 0, fill="#FFB020", outline="#FFFFFF"),            # 착탄 폭발
                              cv.create_text(0, 0, text=g if g and g != "arrow" else "", font=(FONT, 18), fill="#FFFFFF")))

        def place(grp, d):
            x, y, p, st = d
            mark, body, lab, burst, fire = grp
            proj = (body, lab)
            if st == 0:
                self.xy(mark, x - rr, y - rr, x + rr, y + rr)
                px = x + slant * (y + 40) * (1 - p)
                py = -40 + (y + 40) * p
                self.put_proj(proj, px, py, 9, math.atan2(1.0, -slant))
                self.show_all((mark, body, lab))
                self.show_all((burst, fire), False)
            else:
                self.xy(burst, x - rr, y - rr, x + rr, y + rr)
                self.cfg(burst, fill="#FFB020" if st == 1 else "#7A2E0E", outline="#FFFFFF" if st == 1 else "#FF8A3D")
                self.show(burst)
                self.show_all((mark, body, lab), False)
                if st == 2 and g and g != "arrow":
                    self.xy(fire, x, y)
                self.show(fire, st == 2 and bool(g) and g != "arrow")
        self.pool("r", s["rn"], make, place)
        self.cfg(self.hud, text=f"남은 공격 {s['left']}", fill="#FFD166")

    # ── cone: 부채꼴 ──
    def _i_cone(self, _):
        cv = self.cv
        self.tur = cv.create_rectangle(0, 0, 0, 0, fill="#8A8FA8", outline="#FF3B3B", width=2, state="hidden")
        self.prev = self._low(cv.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline="#FF6B6B", width=2, dash=(6, 4), state="hidden"))

    def _m_cone(self, s):
        tx, ty = s["tur"]
        self.xy(self.tur, tx - 9, ty - 9, tx + 9, ty + 9)
        self.show(self.tur)
        half, L = s["half"], s["cl"]
        if s["left"] > 0:
            self.xy(self.prev, *self.wedge(tx, ty, s["aa"], half, L))
            self.show(self.prev)
        else:
            self.show(self.prev, False)
        g = self.g or "🔥"
        warn = max(s["warn"], 0.01)

        def make():
            cv = self.cv
            return self._low((cv.create_polygon(0, 0, 0, 0, 0, 0, fill="#4A1212", outline="#FF3B3B", width=2),
                              cv.create_polygon(0, 0, 0, 0, 0, 0, fill="#B81D1D", outline=""),
                              cv.create_text(0, 0, text=g, font=(FONT, 24), fill="#FFFFFF"), cv.create_text(0, 0, text=g, font=(FONT, 30), fill="#FFFFFF"),
                              cv.create_text(0, 0, text=g, font=(FONT, 22), fill="#FFFFFF")))

        def place(grp, c):
            x, y, ang, t, st = c
            outer, inner, f1, f2, f3 = grp
            self.xy(outer, *self.wedge(x, y, ang, half, L))
            if st == 0:
                k = min(1.0, t / warn)
                self.cfg(outer, fill="#4A1212", outline="#FF3B3B")
                self.xy(inner, *self.wedge(x, y, ang, half, L * k))
                self.show(inner)
                self.show_all((f1, f2, f3), False)
            else:
                self.cfg(outer, fill="#FFB020", outline="#FFFFFF")
                self.show(inner, False)
                for f, k in ((f1, 0.3), (f2, 0.6), (f3, 0.88)):
                    self.xy(f, x + math.cos(ang) * L * k, y + math.sin(ang) * L * k)
                    self.show(f)
        self.pool("c", s["cn"], make, place)
        self.cfg(self.hud, text=f"남은 발사 {s['left']}", fill="#FF6B6B")

    # ── beam: 레이저 ──
    def _i_beam(self, _):
        cv = self.cv
        self.tur = cv.create_rectangle(0, 0, 0, 0, fill="#8A8FA8", outline="#FF3B3B", width=2, state="hidden")
        self.prev = self._low(cv.create_line(0, 0, 0, 0, fill="#FF6B6B", width=2, dash=(7, 5), state="hidden"))
        self.b_out = self._low(cv.create_line(0, 0, 0, 0, fill="#FF5C3B", width=10, state="hidden"))
        self.b_core = self._low(cv.create_line(0, 0, 0, 0, fill="#FFFFFF", width=4, state="hidden"))

    def _m_beam(self, s):
        tx, ty = s["tur"]
        self.xy(self.tur, tx - 9, ty - 9, tx + 9, ty + 9)
        self.show(self.tur)
        b, far = s["bm"], 1100
        if b:
            x, y, a, st, t = b
            ex, ey = x + math.cos(a) * far, y + math.sin(a) * far
            self.xy(self.b_out, x, y, ex, ey)
            self.xy(self.b_core, x, y, ex, ey)
            if st == 0:                                          # 충전: 가는 선 (점점 굵어져요)
                k = min(1.0, t / max(s["warn"], 0.01))
                self.cfg(self.b_out, width=2 + int(4 * k), fill="#FF3B3B")
                self.cfg(self.b_core, width=1)
                self.show(self.b_out)
                self.show(self.b_core, False)
            else:
                self.cfg(self.b_out, width=int(s["bw"] * 1.4), fill="#FF8A3D")
                self.cfg(self.b_core, width=max(3, int(s["bw"] * 0.5)))
                self.show_all((self.b_out, self.b_core))
            self.show(self.prev, False)
        else:
            self.show_all((self.b_out, self.b_core), False)
            if s["left"] > 0:
                a = s["aa"]
                self.xy(self.prev, tx, ty, tx + math.cos(a) * far, ty + math.sin(a) * far)
                self.show(self.prev)
            else:
                self.show(self.prev, False)
        self.cfg(self.hud, text=f"남은 레이저 {s['left']}", fill="#FF8A3D")

    # ── chase ──
    def _i_chase(self, _):
        cv = self.cv
        self.cx1, self.cx2 = self.mk_cross("#FFD166")
        self.blade = self._low(cv.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, fill=self.pcol if self.g else "#FF5C5C",
                                                 outline="#FFFFFF", width=2, state="hidden"))
        self.bglyph = self._low(cv.create_text(0, 0, text=self.g or "", font=(FONT, 20), state="hidden", fill="#FFFFFF"))

    def _m_chase(self, s):
        ax, ay = s["aim"]
        self.aim_cross(self.cx1, self.cx2, ax, ay, 8)
        x, y = s["c"]
        r = s["cr"]
        vis = self.vis(x, y)
        self.xy(self.blade, x, y - r, x + r, y, x, y + r, x - r, y)
        self.show(self.blade, vis)
        if self.g:
            self.xy(self.bglyph, x, y)
            self.cfg(self.bglyph, font=(FONT, max(14, int(r * 1.5))))
            self.show(self.bglyph, vis)

    # ── orbit: 회전 칼날 구체 ──
    def _i_orbit(self, _):
        cv = self.cv
        self.cx1, self.cx2 = self.mk_cross("#FFD166")
        self.o_body = self._low(cv.create_oval(0, 0, 0, 0, fill="#5A2A8A", outline="#FFFFFF", width=2, state="hidden"))
        self.o_txt = self._low(cv.create_text(0, 0, text="✦", fill="#FFFFFF", font=(FONT, 16, "bold"), state="hidden"))

    def _m_orbit(self, s):
        ox, oy = s["o"]
        ax, ay = s["aim"]
        self.aim_cross(self.cx1, self.cx2, ax, ay, 8)
        b = s["body"]
        vis = self.vis(ox, oy)
        self.xy(self.o_body, ox - b, oy - b, ox + b, oy + b)
        self.cfg(self.o_body, fill="#FF5C8A" if s["bst"] else "#5A2A8A")
        self.xy(self.o_txt, ox, oy)
        self.show_all((self.o_body, self.o_txt), vis)
        L, nb, th, bw, g = s["bl"], s["nb"], s["th"], s["bw"], self.g

        def make():
            cv = self.cv
            return self._low((cv.create_line(0, 0, 0, 0, fill="#C8D0E0", width=int(bw * 0.7)),
                              cv.create_text(0, 0, text=g or "🗡", font=(FONT, 20), fill="#FFFFFF")))
        data = [(ox + math.cos(th + i * math.tau / nb) * L, oy + math.sin(th + i * math.tau / nb) * L, ox, oy) for i in range(nb)]

        def place(grp, d):
            self.xy(grp[0], d[2], d[3], d[0], d[1])
            self.xy(grp[1], d[0], d[1])
            self.cfg(grp[0], fill="#FF8AB0" if s["bst"] else "#C8D0E0")
        self.pool("bl", data, make, place)
        if not vis:
            for grp in self.pools.get("bl", []):
                self.show_group(grp, False)

    # ── duel: 칼싸움 ──
    def _i_duel(self, _):
        cv = self.cv
        self.a_oval = self._low(cv.create_oval(0, 0, 0, 0, fill="#FF5C5C", outline="#FFFFFF", width=2, state="hidden"))
        self.a_tag = self._low(cv.create_text(0, 0, text="나" if self.me_att else "상대", fill="#FFD0D0",
                                              font=(FONT, 9, "bold"), state="hidden"))
        self.a_arc = self._low(cv.create_arc(0, 0, 0, 0, style="pieslice", fill="#5A2222", outline="#FF8A8A", state="hidden"))
        self.d_arc = self._low(cv.create_arc(0, 0, 0, 0, style="pieslice", fill="#1F3A5A", outline="#8AD1FF", state="hidden"))
        self.a_sw = self._low(cv.create_text(0, 0, text="🗡", font=(FONT, 22), state="hidden", fill="#FFFFFF"))
        self.d_sw = self._low(cv.create_text(0, 0, text="🗡", font=(FONT, 22), state="hidden", fill="#FFFFFF"))
        self.a_ln = self._low(cv.create_line(0, 0, 0, 0, fill="#FFB0B0", width=4, state="hidden"))
        self.d_ln = self._low(cv.create_line(0, 0, 0, 0, fill="#B0E0FF", width=4, state="hidden"))
        self.stun_a = cv.create_text(0, 0, text="💫", font=(FONT, 16), state="hidden", fill="#FFFFFF")
        self.stun_d = cv.create_text(0, 0, text="💫", font=(FONT, 16), state="hidden", fill="#FFFFFF")

    def _fighter(self, x, y, face, lock, st, prog, reach, arc, arc_it, ln, sw, stun, tint):
        wind, rec = st == 1, st == 2
        if wind:                                                 # 베는 동안 칼이 호를 쓸고 지나가요
            ang = lock - arc + 2 * arc * prog
        elif rec:
            ang = lock + arc
        else:
            ang = face
        L = reach * 0.92
        ex, ey = x + math.cos(ang) * L, y + math.sin(ang) * L
        self.xy(ln, x, y, ex, ey)
        self.xy(sw, ex, ey)
        self.show_all((ln, sw), st != 3)
        self.cfg(ln, fill="#6A6A7A" if rec else tint)
        if wind:
            R = reach
            self.xy(arc_it, x - R, y - R, x + R, y + R)
            self.cfg(arc_it, start=round(math.degrees(-lock) - math.degrees(arc), 1), extent=round(2 * math.degrees(arc), 1))
        self.show(arc_it, wind)
        self.xy(stun, x, y - 24)
        self.show(stun, st == 3)

    def _m_duel(self, s):
        ax, ay = s["a"]
        self.xy(self.a_oval, ax - 10, ay - 10, ax + 10, ay + 10)
        self.xy(self.a_tag, ax, ay - 19)
        self.show_all((self.a_oval, self.a_tag))
        dx, dy = s["d"]
        self._fighter(ax, ay, s["af"], s["al"], s["ast"], s["ap"], s["reach"], s["arc"], self.a_arc, self.a_ln, self.a_sw, self.stun_a, "#FFB0B0")
        self._fighter(dx, dy, s["df"], s["dl"], s["dst"], s["dp"], s["reach"], s["arc"], self.d_arc, self.d_ln, self.d_sw, self.stun_d, "#B0E0FF")
        self.cfg(self.hud, text="베기: 클릭" if self.me_att else "베기: 클릭 / 스페이스", fill="#FFB0B0")

    # ── vortex: 블랙홀 ──
    def _i_vortex(self, _):
        cv = self.cv
        self.v_pull = self._low(cv.create_oval(0, 0, 0, 0, outline="#7A4AD6", width=2, dash=(4, 6), state="hidden"))
        self.v_boom = self._low(cv.create_oval(0, 0, 0, 0, outline="#FF3B3B", width=2, dash=(5, 4), state="hidden"))
        self.v_boom_f = self._low(cv.create_oval(0, 0, 0, 0, fill="#B81D1D", outline="", state="hidden"))
        self.v_core = self._low(cv.create_oval(0, 0, 0, 0, fill="#07030F", outline="#B070FF", width=3, state="hidden"))
        self.v_txt = self._low(cv.create_text(0, 0, text=self.g or "🌀", font=(FONT, 26), state="hidden", fill="#FFFFFF"))
        self.cx1, self.cx2 = self.mk_cross("#B070FF")

    def _m_vortex(self, s):
        hx, hy = s["h"]
        rp, rc = s["rp"], s["rc"]
        vis = self.vis(hx, hy)
        self.xy(self.v_pull, hx - rp, hy - rp, hx + rp, hy + rp)
        self.xy(self.v_core, hx - rc, hy - rc, hx + rc, hy + rc)
        self.xy(self.v_txt, hx, hy)
        self.show_all((self.v_pull, self.v_core, self.v_txt), vis)
        if s["boom"] and s["bp"] > 0:
            R = s["boom"]
            self.xy(self.v_boom, hx - R, hy - R, hx + R, hy + R)
            k = s["bp"]
            self.xy(self.v_boom_f, hx - R * k, hy - R * k, hx + R * k, hy + R * k)
            self.show_all((self.v_boom, self.v_boom_f), vis)
        else:
            self.show_all((self.v_boom, self.v_boom_f), False)
        if self.me_att:
            self.aim_cross(self.cx1, self.cx2, *s["aim"], 7)

    # ── warp: 차원문 ──
    def _i_warp(self, _):
        self.cx1, self.cx2 = self.mk_cross("#B070FF")

    def _m_warp(self, s):
        pr, er, warn = s["pr"], s["er"], max(s["warn"], 0.01)
        if self.me_att and s["left"] > 0:
            self.aim_cross(self.cx1, self.cx2, *s["aim"], 9)

        def make():
            cv = self.cv
            return self._low((cv.create_oval(0, 0, 0, 0, outline="#FF8A3D", width=2, dash=(4, 4)),          # 출구
                              cv.create_text(0, 0, text="❓", font=(FONT, 14), fill="#FFFFFF"),
                              cv.create_line(0, 0, 0, 0, fill="#7A4AD6", dash=(3, 5)),                        # 연결선
                              cv.create_oval(0, 0, 0, 0, fill="#2A0F4A", outline="#B070FF", width=3),         # 입구
                              cv.create_text(0, 0, text="🌀", font=(FONT, 22), fill="#FFFFFF")))

        def place(grp, p):
            x, y, xx, xy_, age = p
            ex, ring, link, ent, txt = grp
            on = age >= 0.35
            self.xy(ent, x - pr, y - pr, x + pr, y + pr)
            self.cfg(ent, outline="#E0B0FF" if on else "#5A3A7A", fill="#2A0F4A" if on else "#150826")
            self.xy(txt, x, y)
            self.xy(ex, xx - er * 0.5, xy_ - er * 0.5, xx + er * 0.5, xy_ + er * 0.5)
            self.xy(ring, xx, xy_)
            self.xy(link, x, y, xx, xy_)
        self.pool("p", s["pt"], make, place)

        def make2():
            cv = self.cv
            return self._low((cv.create_oval(0, 0, 0, 0, fill="#4A1212", outline="#FF3B3B", width=2),
                              cv.create_oval(0, 0, 0, 0, fill="#B81D1D", outline="")))

        def place2(grp, b):
            x, y, t = b
            k = min(1.0, t / warn)
            self.xy(grp[0], x - er, y - er, x + er, y + er)
            self.xy(grp[1], x - er * k, y - er * k, x + er * k, y + er * k)
        self.pool("w", s["bl"], make2, place2)
        self.cfg(self.hud, text=f"남은 차원문 {s['left']}", fill="#B070FF")

    # ── grid: 심판의 격자 ──
    def _i_grid(self, _):
        cv, n = self.cv, int(self.spec.get("n", 3))
        cs = self.S / n
        self.cells = {}
        for i in range(n):
            for j in range(n):
                self.cells[(i, j)] = self._low(cv.create_rectangle(i * cs + 3, j * cs + 3, (i + 1) * cs - 3, (j + 1) * cs - 3,
                                                                    fill="", outline="#2A2A3A", width=2))
        self.cursor = cv.create_rectangle(0, 0, 0, 0, outline="#FFD166", width=3, dash=(6, 4), state="hidden")
        self.gn, self.cs = n, cs

    def _m_grid(self, s):
        state = {}
        for i, j, t, st in s["gc"]:
            state[(i, j)] = (t, st)
        warn = max(s["warn"], 0.01)
        for key, it in self.cells.items():
            if key in state:
                t, st = state[key]
                if st == 0:
                    pulse = int(t / warn * 6) % 2
                    self.cfg(it, fill="#5A1616" if pulse else "#4A1212", outline="#FF3B3B")
                else:
                    self.cfg(it, fill="#FFB020", outline="#FFFFFF")
            else:
                self.cfg(it, fill="", outline="#2A2A3A")
        if self.me_att and s["left"] > 0 and not self.spec.get("auto"):
            ax, ay = s["aim"]
            i, j = int(min(self.gn - 1, ax // self.cs)), int(min(self.gn - 1, ay // self.cs))
            self.xy(self.cursor, i * self.cs + 6, j * self.cs + 6, (i + 1) * self.cs - 6, (j + 1) * self.cs - 6)
            self.show(self.cursor)
        else:
            self.show(self.cursor, False)
        self.cfg(self.hud, text=f"남은 {'심판' if self.spec.get('auto') else '칸'} {s['left']}", fill="#FF6B6B")

    # ── channel: 치유 의식 ──
    def _i_channel(self, _):
        cv = self.cv
        self.c_circ = self._low(cv.create_oval(0, 0, 0, 0, fill="#10301C", outline="#38D66B", width=3, state="hidden"))
        self.c_arc = self._low(cv.create_arc(0, 0, 0, 0, start=90, extent=0, style="arc", outline="#FFD166", width=5, state="hidden"))
        self.c_txt = self._low(cv.create_text(0, 0, text=self.g or "✚", fill="#9BE59D", font=(FONT, 30, "bold"), state="hidden"))
        self.c_pct = self._low(cv.create_text(0, 0, text="", fill="#FFFFFF", font=(FONT, 12, "bold"), state="hidden"))
        self.cx1, self.cx2 = self.mk_cross("#38D66B")

    def _m_channel(self, s):
        x, y, r = s["ch"]
        vis = self.vis(x, y)
        self.xy(self.c_circ, x - r, y - r, x + r, y + r)
        self.cfg(self.c_circ, fill="#3A1414" if s["inn"] else "#10301C", outline="#FF6B6B" if s["inn"] else "#38D66B")
        self.xy(self.c_arc, x - r - 7, y - r - 7, x + r + 7, y + r + 7)
        self.cfg(self.c_arc, extent=round(-359.9 * s["pg"], 1))
        self.xy(self.c_txt, x, y - 4)
        self.xy(self.c_pct, x, y + 22)
        self.cfg(self.c_pct, text=f"+{round(s['heal'] * s['pg'])}")
        self.show_all((self.c_circ, self.c_arc, self.c_txt, self.c_pct), vis)
        if self.me_att:
            self.aim_cross(self.cx1, self.cx2, *s["aim"], 7)
        msg = "💥 방해받는 중!" if s["inn"] else ("🌀 순간이동 가능: 클릭" if s["bk"] <= 0 and self.me_att else "의식 진행 중")
        self.cfg(self.hud, text=msg, fill="#FF6B6B" if s["inn"] else "#9BE59D")

    # ── bounce ──
    def _i_bounce(self, _):
        pass

    def _m_bounce(self, s):
        r, g = s["dcr"], self.g

        def make():
            cv = self.cv
            return self._low((cv.create_oval(0, 0, 0, 0, fill=self.pcol, outline=mix(self.pcol, "#FFFFFF", 0.45), width=1),
                              cv.create_text(0, 0, text=g or "🎲", fill="#FFFFFF" if g else "#222222", font=(FONT, int(r * 1.3)))))

        def place(grp, d):
            self.xy(grp[0], d[0] - r, d[1] - r, d[0] + r, d[1] + r)
            self.xy(grp[1], d[0], d[1])
        self.pool("d", s["dc"], make, place)

    # ── pick ──
    def _i_pick(self, pick_rects):
        cv, S = self.cv, self.S
        self.boxes = []
        for (x1, y1, x2, y2) in pick_rects:
            r = cv.create_rectangle(x1, y1, x2, y2, fill="#2A2A38", outline="#8A8FA8", width=2)
            t = cv.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="", fill="#FFFFFF", font=(FONT, 28, "bold"))
            self.boxes.append((r, t, (x1, y1, x2, y2)))
        self.hint = cv.create_text(S / 2, 190, text="", fill="#FFD166", font=(FONT, 18, "bold"))
        self.ptime = cv.create_text(S / 2, 430, text="", fill="#9AA0B5", font=(FONT, 12))

    def _m_pick(self, s):
        picked, danger = s["picked"], s.get("danger") or []
        mx, my = self.hover
        for i, (r, t, (x1, y1, x2, y2)) in enumerate(self.boxes):
            hover = self.me_def and picked is None and x1 <= mx <= x2 and y1 <= my <= y2
            if picked is None:
                self.cfg(r, fill="#3A3A55" if hover else "#2A2A38", outline="#8A8FA8", width=2)
                self.cfg(t, text=str(i + 1))
            else:
                bad = i in danger
                self.cfg(r, fill="#7A1F1F" if bad else "#1F6A3A", outline="#FFD166" if i == picked else "#8A8FA8",
                         width=4 if i == picked else 2)
                self.cfg(t, text="☠" if bad else "♥")
        hint = ("상자를 고르세요! (클릭 / 숫자키)" if self.me_def else "상대가 상자를 고르는 중…") if picked is None else \
            ("안전 상자!" if s["safe"] else "위험 상자!")
        self.cfg(self.hint, text=hint)
        self.cfg(self.ptime, text=f"남은 시간 {max(0.0, s['T'] - s['t']):0.1f}초" if picked is None else "")


# ─── 앱 ─────────────────────────────────────────────────
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🃏 한 장 승부")
        self.root.geometry(f"{W}x{H}")
        self.root.resizable(False, False)
        self.deck = load_deck()
        self.mode = None          # None | 'ai' | 'host' | 'guest'
        self.g, self.view, self.sel_id, self.net = None, None, None, None
        self.deck_back = "menu"          # 덱 화면의 '뒤로' 목적지 (메뉴 / 대기실)
        self.reset_lobby_state()
        self.ai_job, self.prev_hp, self.msg_job, self.fx_token, self.fx_widgets = None, None, None, 0, []
        self.sound, self.zoom_f = Sound(self.root), None
        self.root.bind("<Escape>", lambda e: self.close_zoom())
        # 실시간 아레나 상태
        self.ar, self.keys, self.key_jobs, self.mouse = None, set(), {}, (AR.SIZE / 2, AR.SIZE / 2)
        self.click_count, self.pick_sent = 0, None
        self.guest_arena = False      # (방장) 상대가 아레나를 지원하는지
        self.remote_in = {}           # (방장) 상대가 보낸 아레나 입력
        self.root.bind("<KeyPress>", self.on_key_down)
        self.root.bind("<KeyRelease>", self.on_key_up)
        self.screens = {}
        self.build_menu()
        self.show("menu")
        self.root.update()                    # 메뉴를 먼저 그려서 창이 바로 보이게 하고
        self.build_deck()                     # 나머지 화면은 그 뒤에 만들어요
        self.build_online()
        self.build_lobby()
        self.build_battle()
        self.root.after(15, self.poll)

    def run(self):
        self.root.mainloop()

    # ── 공통 ──
    def make_screen(self, name):
        f = tk.Frame(self.root)
        c = tk.Canvas(f, width=W, height=H, highlightthickness=0)
        c.pack(fill="both", expand=True)
        vgrad(c, 0, 0, W, H, BG_TOP, BG_BOTTOM)
        self.screens[name] = f
        return f, c

    def show(self, name):
        for f in self.screens.values():
            f.place_forget()
        self.screens[name].place(x=0, y=0, relwidth=1, relheight=1)
        self.current = name
        if name == "menu":
            self.update_menu()
        if name == "deck":
            self.deck_back_btn.set_text("← 대기실" if self.deck_back == "lobby" else "← 메뉴")
            self.update_deck_ui()
        if name == "lobby":
            self.lobby_sync()

    def deck_ok(self):
        err = validate_deck(self.deck)
        if err:
            messagebox.showwarning("덱을 확인하세요", err)
            self.show("deck")
            return False
        return True

    # ── 메뉴 ──
    def build_menu(self):
        f, c = self.make_screen("menu")
        c.create_text(W / 2, 62, text="🃏 한 장 승부", font=(FONT, 42, "bold"), fill=TEXT_DARK)
        c.create_text(W / 2, 112, text="설치로 판을 깔고, 즉발로 승부를 내는 1:1 카드 배틀", font=(FONT, 12), fill=TEXT_MUTED)
        p = panel(c, W / 2 - 230, 140, 460, 465, r=26, pad=22)
        self.menu_deck_lbl = tk.Label(p, font=(FONT, 11, "bold"), bg=CARD_BG)
        self.menu_deck_lbl.pack(pady=(0, 10))
        items = [("⚔  AI 대전", self.start_ai, PRIMARY, PRIMARY_H, PRIMARY_P),
                 ("🌐  방 만들기 / 참가 (온라인)", lambda: self.show("online"), SECONDARY, SECONDARY_H, SECONDARY_P),
                 ("🃏  덱 구성", lambda: self.open_deck("menu"), TEAL, "#3ED9CA", TEAL_DARK),
                 ("📖  규칙 보기", self.show_rules, "#E07B2A", "#F09040", "#C06010"),
                 ("🚪  종료", self.root.destroy, "#C9A876", "#D9BA8C", "#B5905F")]
        for t, cmd, a, b, d in items:
            RBtn(p, t, cmd, w=380, h=54, r=18, theme=(a, b, d), font=(FONT, 13, "bold")).pack(pady=5)

    def update_menu(self):
        err = validate_deck(self.deck)
        if err:
            self.menu_deck_lbl.config(text=f"내 덱 {len(self.deck)}장 — 덱 구성이 필요해요 ({CFG['deck_min']}~{CFG['deck_max']}장)", fg=FAIL_TXT)
        else:
            self.menu_deck_lbl.config(text=f"내 덱 {len(self.deck)}장 ✔ 준비 완료", fg=SUCCESS_TXT)

    def show_rules(self):
        messagebox.showinfo("규칙", rules_text().replace("(창 버전. 터미널은 자동 판정)", "(한글 입력 상태에서도 돼요)")
                            + "\n\n카드 클릭 = 선택, 더블클릭 = 바로 사용\n오른쪽 클릭 / '🔍 자세히' 버튼 / 설치된 카드 클릭 = 카드 확대 (덱 구성에서는 카드 클릭)")

    # ── 덱 구성 ──
    def build_deck(self):
        f, c = self.make_screen("deck")
        bar = panel(c, 20, 16, 1260, 72, r=20, pad=12)
        self.deck_back_btn = RBtn(bar, "← 메뉴", lambda: self.show(self.deck_back), w=110, h=42, theme="blue")
        self.deck_back_btn.pack(side="left", padx=(0, 14))
        tk.Label(bar, text="🃏 덱 구성", font=(FONT, 18, "bold"), bg=CARD_BG, fg=TEXT_DARK).pack(side="left")
        self.deck_total = tk.Label(bar, font=(FONT, 13, "bold"), bg=CARD_BG)
        self.deck_total.pack(side="left", padx=18)
        self.meters = {}
        for r in RORDER:
            lb = tk.Label(bar, font=(FONT, 10, "bold"), bg=CARD_BG, fg=RC[r])
            lb.pack(side="left", padx=6)
            self.meters[r] = lb
        RBtn(bar, "비우기", self.deck_clear, w=90, h=42, theme="tan").pack(side="right")
        RBtn(bar, "자동 구성", self.deck_auto, w=110, h=42, theme="teal").pack(side="right", padx=8)

        cont = tk.Frame(c, bg=BG_BOTTOM)
        c.create_window(20, 106, anchor="nw", window=cont, width=1260, height=H - 116)
        sc = tk.Canvas(cont, bg=BG_BOTTOM, highlightthickness=0)
        sb = ttk.Scrollbar(cont, orient="vertical", command=sc.yview)
        sc.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        sc.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(sc, bg=BG_BOTTOM)
        sc.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))

        def wheel(delta):
            if self.current == "deck":
                sc.yview_scroll(-1 if delta > 0 else 1, "units")
        self.root.bind_all("<MouseWheel>", lambda e: wheel(e.delta))
        self.root.bind_all("<Button-4>", lambda e: wheel(1))
        self.root.bind_all("<Button-5>", lambda e: wheel(-1))

        order = sorted(CARDS.values(), key=lambda d: (RORDER.index(d["rarity"]), d["kind"] != "install"))
        self.tiles = {}
        for i, d in enumerate(order):
            t = tk.Frame(inner, bg=BG_BOTTOM)
            t.grid(row=i // 7, column=i % 7, padx=8, pady=8)
            CardView(t, d["id"], 150, 210, bg=BG_BOTTOM, cmd=lambda cid=d["id"]: self.show_zoom(cid)).pack()
            ctl = tk.Frame(t, bg=BG_BOTTOM)
            ctl.pack(pady=(6, 0))
            minus = RBtn(ctl, "−", lambda cid=d["id"]: self.deck_change(cid, -1), w=40, h=30, r=12,
                         bg=BG_BOTTOM, theme="blue", font=(FONT, 12, "bold"))
            minus.pack(side="left")
            cnt = tk.Label(ctl, text="0", font=(FONT, 13, "bold"), bg=BG_BOTTOM, fg=TEXT_DARK, width=3)
            cnt.pack(side="left")
            plus = RBtn(ctl, "+", lambda cid=d["id"]: self.deck_change(cid, 1), w=40, h=30, r=12,
                        bg=BG_BOTTOM, theme="primary", font=(FONT, 12, "bold"))
            plus.pack(side="left")
            self.tiles[d["id"]] = (cnt, minus, plus)

    def update_deck_ui(self):
        n = len(self.deck)
        rc = rarity_counts(self.deck)
        full = n >= CFG["deck_max"]
        valid = CFG["deck_min"] <= n <= CFG["deck_max"]
        self.deck_total.config(text=f"{n}장 ({CFG['deck_min']}~{CFG['deck_max']}) · 같은 카드 최대 {CFG['max_copies']}장",
                               fg=SUCCESS_TXT if valid else FAIL_TXT)
        for r in RORDER:
            lim = LIMIT[r]
            self.meters[r].config(text=f"{RN[r]} {rc[r]}/{'∞' if lim >= 10 ** 9 else lim}")
        for cid, (cnt, minus, plus) in self.tiles.items():
            k = self.deck.count(cid)
            cnt.config(text=str(k))
            minus.enable(k > 0)
            plus.enable(not full and k < CFG["max_copies"] and rc[CARDS[cid]["rarity"]] < LIMIT[CARDS[cid]["rarity"]])

    def deck_change(self, cid, d):
        if d > 0:
            self.deck.append(cid)
        elif cid in self.deck:
            self.deck.remove(cid)
        save_deck(self.deck)
        self.update_deck_ui()

    def deck_auto(self):
        self.deck = auto_deck()
        save_deck(self.deck)
        self.update_deck_ui()

    def deck_clear(self):
        self.deck = []
        save_deck(self.deck)
        self.update_deck_ui()

    # ── 온라인 ──
    def build_online(self):
        f, c = self.make_screen("online")
        c.create_text(W / 2, 42, text="🌐 온라인 대전", font=(FONT, 26, "bold"), fill=TEXT_DARK)
        p = panel(c, W / 2 - 300, 76, 600, 560, r=26, pad=22)
        lab = dict(bg=CARD_BG, fg=TEXT_DARK)
        muted = dict(font=(FONT, 10), bg=CARD_BG, fg=TEXT_MUTED, justify="left")
        tk.Label(p, text="서버 주소", font=(FONT, 12, "bold"), **lab).pack(anchor="w")
        self.server_entry = tk.Entry(p, width=30, font=(FONT, 12), bd=2, relief="solid")
        self.server_entry.insert(0, load_server())
        self.server_entry.pack(anchor="w", pady=(4, 2))
        tk.Label(p, text="relay_server.py 를 켠 컴퓨터의 주소:포트 (친구와 같은 서버여야 해요. 한 번 적으면 저장돼요)", **muted).pack(anchor="w")
        tk.Frame(p, bg=NEUTRAL_BD, height=2).pack(fill="x", pady=12)
        tk.Label(p, text="방 만들기", font=(FONT, 16, "bold"), **lab).pack(anchor="w")
        tk.Label(p, text="5자리 방 번호가 만들어져요. 번호를 친구에게 알려 주세요.", **muted).pack(anchor="w")
        RBtn(p, "방 만들기", self.create_room, w=150, h=42, theme="primary").pack(anchor="w", pady=10)
        tk.Frame(p, bg=NEUTRAL_BD, height=2).pack(fill="x", pady=6)
        tk.Label(p, text="방 참가", font=(FONT, 16, "bold"), **lab).pack(anchor="w")
        tk.Label(p, text="친구가 알려 준 5자리 방 번호를 입력하세요.", **muted).pack(anchor="w")
        row2 = tk.Frame(p, bg=CARD_BG)
        row2.pack(anchor="w", pady=10)
        ok5 = self.root.register(lambda v: v == "" or (v.isdigit() and len(v) <= 5))
        self.join_code = tk.Entry(row2, width=7, font=(FONT, 22, "bold"), bd=2, relief="solid", justify="center",
                                  validate="key", validatecommand=(ok5, "%P"))
        self.join_code.pack(side="left", padx=(0, 10))
        self.join_code.bind("<Return>", lambda e: self.start_join())
        RBtn(row2, "참가", self.start_join, w=90, h=44, theme="blue").pack(side="left")
        self.on_status = tk.Label(p, text="", font=(FONT, 11), bg=NEUTRAL_BG, fg=TEXT_DARK, wraplength=520,
                                  justify="left", padx=12, pady=12)
        self.on_status.pack(fill="x", pady=(10, 8))
        RBtn(p, "← 메뉴", self.leave, w=110, h=40, theme="tan").pack(anchor="w", pady=(6, 0))

    def set_online_status(self, text, bad=False):
        self.on_status.config(text=text, bg=FAIL_BG if bad else NEUTRAL_BG)

    def server_addr(self):
        try:
            srv = parse_server(self.server_entry.get())
        except ValueError as e:
            self.set_online_status(str(e), True)
            return None
        save_server(self.server_entry.get().strip())
        return srv

    def create_room(self):
        srv = self.server_addr()
        if srv:
            self.leave_net()
            self.net = Net()
            self.net.create(srv)
            self.set_online_status("서버에 연결하는 중…")

    def start_join(self):
        code = self.join_code.get().strip()
        if not (len(code) == 5 and code.isdigit()):
            self.set_online_status("방 번호는 5자리 숫자예요 (예: 73945)", True)
            return
        srv = self.server_addr()
        if srv:
            self.leave_net()
            self.net, self.room_code = Net(), code
            self.net.join(srv, code)
            self.set_online_status("방에 들어가는 중…")

    # ── 대기실: 서로 덱을 확인·변경하고 둘 다 '준비완료'를 누르면 시작 ──
    def build_lobby(self):
        f, c = self.make_screen("lobby")
        c.create_text(W / 2, 38, text="🎮 대기실", font=(FONT, 28, "bold"), fill=TEXT_DARK)
        top = panel(c, W / 2 - 380, 66, 760, 118, r=24, pad=14)
        row = tk.Frame(top, bg=CARD_BG)
        row.pack(expand=True)
        tk.Label(row, text="방 번호", font=(FONT, 12, "bold"), bg=CARD_BG, fg=TEXT_MUTED).pack(side="left", padx=(0, 14))
        self.lb_code = tk.Label(row, text="-----", font=(FONT, 46, "bold"), bg=CARD_BG, fg=PRIMARY)
        self.lb_code.pack(side="left")
        RBtn(row, "📋 복사", self.copy_room_code, w=100, h=40, theme="teal").pack(side="left", padx=(16, 0))
        self.lb = {}
        for who, x in (("me", W / 2 - 380), ("op", W / 2 + 10)):
            pn = panel(c, x, 200, 370, 270, r=22, pad=16)
            w = {"title": tk.Label(pn, font=(FONT, 16, "bold"), bg=CARD_BG, fg=TEXT_DARK)}
            w["title"].pack(anchor="w")
            w["chip"] = tk.Label(pn, font=(FONT, 12, "bold"), padx=14, pady=6)
            w["chip"].pack(anchor="w", pady=(10, 6))
            w["deck"] = tk.Label(pn, font=(FONT, 11), bg=CARD_BG, justify="left", wraplength=330)
            w["deck"].pack(anchor="w")
            if who == "me":
                bt = tk.Frame(pn, bg=CARD_BG)
                bt.pack(anchor="w", pady=(18, 0))
                RBtn(bt, "🃏 덱 편집", self.lobby_edit_deck, w=130, h=46, theme="teal").pack(side="left")
                w["ready"] = RBtn(bt, "준비완료", self.toggle_ready, w=150, h=46, theme="primary", font=(FONT, 12, "bold"))
                w["ready"].pack(side="left", padx=(10, 0))
            self.lb[who] = w
        bot = panel(c, W / 2 - 380, 486, 760, 130, r=22, pad=14)
        self.lb_msg = tk.Label(bot, font=(FONT, 12, "bold"), bg=CARD_BG, fg=TEXT_DARK, wraplength=700)
        self.lb_msg.pack(pady=(2, 10))
        RBtn(bot, "나가기", self.leave, w=110, h=40, theme="tan").pack()

    def copy_room_code(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.room_code)
        self.lb_msg.config(text=f"방 번호 {self.room_code} 를 복사했어요", fg=SUCCESS_TXT)

    def lobby_edit_deck(self):
        self.my_ready = False                   # 덱을 고치는 동안은 준비 해제
        self.send_lob()
        self.open_deck("lobby")

    def open_deck(self, back):
        self.deck_back = back
        self.show("deck")

    def send_lob(self):
        self.lob_deck = list(self.deck)
        if self.net and self.net.role:
            self.net.send({"t": "lob", "deck": self.deck, "ready": self.my_ready})

    def lobby_sync(self):
        """대기실이 열릴 때: 덱이 바뀌었으면 준비 해제, 내 상태를 상대에게 알려요"""
        if self.lob_deck is not None and list(self.deck) != self.lob_deck:
            self.my_ready = False
        self.send_lob()
        self.lobby_refresh()

    def lobby_refresh(self):
        me, op = self.lb["me"], self.lb["op"]
        host = bool(self.net and self.net.role == "host")
        self.lb_code.config(text=self.room_code or "-----")
        chip_ok = dict(bg="#D9F5E3", fg=SUCCESS_TXT)
        chip_no = dict(bg=NEUTRAL_BG, fg=TEXT_MUTED)
        err = validate_deck(self.deck)
        me["title"].config(text=f"👤 나 ({'방장' if host else '참가자'})")
        me["chip"].config(text="✅ 준비완료" if self.my_ready else "⏳ 준비 중", **(chip_ok if self.my_ready else chip_no))
        me["deck"].config(text=f"덱 {len(self.deck)}장 ✔" if not err else f"덱 {len(self.deck)}장 — {err}",
                          fg=SUCCESS_TXT if not err else FAIL_TXT)
        me["ready"].set_text("준비 취소" if self.my_ready else "준비완료")
        op["title"].config(text=f"👤 상대 ({'참가자' if host else '방장'})")
        if not self.opp_here:
            op["chip"].config(text="⌛ 기다리는 중", **chip_no)
            op["deck"].config(text="상대가 들어오면 여기에 표시돼요", fg=TEXT_MUTED)
            msg, bad = "친구에게 방 번호를 알려 주세요" if host else "연결 중…", False
        else:
            op["chip"].config(text="✅ 준비완료" if self.opp_ready else "⏳ 준비 중", **(chip_ok if self.opp_ready else chip_no))
            if self.opp_err:
                op["deck"].config(text=f"덱이 올바르지 않아요: {self.opp_err}", fg=FAIL_TXT)
            elif self.opp_deck is None:
                op["deck"].config(text="덱 정보를 받는 중…", fg=TEXT_MUTED)
            else:
                op["deck"].config(text=f"덱 {len(self.opp_deck or [])}장 ✔", fg=SUCCESS_TXT)
            if self.my_ready and self.opp_ready:
                msg, bad = "둘 다 준비완료! 곧 시작해요…", False
            elif self.my_ready:
                msg, bad = "상대가 준비하기를 기다리는 중…", False
            else:
                msg, bad = "덱을 확인하고 '준비완료'를 누르세요. 둘 다 누르면 시작해요", False
        self.lb_msg.config(text=msg, fg=FAIL_TXT if bad else TEXT_DARK)

    def toggle_ready(self):
        if not self.my_ready:
            err = validate_deck(self.deck)
            if err:
                self.lb_msg.config(text=f"덱을 먼저 고쳐 주세요: {err}", fg=FAIL_TXT)
                return
            if not self.opp_here:
                self.lb_msg.config(text="상대가 들어온 뒤에 준비할 수 있어요", fg=FAIL_TXT)
                return
        self.my_ready = not self.my_ready
        self.send_lob()
        self.lobby_refresh()
        self.try_start()

    def try_start(self):
        """(방장) 둘 다 준비되면 게임 시작"""
        if (self.net and self.net.role == "host" and not self.g and self.my_ready and self.opp_ready
                and self.opp_deck and not validate_deck(self.deck)):
            self.reset_game_state()
            self.mode, self.guest_arena, self.g = "host", True, Game(self.deck, self.opp_deck)
            self.net.ready = True
            self.my_ready = self.opp_ready = False
            self.show("battle")
            self.after_change()

    def handle_lob(self, m):
        if self.mode in ("host", "guest"):
            if self.view and self.view["o"]:                 # 끝난 게임 화면이면 상대와 함께 대기실로
                self.back_to_lobby()
            else:
                return                                        # 진행 중에는 무시
        err = validate_deck(m.get("deck"))
        self.opp_here, self.opp_deck, self.opp_err = True, None if err else list(m["deck"]), err
        self.opp_ready = bool(m.get("ready")) and not err
        self.lobby_refresh()
        self.try_start()

    def back_to_lobby(self):
        """게임이 끝난 뒤 같은 상대와 다시 하려고 대기실로"""
        if not self.net:
            return self.leave()
        self.reset_game_state()
        self.net.ready = False
        self.over_f.place_forget()
        self.my_ready = self.opp_ready = False
        self.show("lobby")

    def reset_online(self, msg="", bad=False):
        self.set_online_status(msg, bad)

    def reset_lobby_state(self):
        self.room_code, self.my_ready, self.opp_ready, self.opp_here = "", False, False, False
        self.opp_deck, self.opp_err, self.lob_deck = None, None, None

    def leave_net(self):
        if self.net:
            self.net.close()
            self.net = None

    # ── 전투 화면 ──
    def build_battle(self):
        f, c = self.make_screen("battle")
        self.battle_f = f
        # 상대 영역
        po = panel(c, 20, 8, 1260, 150, r=18, pad=10)
        r1 = tk.Frame(po, bg=CARD_BG)
        r1.pack(fill="x")
        tk.Label(r1, text="👤 상대", font=(FONT, 15, "bold"), bg=CARD_BG, fg=TEXT_DARK).pack(side="left")
        self.opp_bar = HPBar(r1, w=340)
        self.opp_bar.pack(side="left", padx=12)
        self.opp_hp = tk.Label(r1, font=(FONT, 20, "bold"), bg=CARD_BG, fg=TEXT_DARK, width=3)
        self.opp_hp.pack(side="left")
        self.opp_info = tk.Label(r1, font=(FONT, 10), bg=CARD_BG, fg=TEXT_MUTED)
        self.opp_info.pack(side="right")
        self.opp_backs = tk.Canvas(r1, width=160, height=40, bg=CARD_BG, highlightthickness=0)
        self.opp_backs.pack(side="right", padx=14)
        tk.Label(po, text="상대 설치", font=(FONT, 9), bg=CARD_BG, fg=TEXT_MUTED).pack(anchor="w", pady=(4, 1))
        self.opp_field = tk.Frame(po, bg=CARD_BG, height=60)
        self.opp_field.pack(anchor="w", fill="x")
        self.opp_field.pack_propagate(False)

        # 중앙 (턴 + 로그)
        pm = panel(c, 20, 168, 1260, 84, r=18, pad=8, bg=NEUTRAL_BG)
        self.banner = tk.Label(pm, font=(FONT, 22, "bold"), bg=NEUTRAL_BG, fg=TEXT_DARK, width=10)
        self.banner.pack(side="left", padx=(8, 20))
        self.log_lbl = tk.Label(pm, font=(FONT, 10), bg=NEUTRAL_BG, fg=TEXT_DARK, justify="left", anchor="w")
        self.log_lbl.pack(side="left", fill="both", expand=True)

        # 내 영역
        pme = panel(c, 20, 262, 1260, 396, r=18, pad=10)
        r2 = tk.Frame(pme, bg=CARD_BG)
        r2.pack(fill="x")
        tk.Label(r2, text="🙂 나", font=(FONT, 15, "bold"), bg=CARD_BG, fg=TEXT_DARK).pack(side="left")
        self.me_bar = HPBar(r2, w=340)
        self.me_bar.pack(side="left", padx=12)
        self.me_hp = tk.Label(r2, font=(FONT, 20, "bold"), bg=CARD_BG, fg=TEXT_DARK, width=3)
        self.me_hp.pack(side="left")
        self.me_info = tk.Label(r2, font=(FONT, 10), bg=CARD_BG, fg=TEXT_MUTED)
        self.me_info.pack(side="right")
        tk.Label(pme, text="내 설치", font=(FONT, 9), bg=CARD_BG, fg=TEXT_MUTED).pack(anchor="w", pady=(4, 1))
        self.me_field = tk.Frame(pme, bg=CARD_BG, height=60)
        self.me_field.pack(anchor="w", fill="x")
        self.me_field.pack_propagate(False)
        self.hand_f = tk.Frame(pme, bg=CARD_BG, height=192)
        self.hand_f.pack(fill="x", pady=(6, 2))
        self.hand_f.pack_propagate(False)
        ar = tk.Frame(pme, bg=CARD_BG)
        ar.pack(fill="x", pady=(2, 0))
        self.use_btn = RBtn(ar, "사용하기", self.use_selected, w=150, h=42, r=16, font=(FONT, 12, "bold"))
        self.use_btn.pack(side="left")
        self.end_btn = RBtn(ar, "턴 넘기기", lambda: self.do_action({"a": "end"}), w=150, h=42, r=16,
                            theme="blue", font=(FONT, 12, "bold"))
        self.end_btn.pack(side="left", padx=10)
        self.zoom_btn = RBtn(ar, "🔍 자세히", self.zoom_selected, w=110, h=42, r=16, theme="teal", font=(FONT, 10, "bold"))
        self.zoom_btn.pack(side="left")
        RBtn(ar, "나가기", self.leave, w=90, h=42, r=16, theme="tan").pack(side="left", padx=(10, 0))
        self.snd_btn = RBtn(ar, "🔊 소리 켬", self.toggle_sound, w=110, h=42, r=16, theme="gray", font=(FONT, 9, "bold"))
        self.snd_btn.pack(side="left", padx=(10, 0))
        self.hint_lbl = tk.Label(ar, font=(FONT, 10), bg=CARD_BG, fg=TEXT_MUTED, wraplength=400, justify="left")
        self.hint_lbl.pack(side="left", padx=16)

        # 게임 종료 팝업
        self.over_f = tk.Frame(f, bg=CARD_BG, highlightbackground=TEXT_DARK, highlightthickness=3)
        self.over_title = tk.Label(self.over_f, font=(FONT, 40, "bold"), bg=CARD_BG, padx=60, pady=10)
        self.over_title.pack(pady=(24, 4))
        self.over_sub = tk.Label(self.over_f, font=(FONT, 12), bg=CARD_BG, fg=TEXT_MUTED)
        self.over_sub.pack()
        ob = tk.Frame(self.over_f, bg=CARD_BG)
        ob.pack(pady=22)
        self.again_btn = RBtn(ob, "다시 하기", self.start_ai, w=130, h=44, theme="primary")
        self.again_btn.pack(side="left", padx=6)
        self.lobby_btn = RBtn(ob, "대기실로", self.back_to_lobby, w=130, h=44, theme="teal")
        self.over_menu_btn = RBtn(ob, "메뉴로", self.leave, w=130, h=44, theme="blue")
        self.over_menu_btn.pack(side="left", padx=6)

    def set_msg(self, text, bad=True):
        self.hint_lbl.config(text=text, fg=FAIL_TXT if bad else TEXT_MUTED)
        if self.msg_job:
            self.root.after_cancel(self.msg_job)
        self.msg_job = self.root.after(2800, self.refresh_hint)

    def refresh_hint(self):
        self.msg_job = None
        v = self.view
        if not v:
            return
        mt = v["t"] == 1 and not v["o"]
        has_inst = any(CARDS[x]["kind"] == "instant" for x in v["me"]["hand"])
        if v["o"]:
            txt = ""
        elif not mt:
            txt = "상대 차례예요…"
        elif v["me"].get("in"):
            txt = "이번 턴 설치는 이미 했어요 (턴당 1장). 즉발 카드를 쓰거나 턴을 넘기세요."
        elif has_inst:
            txt = "설치 카드는 턴당 1장 먼저 깔 수 있어요. 즉발 카드를 하나 쓰면 턴이 끝나요."
        else:
            txt = "즉발 카드가 없어요. 설치를 마쳤다면 턴을 넘기세요."
        self.hint_lbl.config(text=txt, fg=TEXT_MUTED)

    def flash_hp(self, lbl, delta):
        lbl.config(fg=FAIL_TXT if delta < 0 else SUCCESS_TXT)
        self.root.after(700, lambda: lbl.config(fg=TEXT_DARK))

    def refresh(self):
        v = self.view
        if not v:
            return
        mx = CFG["max_hp"]
        mt = v["t"] == 1 and not v["o"]
        for who, bar, lbl in (("op", self.opp_bar, self.opp_hp), ("me", self.me_bar, self.me_hp)):
            hp = v[who]["hp"]
            bar.set(max(hp, 0), mx)
            lbl.config(text=str(max(hp, 0)))
            if self.prev_hp and hp != self.prev_hp[who]:
                self.flash_hp(lbl, hp - self.prev_hp[who])
        self.prev_hp = {"op": v["op"]["hp"], "me": v["me"]["hp"]}

        def stat(d):
            t = ""
            if d.get("ps"):
                t += f"   ☠ 중독 {d['ps']}턴"
            if d.get("sh"):
                t += f"   🛡 보호막 {d['sh']}"
            return t
        self.opp_info.config(text=f"손패 {v['op']['hn']}장 · 덱 {v['op']['dn']}장" + stat(v["op"]))
        self.me_info.config(text=f"덱 {v['me']['dn']}장" + stat(v["me"]))
        self.opp_backs.delete("all")
        for i in range(min(v["op"]["hn"], 10)):
            x = 4 + i * 15
            self.opp_backs.create_polygon(rrp(x, 4, x + 22, 36, 4), smooth=True, fill="#E8C07A", outline="#C9A876")

        for frame, f in ((self.opp_field, v["op"]["f"]), (self.me_field, v["me"]["f"])):
            for w in frame.winfo_children():
                w.destroy()
            if not f:
                tk.Label(frame, text="없음", font=(FONT, 9), bg=CARD_BG, fg=TEXT_MUTED).pack(side="left", pady=14)
            for item in f:
                cid, left = item[0], item[1]
                hp = item[2] if len(item) > 2 else None
                field_chip(frame, cid, left, on_click=lambda cid=cid: self.show_zoom(cid), hp=hp).pack(side="left", padx=(0, 6))

        self.banner.config(
            text=("승리!" if v["w"] == 1 else "패배…" if v["w"] == 0 else "무승부") if v["o"]
            else ("내 차례" if mt else "상대 차례"),
            fg=SUCCESS_TXT if (mt or v["w"] == 1) else (FAIL_TXT if v["w"] == 0 else TEXT_MUTED))
        names = {-1: "", 0: "나: ", 1: "상대: "}
        self.log_lbl.config(text="\n".join(names[w] + t for w, t in v["log"][-3:]))

        for w in self.hand_f.winfo_children():
            w.destroy()
        hand = v["me"]["hand"]
        if self.sel_id not in hand:
            self.sel_id = None
        sel_idx = hand.index(self.sel_id) if self.sel_id else None
        n = max(len(hand), 1)
        cw = int(max(96, min(120, (1200 - 8 * (n - 1)) / n)))
        for i, cid in enumerate(hand):
            cv = CardView(self.hand_f, cid, cw, int(cw * 1.4), selected=(i == sel_idx),
                          cmd=lambda cid=cid: self.select(cid), dbl=lambda cid=cid: self.use(cid),
                          rcmd=lambda cid=cid: self.show_zoom(cid))
            cv.pack(side="left", padx=3, pady=(0, 18) if i == sel_idx else (18, 0), anchor="n")
        if not hand:
            tk.Label(self.hand_f, text="손패가 비었어요", font=(FONT, 11), bg=CARD_BG, fg=TEXT_MUTED).pack(pady=50)

        has_inst = any(CARDS[x]["kind"] == "instant" for x in hand)
        sel_kind = CARDS[self.sel_id]["kind"] if self.sel_id else None
        self.use_btn.set_text("설치하기" if sel_kind == "install" else "사용하기")
        used_inst = bool(v["me"].get("in"))
        self.use_btn.enable(mt and self.sel_id is not None and not (sel_kind == "install" and used_inst))
        self.end_btn.enable(mt and not has_inst)
        self.zoom_btn.enable(self.sel_id is not None)
        if self.msg_job is None:
            self.refresh_hint()

        if v["o"]:
            self.over_title.config(text="승리! 🎉" if v["w"] == 1 else "패배…" if v["w"] == 0 else "무승부",
                                   fg=SUCCESS_TXT if v["w"] == 1 else FAIL_TXT if v["w"] == 0 else TEXT_DARK)
            self.over_sub.config(text="상대의 체력을 모두 깎았어요." if v["w"] == 1 else "체력이 0이 되었어요." if v["w"] == 0 else "둘 다 쓰러졌어요.")
            self.again_btn.pack_forget()
            self.lobby_btn.pack_forget()
            if self.mode == "ai":
                self.again_btn.pack(side="left", padx=6, before=self.over_menu_btn)
            elif self.net:
                self.lobby_btn.pack(side="left", padx=6, before=self.over_menu_btn)
            self.over_f.place(relx=0.5, rely=0.45, anchor="center")
            self.over_f.lift()
        else:
            self.over_f.place_forget()

    # ── 효과 / 소리 ──
    def toggle_sound(self):
        self.sound.on = not self.sound.on
        self.snd_btn.set_text("🔊 소리 켬" if self.sound.on else "🔇 소리 끔")

    def fx_after(self, ms, fn):
        tok = self.fx_token

        def run():
            if tok != self.fx_token:
                return
            try:
                fn()
            except tk.TclError:
                pass
        self.root.after(ms, run)

    def kill(self, w):
        try:
            w.destroy()
        except tk.TclError:
            pass
        if w in self.fx_widgets:
            self.fx_widgets.remove(w)

    def fx_widget(self, w, ms):
        self.fx_widgets.append(w)
        self.fx_after(ms, lambda: self.kill(w))

    def clear_fx(self):
        self.fx_token += 1
        for w in list(self.fx_widgets):
            self.kill(w)
        try:
            self.battle_f.place_configure(x=0)
            self.banner.config(bg=NEUTRAL_BG)
            self.banner.master.config(bg=NEUTRAL_BG)
        except (tk.TclError, AttributeError):
            pass

    def play_events(self, old, v):
        """카드 사용 → 체력 변화 → 턴 전환 순서로 시간차를 두고 보여 줌"""
        t = 0
        if v.get("pd"):                      # 아레나가 열리는 중: 아레나 안내가 대신 보여 줘요
            return
        new_action = old is None or v["q"] != old["q"]
        lp = v.get("lp")
        if old is not None and new_action and lp and lp[1] in CARDS and old.get("lp") != lp:
            who, cid = lp
            if CARDS[cid]["rarity"] == "legend":
                self.legend_fx(cid, who)
                t = 1900
            else:
                self.sound.play("play")
                if who == 1:
                    self.card_popup(cid, who)
                    t = 1100
                else:
                    t = 250
        if old is not None and new_action:
            self.fx_after(t, lambda o=old, n=v: self.hp_fx(o, n))
            t += 650
        if v["o"]:
            if old is None or not old["o"]:
                self.fx_after(t, lambda: self.sound.play("win" if v["w"] == 1 else "lose" if v["w"] == 0 else "turn_opp"))
        elif old is None or old["t"] != v["t"]:
            self.fx_after(t, lambda m=(v["t"] == 1): self.turn_fx(m))

    def turn_fx(self, mine):
        self.sound.play("turn_me" if mine else "turn_opp")
        b = tk.Label(self.battle_f, text="⚔  내 차례!" if mine else "⏳  상대 차례…", font=(FONT, 38, "bold"),
                     bg=SUCCESS_TXT if mine else "#5B6B8C", fg="#FFF", padx=56, pady=14,
                     highlightthickness=4, highlightbackground="#FFF")
        b.place(relx=0.5, rely=0.30, anchor="center")
        b.lift()
        for i in range(1, 5):   # 위에서 내려오며 등장
            self.fx_after(i * 30, lambda i=i: b.place_configure(rely=0.30 + 0.025 * i))
        self.fx_widget(b, 1100 if mine else 850)
        if mine:                # 상단 '내 차례' 표시도 깜빡임
            for i in range(4):
                self.fx_after(i * 170, lambda i=i: self.banner.master.config(bg=SUCCESS_BG if i % 2 == 0 else NEUTRAL_BG))
                self.fx_after(i * 170, lambda i=i: self.banner.config(bg=SUCCESS_BG if i % 2 == 0 else NEUTRAL_BG))

    def card_popup(self, cid, who, legend=False):
        d = CARDS[cid]
        gold = "#C8921E"
        bg = "#FFF8DC" if legend else CARD_BG
        f = tk.Frame(self.battle_f, bg=bg, highlightthickness=6 if legend else 3,
                     highlightbackground=gold if legend else RC[d["rarity"]])
        who_txt = "내가 사용!" if who == 0 else "상대가 사용!"
        tk.Label(f, text=("✨ 레전드 카드 ✨\n" if legend else "") + who_txt,
                 font=(FONT, 16 if legend else 12, "bold"), bg=bg, fg=gold if legend else TEXT_DARK
                 ).pack(padx=40, pady=(12, 4))
        cw = 190 if legend else 140
        CardView(f, cid, cw, int(cw * 1.4), bg=bg).pack(padx=40, pady=(0, 14))
        if legend:   # 가장자리 여백에 반짝이
            for _ in range(14):
                x = random.choice([random.uniform(0.0, 0.05), random.uniform(0.93, 0.98)])
                tk.Label(f, text=random.choice(["✨", "✦", "★"]), font=(FONT, random.randint(13, 20)),
                         bg=bg, fg=gold, padx=0, pady=0).place(relx=x, rely=random.uniform(0.02, 0.92))
        f.place(relx=0.5, rely=0.46, anchor="center")
        f.lift()
        self.fx_widget(f, 1800 if legend else 1000)

    def legend_fx(self, cid, who):
        self.sound.play("legend")
        flash = tk.Frame(self.battle_f, bg="#FFF3C4")        # 황금빛 번쩍임
        flash.place(x=0, y=0, relwidth=1, relheight=1)
        flash.lift()
        self.fx_widget(flash, 170)
        self.fx_after(110, lambda: self.card_popup(cid, who, legend=True))
        self.fx_after(110, lambda: self.shake_fx(10))

    def shake_fx(self, amp=8):
        for i, dx in enumerate([-1, 1, -.7, .7, -.4, .4, 0]):
            self.fx_after(i * 28, lambda dx=dx: self.battle_f.place_configure(x=int(dx * amp)))

    def float_num(self, lbl, diff):
        x = lbl.winfo_rootx() - self.battle_f.winfo_rootx() + 70
        y = lbl.winfo_rooty() - self.battle_f.winfo_rooty() + 2
        w = tk.Label(self.battle_f, text=f"{diff:+d}", font=(FONT, 30, "bold"),
                     fg=FAIL_TXT if diff < 0 else SUCCESS_TXT, bg=CARD_BG)
        w.place(x=x, y=y)
        w.lift()
        self.fx_widgets.append(w)

        def step(i=0):
            if i >= 18:
                self.kill(w)
                return
            w.place_configure(y=y + i * 3)
            self.fx_after(32, lambda: step(i + 1))
        step()

    def hp_fx(self, old, new):
        diffs = {s: new[s]["hp"] - old[s]["hp"] for s in ("me", "op")}
        for side, lbl in (("op", self.opp_hp), ("me", self.me_hp)):
            if diffs[side]:
                self.float_num(lbl, diffs[side])
        hurt, healed = min(diffs.values()) < 0, max(diffs.values()) > 0
        if hurt:
            self.sound.play("hit")
            if min(diffs.values()) <= -4:
                self.shake_fx(8)
        if healed:
            if hurt:
                self.fx_after(320, lambda: self.sound.play("heal"))
            else:
                self.sound.play("heal")

    # ── 카드 확대 보기 ──
    def zoom_selected(self):
        if self.sel_id:
            self.show_zoom(self.sel_id)

    def show_zoom(self, cid):
        """카드를 크게 보여 주고, 자세한 규칙 설명을 함께 보여 줌 (Esc / 바깥 클릭 / 닫기 버튼으로 닫기)"""
        self.close_zoom()
        c = CARDS[cid]
        rc = RC[c["rarity"]]
        z = tk.Frame(self.root, bg="#2B2118")
        z.place(x=0, y=0, relwidth=1, relheight=1)
        z.lift()
        z.bind("<Button-1>", lambda e: self.close_zoom() if e.widget is z else None)
        box = tk.Frame(z, bg=CARD_BG, highlightthickness=5, highlightbackground=rc)
        box.place(relx=0.5, rely=0.5, anchor="center")
        CardView(box, cid, 290, 406, bg=CARD_BG).grid(row=0, column=0, padx=(26, 14), pady=26, sticky="n")
        right = tk.Frame(box, bg=CARD_BG)
        right.grid(row=0, column=1, padx=(14, 26), pady=26, sticky="n")
        wrap = 470
        tk.Label(right, text=f"{glyph(c)}  {c['name']}", font=(FONT, 26, "bold"), bg=CARD_BG, fg=TEXT_DARK).pack(anchor="w")
        tk.Label(right, text=f"{RN[c['rarity']]} · {KN[c['kind']]} 카드", font=(FONT, 12, "bold"), bg=CARD_BG,
                 fg=rc).pack(anchor="w", pady=(0, 10))
        tk.Label(right, text=describe(c), font=(FONT, 15, "bold"), bg=NEUTRAL_BG, fg=TEXT_DARK, wraplength=wrap - 24,
                 justify="left", padx=12, pady=10).pack(fill="x")
        tk.Label(right, text="자세한 규칙", font=(FONT, 11, "bold"), bg=CARD_BG, fg=TEXT_MUTED).pack(anchor="w", pady=(14, 4))
        for note in card_notes(c):
            tk.Label(right, text="•  " + note, font=(FONT, 11), bg=CARD_BG, fg=TEXT_DARK, wraplength=wrap,
                     justify="left").pack(anchor="w", pady=2)
        RBtn(right, "닫기 (Esc)", self.close_zoom, w=130, h=40, theme="blue").pack(anchor="w", pady=(16, 0))
        self.zoom_f = z

    def close_zoom(self):
        z = getattr(self, "zoom_f", None)
        if z is not None:
            try:
                z.destroy()
            except tk.TclError:
                pass
        self.zoom_f = None

    # ── 행동 ──
    def select(self, cid):
        self.sel_id = None if self.sel_id == cid else cid
        self.refresh()

    def use(self, cid):
        self.sel_id = cid
        self.do_action({"a": "play", "id": cid})

    def use_selected(self):
        if self.sel_id:
            self.do_action({"a": "play", "id": self.sel_id})

    def do_action(self, a):
        if not self.view or self.view["o"]:
            return
        if self.view["t"] != 1:
            self.set_msg("지금은 상대 차례예요.")
            return
        if self.mode == "guest":
            self.net.send(a)
            self.sel_id = None
            return
        ok, msg = self.g.act(0, a)
        if not ok:
            self.set_msg(msg)
        else:
            self.sel_id = None
        self.after_change()

    def apply_view(self, v):
        """새 화면 데이터를 반영하고, 바뀐 내용에 맞춰 효과/소리를 재생"""
        old = self.view
        if old is not None and v["q"] != old["q"]:
            self.clear_fx()          # 이전 효과가 남아 있어도 최신 상황이 우선
        self.view = v
        self.refresh()
        self.play_events(old, v)

    def after_change(self):
        self.apply_view(self.g.view_for(0))
        pend = bool(self.g.pending)
        if self.mode == "host" and self.net and self.net.ready and (not pend or self.guest_arena):
            self.net.send({"t": "st", "v": self.g.view_for(1), "n": None})
        if pend:
            if self.ar is None:
                self.start_arena_local()
        elif self.mode == "ai" and not self.g.over and self.g.turn == 1 and self.ai_job is None:
            self.ai_job = self.root.after(900, self.ai_step)

    def ai_step(self):
        self.ai_job = None
        if self.mode != "ai" or not self.g or self.g.over or self.g.turn != 1:
            return
        self.g.act(1, ai_choose(self.g, 1))
        self.after_change()

    # ══════════ 실시간 아레나 ══════════
    def key_name(self, e):
        k = e.keysym
        if k in ("Up", "Down", "Left", "Right"):
            return k
        if len(k) == 1 and k.lower() in "wasd":
            return k.lower()
        if k in HANGUL_KEYS:
            return HANGUL_KEYS[k]
        if os.name == "nt":
            n = {87: "w", 65: "a", 83: "s", 68: "d"}.get(getattr(e, "keycode", 0))
            if n:
                return n
        if len(k) == 1 and k in "123456789":
            return k
        if k == "space":
            return "space"
        return None

    def on_key_down(self, e):
        n = self.key_name(e)
        if not n:
            return
        job = self.key_jobs.pop(n, None)
        if job:
            self.root.after_cancel(job)
        if n == "space":
            self.click_count += 1                                  # 스페이스 = 클릭 (칼싸움 베기 등)
            return
        self.keys.add(n)
        if n.isdigit():
            self.arena_pick(int(n) - 1)

    def on_key_up(self, e):
        n = self.key_name(e)
        if not n:
            return
        job = self.key_jobs.pop(n, None)
        if job:
            self.root.after_cancel(job)
        # 리눅스의 키 반복(릴리즈+프레스 쌍)을 걸러 내기 위해 잠깐 기다렸다가 뗀 걸로 처리
        self.key_jobs[n] = self.root.after(40, lambda: (self.keys.discard(n), self.key_jobs.pop(n, None)))

    def move_vec(self):
        k = self.keys
        ix = (("d" in k) or ("Right" in k)) - (("a" in k) or ("Left" in k))
        iy = (("s" in k) or ("Down" in k)) - (("w" in k) or ("Up" in k))
        return int(ix), int(iy)

    @staticmethod
    def pick_rects(n):
        S = AR.SIZE
        w = min(100.0, (S - 40) / n - 12)
        h, gap = 110.0, 12.0
        total = n * w + (n - 1) * gap
        x0, y1 = (S - total) / 2, S / 2 - h / 2 + 10
        return [(x0 + i * (w + gap), y1, x0 + i * (w + gap) + w, y1 + h) for i in range(n)]

    def on_arena_motion(self, e):
        self.mouse = (max(0, min(AR.SIZE, e.x)), max(0, min(AR.SIZE, e.y)))

    def on_arena_click(self, e):
        ar = self.ar
        if not ar or ar["phase"] != "run":
            return
        if ar["spec"]["mode"] == "pick":
            for i, (x1, y1, x2, y2) in enumerate(self.pick_rects(ar["spec"]["n"])):
                if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                    self.arena_pick(i)
        else:
            self.click_count += 1

    def arena_pick(self, idx):
        ar = self.ar
        if not ar or ar["phase"] != "run" or ar["spec"]["mode"] != "pick" or ar["me_att"]:
            return
        if not 0 <= idx < ar["spec"]["n"]:
            return
        if ar["kind"] == "host":
            ar["sim"].pick(idx)
        elif self.pick_sent is None:
            self.pick_sent = idx

    def build_arena_ui(self, pd_cid, me_att, spec, mods):
        c = CARDS[pd_cid]
        title, att_txt, def_txt = AR.help_for(spec)
        f = tk.Frame(self.root, bg=ARENA_BG)
        f.place(x=0, y=0, relwidth=1, relheight=1)
        f.lift()
        self.root.focus_force()
        tk.Label(f, text=f"{glyph(c)}  {c['name']}  —  {title}", font=(FONT, 18, "bold"), bg=ARENA_BG,
                 fg="#FFD166").place(relx=0.5, y=12, anchor="n")
        cv = tk.Canvas(f, width=AR.SIZE, height=AR.SIZE, bg="#000", highlightthickness=3, highlightbackground="#2A2A38")
        cv.place(x=350, y=54)
        cv.bind("<Motion>", self.on_arena_motion)
        cv.bind("<Button-1>", self.on_arena_click)
        left = tk.Frame(f, bg=ARENA_BG)
        left.place(x=20, y=54, width=315, height=600)
        role = "⚔  당신은 공격하는 쪽" if me_att else "🏃  당신은 피하는 쪽"
        tk.Label(left, text=role, font=(FONT, 17, "bold"), bg=ARENA_BG, fg="#FF6B6B" if me_att else "#3DD6F5",
                 anchor="w").pack(fill="x", pady=(0, 8))
        tk.Label(left, text=att_txt if me_att else def_txt, font=(FONT, 12), bg=ARENA_BG, fg="#E6E6F0",
                 wraplength=300, justify="left", anchor="w").pack(fill="x")
        tk.Label(left, text=AR.ctrl_for(spec, me_att),
                 font=(FONT, 11, "bold"), bg=ARENA_BG, fg="#9AA0B5", wraplength=300, justify="left",
                 anchor="w").pack(fill="x", pady=(14, 0))
        eff = []
        if mods.get("dodge"):
            eff.append(f"🥾 피하는 쪽 이동속도 +{round(mods['dodge'] * 100)}%")
        if mods.get("shrink"):
            eff.append(f"🧥 피하는 쪽 몸 크기 -{round(mods['shrink'] * 100)}%")
        if mods.get("atk"):
            eff.append(f"🎯 공격 속도·범위 +{round(mods['atk'] * 100)}%")
        if mods.get("foe_slow"):
            eff.append(f"🕸 피하는 쪽 이동속도 -{round(mods['foe_slow'] * 100)}%")
        if mods.get("proj_slow"):
            eff.append(f"🌀 공격 속도 -{round(mods['proj_slow'] * 100)}%")
        if spec.get("twist"):
            eff.append(AR.TWIST_TXT.get(spec["twist"], "") + (f" ({spec['tw_at']:g}초 뒤부터)" if spec.get("tw_at") else ""))
        if spec.get("fog"):
            eff.append("🌑 어둠: 피하는 쪽 주변만 보여요")
        if eff:
            tk.Label(left, text="필드 효과", font=(FONT, 10, "bold"), bg=ARENA_BG, fg="#FFD166", anchor="w"
                     ).pack(fill="x", pady=(18, 2))
            for t in eff:
                tk.Label(left, text=t, font=(FONT, 11), bg=ARENA_BG, fg="#E6E6F0", anchor="w").pack(fill="x")
        right = tk.Frame(f, bg=ARENA_BG)
        right.place(x=965, y=54, width=315, height=600)
        lbl = {}
        for key, name in (("op", "상대"), ("me", "나")):
            tk.Label(right, text=name, font=(FONT, 12, "bold"), bg=ARENA_BG, fg="#E6E6F0", anchor="w").pack(fill="x", pady=(10, 0))
            row = tk.Frame(right, bg=ARENA_BG)
            row.pack(fill="x")
            bar = HPBar(row, bg=ARENA_BG, w=230, h=16)
            bar.pack(side="left")
            lbl[key + "_bar"] = bar
            lbl[key] = tk.Label(row, font=(FONT, 15, "bold"), bg=ARENA_BG, fg="#FFFFFF", width=3)
            lbl[key].pack(side="left", padx=6)
        tk.Label(right, text="누적 피해", font=(FONT, 11), bg=ARENA_BG, fg="#9AA0B5", anchor="w").pack(fill="x", pady=(30, 0))
        lbl["dmg"] = tk.Label(right, text="0", font=(FONT, 44, "bold"), bg=ARENA_BG, fg="#FF6B6B", anchor="w")
        lbl["dmg"].pack(fill="x")
        lbl["time"] = tk.Label(right, text="", font=(FONT, 12), bg=ARENA_BG, fg="#9AA0B5", anchor="w")
        lbl["time"].pack(fill="x", pady=(10, 0))
        return f, cv, lbl

    def _arena_common(self, kind, pd, me_att, sim):
        spec = pd["spec"]
        f, cv, lbl = self.build_arena_ui(pd["cid"], me_att, spec, pd["mods"])
        now = time.perf_counter()
        self.click_count, self.pick_sent, self.remote_in = 0, None, {}
        self.keys.clear()
        self.ar = {"kind": kind, "sim": sim, "cid": pd["cid"], "spec": spec, "me_att": me_att, "f": f, "cv": cv,
                   "lbl": lbl, "phase": "intro", "t0": now, "last": now, "acc": 0.0, "snap": None, "result": None,
                   "end_t": None, "lc": 0, "rc": 0, "sent": 0.0, "evbuf": [], "flash": 0.0, "info": 0.0,
                   "ai_att": None, "ai_def": None, "remote": False, "job": None}
        rects = self.pick_rects(spec["n"]) if spec["mode"] == "pick" else None
        self.ar["rend"] = ArenaRenderer(cv, spec, me_att, pd["cid"], rects)
        self.ar["lc"] = 0
        self.ar["lcache"] = {}
        self.sound.play("legend" if CARDS[pd["cid"]]["rarity"] == "legend" else "play")
        return self.ar

    def start_arena_local(self):
        """(AI 대전/방장) 엔진에 대기 중인 공격 → 아레나 열기"""
        pd = self.g.pending
        me_att = pd["pi"] == 0
        sim = AR.Arena(pd["spec"], pd["seed"], pd["mods"])
        ar = self._arena_common("host", pd, me_att, sim)
        remote = self.mode == "host" and self.guest_arena
        ar["remote"] = remote
        if not remote:                                  # 상대 역할은 AI가 조종해요
            if me_att:
                ar["ai_def"] = AR.AIDefender(sim, AI_SKILL, pd["seed"] + 2)
            else:
                ar["ai_att"] = AR.AIAttacker(sim, AI_SKILL, pd["seed"] + 1)
        self.sound_events = []
        ar["job"] = self.root.after(16, self.arena_tick)

    def start_arena_remote(self, pd):
        """(온라인 참가자) 방장이 돌리는 아레나를 받아서 보여 주고 입력만 보내요"""
        ar = self._arena_common("guest", pd, pd["a"] == 0, None)
        ar["job"] = self.root.after(16, self.arena_tick)

    def close_arena(self):
        ar = self.ar
        if not ar:
            return
        self.ar = None
        try:
            if ar.get("job"):
                self.root.after_cancel(ar["job"])
            ar["f"].destroy()
        except tk.TclError:
            pass
        self.keys.clear()

    def finish_arena(self):
        ar = self.ar
        res = ar["sim"].result()
        self.close_arena()
        self.g.resolve_attack(res)
        self.after_change()

    def _apply_inputs(self, ar, now):
        sim = ar["sim"]
        r = self.remote_in
        if ar["me_att"]:
            sim.set_aim(*self.mouse)
            for _ in range(max(0, self.click_count - ar["lc"])):
                sim.click()
            ar["lc"] = self.click_count
            if ar["remote"] and r:
                k = r.get("k", [0, 0])
                sim.set_def_input(k[0], k[1])
                m = r.get("m", [AR.SIZE / 2, AR.SIZE / 3])
                sim.set_def_aim(m[0], m[1])                       # 방패 방향 등
                c = int(r.get("c", 0))
                for _ in range(max(0, c - ar["rc"])):
                    sim.def_click()
                ar["rc"] = max(ar["rc"], c)
                if r.get("p") is not None:
                    sim.pick(int(r["p"]))
        else:
            sim.set_def_input(*self.move_vec())
            sim.set_def_aim(*self.mouse)
            for _ in range(max(0, self.click_count - ar["lc"])):
                sim.def_click()
            ar["lc"] = self.click_count
            if ar["remote"] and r:
                m = r.get("m", [AR.SIZE / 2, AR.SIZE / 3])
                sim.set_aim(m[0], m[1])
                c = int(r.get("c", 0))
                for _ in range(max(0, c - ar["rc"])):
                    sim.click()
                ar["rc"] = max(ar["rc"], c)

    def _arena_sounds(self, evs):
        names = {"fire": "play", "hit": "hit", "boom": "hit", "heal": "heal", "block": "play", "break": "hit", "warp": "turn_opp"}
        seen = set()
        for e in evs:
            n = names.get(e)
            if n and n not in seen:
                seen.add(n)
                self.sound.play(n)

    def arena_tick(self):
        ar = self.ar
        if not ar:
            return
        t_start = time.perf_counter()
        now = t_start
        dt = min(0.1, now - ar["last"])
        ar["last"] = now
        ar["dt"] = dt
        kind, sim = ar["kind"], ar["sim"]
        if ar["phase"] == "intro" and now - ar["t0"] >= ARENA_INTRO:
            ar["phase"] = "run"
        if kind == "host":
            if ar["phase"] == "intro":
                ar["snap"] = sim.snapshot()
            elif ar["phase"] == "run":
                self._apply_inputs(ar, now)
                ar["acc"] += dt
                n = 0
                while ar["acc"] >= AR.DT and n < 6 and not sim.done:
                    if ar["ai_att"]:
                        ar["ai_att"].update(AR.DT)
                    if ar["ai_def"]:
                        ar["ai_def"].update(AR.DT)
                    sim.step(AR.DT)
                    ar["acc"] -= AR.DT
                    n += 1
                snap = sim.snapshot()
                ar["evbuf"] += snap["ev"]
                self._arena_sounds(snap["ev"])
                if any(e in ("hit", "boom") for e in snap["ev"]):
                    ar["flash"] = now + 0.18
                ar["snap"] = snap
                if ar["remote"] and now - ar["sent"] >= 0.02:          # 50Hz로 화면 데이터 전송
                    ar["sent"] = now
                    snap["ev"] = ar["evbuf"]
                    ar["evbuf"] = []
                    self.net.send({"t": "as", "s": snap})
                if sim.done:
                    ar["phase"], ar["end_t"], ar["result"] = "result", now, sim.result()
                    if ar["remote"]:
                        self.net.send({"t": "ae", "r": ar["result"]})
            elif ar["phase"] == "result" and now - ar["end_t"] >= 1.6:
                self.finish_arena()
                return
        else:   # 참가자: 입력만 보내고 방장이 보내 주는 화면을 그려요
            snap = ar["snap"]
            if snap and snap.get("ev"):
                self._arena_sounds(snap["ev"])
                if any(e in ("hit", "boom") for e in snap["ev"]):
                    ar["flash"] = now + 0.18
                snap["ev"] = []
            if ar["phase"] == "run" and now - ar["sent"] >= 0.025 and self.net:   # 40Hz로 입력 전송
                ar["sent"] = now
                self.net.send({"t": "ai", "k": list(self.move_vec()), "m": [round(self.mouse[0]), round(self.mouse[1])],
                               "c": self.click_count, "p": self.pick_sent})
            if ar["phase"] == "result" and now - ar["end_t"] > 5:       # 안전장치
                self.close_arena()
                return
        self.arena_draw(now)
        if now - ar["info"] >= 0.1:
            ar["info"] = now
            self.arena_info(now)
        if self.ar is ar:
            spent = int((time.perf_counter() - t_start) * 1000)
            ar["job"] = self.root.after(max(1, 15 - spent), self.arena_tick)

    def _lset(self, ar, key, widget, **kw):
        """라벨 값이 바뀔 때만 갱신"""
        if ar["lcache"].get(key) != kw:
            ar["lcache"][key] = kw
            widget.config(**kw)

    def arena_info(self, now):
        ar = self.ar
        lbl, v, snap = ar["lbl"], self.view, ar["snap"]
        if v:
            mx = CFG["max_hp"]
            for key in ("me", "op"):
                hp = max(v[key]["hp"], 0)
                self._lset(ar, key, lbl[key], text=str(hp))
                lbl[key + "_bar"].set(hp, mx)
        if snap:
            self._lset(ar, "dmg", lbl["dmg"],
                       text="?" if ar["spec"]["mode"] == "pick" else str(min(snap["dmg"], ar["spec"].get("max", 99))))
            left = max(0.0, snap["T"] - snap["t"])
            self._lset(ar, "time", lbl["time"], text=f"남은 시간 {left:0.1f}초" if ar["spec"]["mode"] != "pick" else "")

    def _predict(self, ar, snap):
        """(참가자가 피하는 쪽일 때) 내 점은 입력 즉시 움직이고, 방장의 위치로 서서히 맞춰요 → 체감 지연 감소"""
        ax, ay = snap["d"]
        p = ar.get("pred")
        if p is None:
            p = ar["pred"] = [ax, ay]
        dt = ar.get("dt", 0.016)
        ix, iy = self.move_vec()
        if ix and iy:
            ix *= 0.7071
            iy *= 0.7071
        sp = snap.get("sp", AR.DEF_SPEED)
        p[0] = min(max(p[0] + ix * sp * dt, 0), AR.SIZE)
        p[1] = min(max(p[1] + iy * sp * dt, 0), AR.SIZE)
        if math.hypot(ax - p[0], ay - p[1]) > 90:
            p[0], p[1] = ax, ay
        else:
            k = min(1.0, 10 * dt)
            p[0] += (ax - p[0]) * k
            p[1] += (ay - p[1]) * k
        return [p[0], p[1]]

    def arena_draw(self, now):
        ar = self.ar
        snap = ar["snap"]
        view = snap
        if ar["kind"] == "guest" and snap:
            view = dict(snap)
            if ar["me_att"]:
                view["aim"] = [self.mouse[0], self.mouse[1]]               # 내 조준은 내 마우스 그대로
            else:
                view["da"] = [self.mouse[0], self.mouse[1]]
                if ar["spec"]["mode"] != "pick" and not snap.get("np"):
                    view["d"] = self._predict(ar, snap)
        ar["rend"].hover = self.mouse
        ar["rend"].update(view, ar, now)

    # ── 게임 시작/종료 ──
    def start_ai(self):
        if not self.deck_ok():
            return
        self.leave_net()
        self.reset_game_state()
        self.mode, self.g = "ai", Game(self.deck, auto_deck())
        self.show("battle")
        self.after_change()

    def reset_game_state(self):
        self.close_arena()
        self.guest_arena = False
        self.close_zoom()
        self.clear_fx()
        if self.ai_job:
            self.root.after_cancel(self.ai_job)
        self.ai_job, self.g, self.view, self.sel_id, self.prev_hp, self.mode = None, None, None, None, None, None

    def leave(self):
        self.leave_net()
        self.reset_game_state()
        self.reset_lobby_state()
        self.reset_online("")
        self.over_f.place_forget()
        self.show("menu")

    # ── 네트워크 이벤트 ──
    def poll(self):
        try:
            while self.net:
                try:
                    ev = self.net.q.get_nowait()
                except queue.Empty:
                    break
                self.on_net(ev)
        finally:
            self.root.after(15, self.poll)

    def on_net(self, ev):
        kind = ev[0]
        net = self.net
        if kind == "room":                                    # (방장) 방이 만들어짐 → 대기실
            self.reset_lobby_state()
            self.room_code = ev[1]
            self.show("lobby")
            self.lobby_sync()
        elif kind == "paired":                                # 두 사람이 이어짐
            self.opp_here = True
            self.show("lobby")
            self.lobby_sync()
        elif kind == "error":
            self.leave_net()
            self.reset_game_state()
            self.reset_lobby_state()
            self.show("online")
            self.reset_online(ev[1], True)
        elif kind in ("disc", "left"):
            if self.view and not self.view["o"]:
                messagebox.showinfo("연결 끊김", "상대와 연결이 끊어졌어요.")
                self.leave()
            elif self.view and self.view["o"]:                # 끝난 화면에서 상대가 나감
                self.leave_net()
                self.over_sub.config(text="상대가 나갔어요.")
                self.lobby_btn.pack_forget()
            else:
                self.leave_net()
                self.reset_lobby_state()
                self.show("online")
                self.reset_online("상대와 연결이 끊어져서 방이 닫혔어요." if kind == "left" or self.current == "lobby"
                                  else "연결이 끊어졌어요.", True)
        elif kind == "msg":
            m = ev[1]
            if m.get("t") == "lob":
                self.handle_lob(m)
            elif net.role == "host":
                self.host_msg(m)
            else:
                self.guest_msg(m)

    def host_msg(self, m):
        if not self.g:
            return
        if m.get("t") == "ai":                 # 상대의 아레나 입력
            self.remote_in = m
        else:
            ok, msg = self.g.act(1, m)
            self.after_change()
            if not ok:
                self.net.send({"t": "st", "v": self.g.view_for(1), "n": msg})

    def guest_msg(self, m):
        if m.get("t") == "err":
            self.set_msg(f"거절됨: {m.get('msg')}")
            return
        if m.get("t") == "as" and self.ar and self.ar["kind"] == "guest":      # 아레나 화면 데이터
            self.ar["snap"] = m["s"]
            return
        if m.get("t") == "ae" and self.ar and self.ar["kind"] == "guest":      # 아레나 결과
            self.ar["phase"], self.ar["result"], self.ar["end_t"] = "result", m["r"], time.perf_counter()
            return
        if m.get("t") != "st":
            return
        first = self.mode != "guest"
        if first:
            if m["v"].get("o"):                # 대기실로 돌아온 뒤 늦게 도착한 옛 상태는 무시
                return
            self.reset_game_state()
            self.mode = "guest"
            self.my_ready = self.opp_ready = False
            self.show("battle")
        self.apply_view(m["v"])
        pd = m["v"].get("pd")
        if pd and not self.ar:
            self.start_arena_remote(pd)
        elif not pd and self.ar:
            self.close_arena()
        if m.get("n"):
            self.set_msg(m["n"])


if __name__ == "__main__":
    App().run()

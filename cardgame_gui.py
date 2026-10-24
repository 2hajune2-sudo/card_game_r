#!/usr/bin/env python3
"""한 장 승부 - tkinter 창 버전 (AI 대전 / 온라인 대전 / 덱 구성)

cardgame.py, cards.json 과 같은 폴더에 두고 실행하세요.
    python cardgame_gui.py

- 카드를 한 번 클릭하면 선택, 더블클릭하면 바로 사용
- 게임 규칙·AI·통신은 cardgame.py 를 그대로 사용합니다.
  (터미널 버전과도 서로 온라인 대전이 됩니다)
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
                      validate_hello, rarity_counts, local_ip, LIMIT, card_notes,
                      make_code, parse_code, open_server, public_ip)

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
MODE_ICON = {"shoot": "🎯", "swarm": "🐜", "zone": "🔥", "chase": "🗡", "bounce": "🎲", "pick": "🎁"}
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
        canvas.create_rectangle(x1, y1 + h * i / steps, x2, y1 + h * (i + 1) / steps + 1,
                                fill=col, outline=col)


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
class RBtn(tk.Canvas):
    def __init__(self, parent, text, cmd=None, w=120, h=40, r=14, bg=CARD_BG, fc=PRIMARY,
                 hc=PRIMARY_H, pc=PRIMARY_P, tc="#FFF", font=(FONT, 10, "bold")):
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0)
        self.cmd, self.w, self.h, self.fc, self.hc, self.pc, self.tc = cmd, w, h, fc, hc, pc, tc
        self.on = True
        self._sh = self.create_polygon(rrp(2, 2, w - 2, h - 2, r), smooth=True, fill=fc, outline="")
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
        self.create_text(w - 13, h - 15, anchor="e", text=RN[c["rarity"]],
                         font=(FONT, max(7, int(8 * s)), "bold"), fill=rc)
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
    b = tk.Label(f, text=describe(c), font=(FONT, 8), bg=PAPER, fg=TEXT_MUTED, wraplength=215,
                 justify="left")
    b.pack(anchor="w", padx=6, pady=(0, 3))
    if on_click:                      # 클릭하면 카드 확대
        for w in (f, a, b):
            w.bind("<Button-1>", lambda e: on_click())
            w.config(cursor="hand2")
    return f


# ─── 네트워크 (줄 단위 JSON, cardgame.py 터미널 버전과 같은 규약) ─────
class Net:
    def __init__(self):
        self.q = queue.Queue()
        self.sock = None
        self.srv = None
        self.closed = False
        self.role = None
        self.ready = False

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
                        self.q.put(("msg", json.loads(line.decode("utf-8"))))
        except (OSError, ValueError):
            pass
        if not self.closed:
            self.q.put(("disc",))

    def send(self, obj):
        if self.sock:
            try:
                self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass

    def host(self):
        self.role = "host"

        def pub(port):                       # 공인 IP 조회는 기다리지 않고 따로 (랙 방지)
            ip = public_ip()
            if ip and not self.closed:
                self.q.put(("public", make_code(ip, port)))

        def run():
            try:
                srv, port = open_server()
                srv.settimeout(0.5)
                self.srv = srv
                self.q.put(("listening", make_code(local_ip(), port), port))
                threading.Thread(target=pub, args=(port,), daemon=True).start()
                sock = None
                while not self.closed and sock is None:
                    try:
                        sock, addr = srv.accept()
                    except socket.timeout:
                        continue
                srv.close()
                if sock is None:
                    return
                sock.settimeout(None)
            except OSError as e:
                if not self.closed:
                    self.q.put(("error", f"방을 열지 못했어요: {e}"))
                return
            self.sock = sock
            self.q.put(("connected", addr[0]))
            self._reader(sock)

        threading.Thread(target=run, daemon=True).start()

    def join(self, ip, port, deck):
        self.role = "guest"

        def run():
            try:
                sock = socket.create_connection((ip, port), timeout=8)
                sock.settimeout(None)
            except OSError as e:
                self.q.put(("error", f"접속하지 못했어요. 코드가 맞는지, 방이 열려 있는지 확인해 주세요. ({e})"))
                return
            self.sock = sock
            self.send({"t": "hello", "deck": deck, "arena": True})
            self._reader(sock)

        threading.Thread(target=run, daemon=True).start()

    def close(self):
        self.closed = True
        for s in (self.sock, self.srv):
            try:
                if s:
                    s.close()
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
    (예전에는 매 프레임 전부 지우고 20~30개를 새로 만들어서 렉의 원인이었어요)"""
    S = AR.SIZE

    def __init__(self, cv, spec, me_att, cid, pick_rects):
        self.cv, self.mode, self.me_def = cv, spec["mode"], not me_att
        self.cache, self.pools, self.flash = {}, {}, False
        S = self.S
        for i in range(1, 6):                                   # 바닥 격자 (정적)
            cv.create_line(i * 100, 0, i * 100, S, fill="#14141C")
            cv.create_line(0, i * 100, S, i * 100, fill="#14141C")
        self.d_oval = cv.create_oval(0, 0, 0, 0, fill="#3DD6F5", outline="#FFFFFF", width=2, state="hidden")
        self.d_tag = cv.create_text(0, 0, text="나" if self.me_def else "상대", fill="#BFEFFF",
                                    font=(FONT, 9, "bold"), state="hidden")
        self.bar = cv.create_rectangle(0, 0, 0, 5, fill="#FFB020", outline="")
        self.hud = cv.create_text(10, 22, text="", anchor="w", fill="#E6E6F0", font=(FONT, 11, "bold"))
        m = self.mode
        if m == "shoot":
            self.aim = cv.create_line(0, 0, 0, 0, fill="#FF3B3B", width=2, dash=(7, 5), state="hidden")
            self.tur = cv.create_rectangle(0, 0, 0, 0, fill="#8A8FA8", outline="#FF3B3B", width=2, state="hidden")
        elif m == "swarm":
            self.ring = cv.create_oval(0, 0, 0, 0, outline="#38D66B", width=2, dash=(3, 3), state="hidden")
            self.cx1 = cv.create_line(0, 0, 0, 0, fill="#38D66B", state="hidden")
            self.cx2 = cv.create_line(0, 0, 0, 0, fill="#38D66B", state="hidden")
        elif m == "zone":
            self.prev = cv.create_oval(0, 0, 0, 0, outline="#FF6B6B", width=2, dash=(6, 4), state="hidden")
            self.arc = cv.create_arc(0, 0, 0, 0, start=90, extent=0, style="arc", outline="#FFD166", width=3, state="hidden")
            self.dot = cv.create_oval(0, 0, 0, 0, fill="#FF6B6B", outline="", state="hidden")
        elif m == "chase":
            self.cx1 = cv.create_line(0, 0, 0, 0, fill="#FFD166", state="hidden")
            self.cx2 = cv.create_line(0, 0, 0, 0, fill="#FFD166", state="hidden")
            self.blade = cv.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, fill="#FF5C5C", outline="#FFFFFF", width=2, state="hidden")
        elif m == "pick":
            self.boxes = []
            for (x1, y1, x2, y2) in pick_rects:
                r = cv.create_rectangle(x1, y1, x2, y2, fill="#2A2A38", outline="#8A8FA8", width=2)
                t = cv.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="", fill="#FFFFFF", font=(FONT, 28, "bold"))
                self.boxes.append((r, t, (x1, y1, x2, y2)))
            self.hint = cv.create_text(S / 2, 190, text="", fill="#FFD166", font=(FONT, 18, "bold"))
            self.ptime = cv.create_text(S / 2, 430, text="", fill="#9AA0B5", font=(FONT, 12))
        # 안내 / 결과 오버레이 (처음부터 만들어 두고 보였다 숨겼다만 해요)
        title, att_txt, def_txt = AR.HELP[m]
        cx = S / 2
        self.intro = [
            cv.create_rectangle(40, 190, S - 40, 420, fill="#101018", outline="#FFD166", width=2, state="hidden"),
            cv.create_text(cx, 235, text=CARDS[cid]["name"], fill="#FFD166", font=(FONT, 30, "bold"), state="hidden"),
            cv.create_text(cx, 280, text="⚔ 당신이 공격!" if me_att else "🏃 당신이 피하세요!",
                           fill="#FF6B6B" if me_att else "#3DD6F5", font=(FONT, 20, "bold"), state="hidden"),
            cv.create_text(cx, 335, text=att_txt if me_att else def_txt, fill="#E6E6F0", font=(FONT, 12), width=480,
                           state="hidden"),
        ]
        self.count = cv.create_text(cx, 395, text="", fill="#FFFFFF", font=(FONT, 28, "bold"), state="hidden")
        self.res = [cv.create_rectangle(60, 250, S - 60, 350, fill="#101018", outline="#FFD166", width=2, state="hidden"),
                    cv.create_text(cx, 300, text="", fill="#FFFFFF", font=(FONT, 24, "bold"), state="hidden")]
        self.me_att = me_att
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

    def pool(self, name, data, make, place):
        lst = self.pools.setdefault(name, [])
        for i, d in enumerate(data):
            if i >= len(lst):
                lst.append(make())
            else:
                self.show_group(lst[i], True)
            place(lst[i], d)
        for i in range(len(data), len(lst)):
            self.show_group(lst[i], False)

    def show_group(self, g, on):
        for it in (g if isinstance(g, tuple) else (g,)):
            self.show(it, on)

    def _low(self, g):
        for it in (g if isinstance(g, tuple) else (g,)):
            self.cv.tag_lower(it, self.d_oval)          # 새 요소는 플레이어 점 아래에
        return g

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
                self.xy(self.d_oval, dx - r, dy - r, dx + r, dy + r)
                self.xy(self.d_tag, dx, dy - r - 9)
                self.show(self.d_oval)
                self.show(self.d_tag)
            self.xy(self.bar, 0, 0, S * max(0.0, 1.0 - s["t"] / max(s["T"], 0.1)), 5)
            getattr(self, "_m_" + self.mode)(s)
        # 안내 오버레이
        intro = ar["phase"] == "intro"
        if intro != self.intro_on:
            self.intro_on = intro
            for it in self.intro + [self.count]:
                self.show(it, intro)
                if intro:
                    cv.tag_raise(it)
        if intro:
            self.cfg(self.count, text=str(int(max(0.0, ARENA_INTRO - (now - ar["t0"]))) + 1))
        # 결과 오버레이
        res = ar["phase"] == "result" and ar["result"] is not None
        if res != self.res_on:
            self.res_on = res
            for it in self.res:
                self.show(it, res)
                if res:
                    cv.tag_raise(it)
        if res:
            r = ar["result"]
            if self.mode == "pick":
                txt = "안전한 상자! 🍀" if r.get("safe") else "위험한 상자! 💥"
            elif self.me_att:
                txt = f"💥 {r['dmg']} 피해를 입혔어요!" if r["dmg"] else "😤 모두 피했어요…"
            else:
                txt = f"💢 {r['dmg']} 피해를 입었어요!" if r["dmg"] else "😎 모두 피했어요!"
            self.cfg(self.res[1], text=txt)

    # ── 모드별 갱신 ──
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
        self.pool("b", s["b"], lambda: self._low(self.cv.create_oval(0, 0, 0, 0, fill="#E8D9B0", outline="#FFFFFF")),
                  lambda it, d: self.xy(it, d[0] - br, d[1] - br, d[0] + br, d[1] + br))
        self.cfg(self.hud, text=f"남은 탄 {s['left']}", fill="#E8D9B0")

    def _m_swarm(self, s):
        ax, ay = s["aim"]
        self.xy(self.ring, ax - 14, ay - 14, ax + 14, ay + 14)
        self.xy(self.cx1, ax - 6, ay, ax + 6, ay)
        self.xy(self.cx2, ax, ay - 6, ax, ay + 6)
        for it in (self.ring, self.cx1, self.cx2):
            self.show(it)
        r = s["ar"]
        self.pool("a", s["a"], lambda: self._low(self.cv.create_oval(0, 0, 0, 0, fill="#38D66B", outline="#B8FFCB")),
                  lambda it, d: self.xy(it, d[0] - r, d[1] - r, d[0] + r, d[1] + r))
        self.cfg(self.hud, text=f"남은 개미 {s['left']}", fill="#38D66B")

    def _m_zone(self, s):
        if s["left"] > 0:
            ax, ay = s["aim"]
            r = s["r"]
            self.xy(self.prev, ax - r, ay - r, ax + r, ay + r)
            self.xy(self.arc, ax - r - 6, ay - r - 6, ax + r + 6, ay + r + 6)
            self.cfg(self.arc, extent=round(-359.9 * s["ch"], 1))
            self.xy(self.dot, ax - 3, ay - 3, ax + 3, ay + 3)
            for it in (self.prev, self.arc, self.dot):
                self.show(it)
        else:
            for it in (self.prev, self.arc, self.dot):
                self.show(it, False)
        warn = max(s["warn"], 0.01)

        def make():
            cv = self.cv
            return self._low((cv.create_oval(0, 0, 0, 0, fill="#4A1212", outline="#FF3B3B", width=2),
                              cv.create_oval(0, 0, 0, 0, fill="#B81D1D", outline=""),
                              cv.create_oval(0, 0, 0, 0, outline="#FFD166", dash=(2, 3))))

        def place(g, z):
            x, y, r, st, t = z
            outer, inner, ring = g
            self.xy(outer, x - r, y - r, x + r, y + r)
            if st == 0:
                k = min(1.0, t / warn)
                self.cfg(outer, fill="#4A1212", outline="#FF3B3B")
                self.xy(inner, x - r * k, y - r * k, x + r * k, y + r * k)
                self.xy(ring, x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4)
                self.show(inner)
                self.show(ring)
            else:
                self.cfg(outer, fill="#FFB020" if st == 1 else "#1B4D27", outline="#FFFFFF" if st == 1 else "#9BE59D")
                self.show(inner, False)
                self.show(ring, False)
        self.pool("z", s["z"], make, place)
        self.cfg(self.hud, text=f"남은 폭격 {s['left']}", fill="#FF6B6B")

    def _m_chase(self, s):
        ax, ay = s["aim"]
        self.xy(self.cx1, ax - 8, ay, ax + 8, ay)
        self.xy(self.cx2, ax, ay - 8, ax, ay + 8)
        x, y = s["c"]
        r = s["cr"]
        self.xy(self.blade, x, y - r, x + r, y, x, y + r, x - r, y)
        for it in (self.cx1, self.cx2, self.blade):
            self.show(it)

    def _m_bounce(self, s):
        r = s["dcr"]

        def make():
            cv = self.cv
            return self._low((cv.create_rectangle(0, 0, 0, 0, fill="#F5F5F5", outline="#222"),
                              cv.create_text(0, 0, text="🎲", font=(FONT, int(r)))))

        def place(g, d):
            self.xy(g[0], d[0] - r, d[1] - r, d[0] + r, d[1] + r)
            self.xy(g[1], d[0], d[1])
        self.pool("d", s["dc"], make, place)

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

    hover = (0.0, 0.0)


# ─── 앱 ─────────────────────────────────────────────────
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🃏 한 장 승부")
        self.root.geometry(f"{W}x{H}")
        self.root.resizable(False, False)
        self.deck = load_deck()
        self.mode = None          # None | 'ai' | 'host' | 'guest'
        self.g = None
        self.view = None
        self.sel_id = None
        self.net = None
        self.ai_job = None
        self.prev_hp = None
        self.msg_job = None
        self.fx_token = 0
        self.fx_widgets = []
        self.sound = Sound(self.root)
        self.zoom_f = None
        self.root.bind("<Escape>", lambda e: self.close_zoom())
        # 실시간 아레나 상태
        self.ar = None
        self.keys = set()
        self.key_jobs = {}
        self.mouse = (AR.SIZE / 2, AR.SIZE / 2)
        self.click_count = 0
        self.pick_sent = None
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
        self.build_battle()
        self.root.after(80, self.poll)

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
            self.update_deck_ui()

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
        c.create_text(W / 2, 112, text="설치로 판을 깔고, 즉발로 승부를 내는 1:1 카드 배틀",
                      font=(FONT, 12), fill=TEXT_MUTED)
        p = panel(c, W / 2 - 230, 140, 460, 465, r=26, pad=22)
        self.menu_deck_lbl = tk.Label(p, font=(FONT, 11, "bold"), bg=CARD_BG)
        self.menu_deck_lbl.pack(pady=(0, 10))
        items = [("⚔  AI 대전", self.start_ai, PRIMARY, PRIMARY_H, PRIMARY_P),
                 ("🌐  방 만들기 / 참가 (온라인)", lambda: self.show("online"), SECONDARY, SECONDARY_H, SECONDARY_P),
                 ("🃏  덱 구성", lambda: self.show("deck"), TEAL, "#3ED9CA", TEAL_DARK),
                 ("📖  규칙 보기", self.show_rules, "#E07B2A", "#F09040", "#C06010"),
                 ("🚪  종료", self.root.destroy, "#C9A876", "#D9BA8C", "#B5905F")]
        for t, cmd, a, b, d in items:
            RBtn(p, t, cmd, w=380, h=54, r=18, fc=a, hc=b, pc=d, font=(FONT, 13, "bold")).pack(pady=5)

    def update_menu(self):
        err = validate_deck(self.deck)
        if err:
            self.menu_deck_lbl.config(text=f"내 덱 {len(self.deck)}장 — 덱 구성이 필요해요 ({CFG['deck_min']}~{CFG['deck_max']}장)", fg=FAIL_TXT)
        else:
            self.menu_deck_lbl.config(text=f"내 덱 {len(self.deck)}장 ✔ 준비 완료", fg=SUCCESS_TXT)

    def show_rules(self):
        lim = CFG["rarity_limit"]
        messagebox.showinfo("규칙", (
            f"• 덱 {CFG['deck_min']}~{CFG['deck_max']}장. 일반 제한 없음 / 레어 {lim['rare']} / 영웅 {lim['hero']} / 레전드 {lim['legend']}장까지\n"
            f"• 같은 카드는 덱에 최대 {CFG['max_copies']}장까지\n"
            f"• 시작 체력 {CFG['start_hp']}, 손패 {CFG['start_hand']}장, 선공 무작위, 체력 0이면 패배\n"
            f"• 설치 카드: 턴을 쓰지 않지만 한 턴에 1장만 (설치 칸 최대 {CFG['field_max']})\n"
            "• 즉발 카드: 사용하면 턴이 끝나요. 손패에 즉발 카드가 있으면 턴을 넘길 수 없어요\n"
            f"• 매 턴 시작에 {CFG['draw_per_turn']}장 뽑기"
            f"{' (선공 첫 턴 제외)' if CFG['first_player_skips_draw'] else ''}\n"
            f"• 덱을 다 뽑으면 내 덱 전체로 리필하고 {CFG['refill_draw']}장 뽑기\n"
            f"• 손패 최대 {CFG['hand_limit']}장\n"
            "• 설치 중에는 'N턴 뒤 발동'이나 '설치가 N장 이상일 때만 발동'하는 카드가 있어요\n"
            "• 확률 카드는 결과가 무작위예요 (방장 컴퓨터가 굴려요)\n"
            "• 방어로는 피해를 1 아래로 줄일 수 없어요 (보호막은 전부 막아요)\n"
            "• 등급: 일반(수치 1, 단독 효과 · 개미 떼만 같은 카드를 모으면 강해짐) / 레어(2~3, 쓸만한 특수) /\n"
            "  영웅(3, 강하지만 리스크) / 레전드(각각 다른 독특한 효과)\n\n"
            "• 공격 카드를 쓰면 검은 아레나가 열려요. 공격하는 쪽은 카드마다 다른 방식으로 마우스 조종,\n"
            "  맞는 쪽은 WASD / 방향키로 피해요. 맞은 만큼만 피해가 들어가요 (한글 입력 상태에서도 돼요)\n"
            "• 상자 고르기 같은 확률 카드는 맞는 쪽이 직접 골라요 (안전하면 회복, 위험하면 피해)\n"
            "• 방어 설치(방벽)는 받는 피해를 N까지 막고, 다 막거나 지속 턴이 지나면 사라져요\n"
            "• 필드 전용 카드는 아레나에서만 효과가 있어요 (피할 때 속도 증가 등)\n\n"
            "카드 클릭 = 선택, 더블클릭 = 바로 사용\n"
            "오른쪽 클릭 / '🔍 자세히' 버튼 / 설치된 카드 클릭 = 카드 확대 (덱 구성에서는 카드 클릭)"))

    # ── 덱 구성 ──
    def build_deck(self):
        f, c = self.make_screen("deck")
        bar = panel(c, 20, 16, 1260, 72, r=20, pad=12)
        RBtn(bar, "← 메뉴", lambda: self.show("menu"), w=100, h=42, fc=SECONDARY, hc=SECONDARY_H,
             pc=SECONDARY_P).pack(side="left", padx=(0, 14))
        tk.Label(bar, text="🃏 덱 구성", font=(FONT, 18, "bold"), bg=CARD_BG, fg=TEXT_DARK).pack(side="left")
        self.deck_total = tk.Label(bar, font=(FONT, 13, "bold"), bg=CARD_BG)
        self.deck_total.pack(side="left", padx=18)
        self.meters = {}
        for r in RORDER:
            lb = tk.Label(bar, font=(FONT, 10, "bold"), bg=CARD_BG, fg=RC[r])
            lb.pack(side="left", padx=6)
            self.meters[r] = lb
        RBtn(bar, "비우기", self.deck_clear, w=90, h=42, fc="#C9A876", hc="#D9BA8C", pc="#B5905F").pack(side="right")
        RBtn(bar, "자동 구성", self.deck_auto, w=110, h=42, fc=TEAL, hc="#3ED9CA", pc=TEAL_DARK).pack(side="right", padx=8)

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
            CardView(t, d["id"], 150, 210, bg=BG_BOTTOM,
                     cmd=lambda cid=d["id"]: self.show_zoom(cid)).pack()
            ctl = tk.Frame(t, bg=BG_BOTTOM)
            ctl.pack(pady=(6, 0))
            minus = RBtn(ctl, "−", lambda cid=d["id"]: self.deck_change(cid, -1), w=40, h=30, r=12,
                         bg=BG_BOTTOM, fc=SECONDARY, hc=SECONDARY_H, pc=SECONDARY_P, font=(FONT, 12, "bold"))
            minus.pack(side="left")
            cnt = tk.Label(ctl, text="0", font=(FONT, 13, "bold"), bg=BG_BOTTOM, fg=TEXT_DARK, width=3)
            cnt.pack(side="left")
            plus = RBtn(ctl, "+", lambda cid=d["id"]: self.deck_change(cid, 1), w=40, h=30, r=12,
                        bg=BG_BOTTOM, fc=PRIMARY, hc=PRIMARY_H, pc=PRIMARY_P, font=(FONT, 12, "bold"))
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
            plus.enable(not full and k < CFG["max_copies"]
                        and rc[CARDS[cid]["rarity"]] < LIMIT[CARDS[cid]["rarity"]])

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
        muted = dict(font=(FONT, 10), bg=CARD_BG, fg=TEXT_MUTED)
        tk.Label(p, text="방 만들기", font=(FONT, 16, "bold"), **lab).pack(anchor="w")
        tk.Label(p, text="내가 방장이 되면 방 코드가 나와요. 친구에게 코드를 알려 주세요.", **muted).pack(anchor="w")
        row = tk.Frame(p, bg=CARD_BG)
        row.pack(anchor="w", pady=10)
        self.host_btn = RBtn(row, "방 만들기", self.toggle_host, w=130, h=40, fc=PRIMARY, hc=PRIMARY_H, pc=PRIMARY_P)
        self.host_btn.pack(side="left")
        self.copy_row = tk.Frame(row, bg=CARD_BG)          # 코드가 나오면 복사 버튼이 생겨요
        self.codes = {}
        tk.Frame(p, bg=NEUTRAL_BD, height=2).pack(fill="x", pady=10)
        tk.Label(p, text="방 참가", font=(FONT, 16, "bold"), **lab).pack(anchor="w")
        tk.Label(p, text="방장이 알려 준 방 코드를 입력하세요.", **muted).pack(anchor="w")
        row2 = tk.Frame(p, bg=CARD_BG)
        row2.pack(anchor="w", pady=10)
        self.join_code = tk.Entry(row2, width=17, font=(FONT, 15, "bold"), bd=2, relief="solid", justify="center")
        self.join_code.pack(side="left", padx=(0, 10))
        self.join_code.bind("<Return>", lambda e: self.start_join())
        RBtn(row2, "참가", self.start_join, w=90, h=40, fc=SECONDARY, hc=SECONDARY_H, pc=SECONDARY_P).pack(side="left")
        self.on_status = tk.Label(p, text="", font=(FONT, 11), bg=NEUTRAL_BG, fg=TEXT_DARK, wraplength=520,
                                  justify="left", padx=12, pady=12)
        self.on_status.pack(fill="x", pady=(12, 8))
        tk.Label(p, text="같은 와이파이/LAN이면 '와이파이 코드'로 바로 돼요.\n인터넷으로 하려면 방장 공유기에서 포트 포워딩을 한 뒤 '인터넷 코드'를 쓰세요.",
                 justify="left", **muted).pack(anchor="w")
        RBtn(p, "← 메뉴", self.leave, w=110, h=40, fc="#C9A876", hc="#D9BA8C", pc="#B5905F").pack(anchor="w", pady=(12, 0))

    def add_code(self, key, label, code):
        """방 코드를 저장하고 복사 버튼을 보여 줘요"""
        self.codes[key] = code
        self.copy_row.pack(side="left", padx=(10, 0))
        RBtn(self.copy_row, f"📋 {label}", lambda: self.copy_code(code), w=140, h=40, fc=TEAL, hc="#4FD3C6", pc=TEAL_DARK
             ).pack(side="left", padx=(0, 6))

    def copy_code(self, code):
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.set_online_status(self.on_status.cget("text") + f"\n(복사했어요: {code})")

    def reset_host(self, msg=None, bad=False):
        """방 만들기 버튼/코드/안내를 처음 상태로"""
        self.host_btn.set_text("방 만들기")
        self.clear_codes()
        if msg is not None:
            self.set_online_status(msg, bad)

    def clear_codes(self):
        self.codes = {}
        for w in self.copy_row.winfo_children():
            w.destroy()
        self.copy_row.pack_forget()

    def set_online_status(self, text, bad=False):
        self.on_status.config(text=text, bg=FAIL_BG if bad else NEUTRAL_BG)

    def toggle_host(self):
        if self.net and self.net.role == "host" and not self.g:   # 대기 중 → 취소
            self.net.close()
            self.net = None
            self.reset_host("방을 닫았어요.")
            return
        if not self.deck_ok():
            return
        self.leave_net()
        self.clear_codes()
        self.net = Net()
        self.net.host()
        self.host_btn.set_text("취소")
        self.set_online_status("방을 여는 중…")

    def start_join(self):
        if not self.deck_ok():
            return
        try:
            ip, port = parse_code(self.join_code.get())
        except ValueError as e:
            self.set_online_status(str(e), True)
            return
        self.leave_net()
        self.reset_host()
        self.net = Net()
        self.net.join(ip, port, self.deck)
        self.set_online_status("접속하는 중…")

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
                            fc=SECONDARY, hc=SECONDARY_H, pc=SECONDARY_P, font=(FONT, 12, "bold"))
        self.end_btn.pack(side="left", padx=10)
        self.zoom_btn = RBtn(ar, "🔍 자세히", self.zoom_selected, w=110, h=42, r=16,
                             fc=TEAL, hc="#3ED9CA", pc=TEAL_DARK, font=(FONT, 10, "bold"))
        self.zoom_btn.pack(side="left")
        RBtn(ar, "나가기", self.leave, w=90, h=42, r=16, fc="#C9A876", hc="#D9BA8C", pc="#B5905F").pack(side="left", padx=(10, 0))
        self.snd_btn = RBtn(ar, "🔊 소리 켬", self.toggle_sound, w=110, h=42, r=16, fc="#8A9BB8", hc="#9EAECA", pc="#6F82A3",
                            font=(FONT, 9, "bold"))
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
        self.again_btn = RBtn(ob, "다시 하기", self.start_ai, w=130, h=44, fc=PRIMARY, hc=PRIMARY_H, pc=PRIMARY_P)
        self.again_btn.pack(side="left", padx=6)
        self.over_menu_btn = RBtn(ob, "메뉴로", self.leave, w=130, h=44, fc=SECONDARY, hc=SECONDARY_H, pc=SECONDARY_P)
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
            self.over_sub.config(text="상대의 체력을 모두 깎았어요." if v["w"] == 1 else
                                 "체력이 0이 되었어요." if v["w"] == 0 else "둘 다 쓰러졌어요.")
            if self.mode == "ai":
                self.again_btn.pack_forget()
                self.again_btn.pack(side="left", padx=6, before=self.over_menu_btn)
            else:
                self.again_btn.pack_forget()
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
        tk.Label(right, text=f"{glyph(c)}  {c['name']}", font=(FONT, 26, "bold"), bg=CARD_BG, fg=TEXT_DARK
                 ).pack(anchor="w")
        tk.Label(right, text=f"{RN[c['rarity']]} · {KN[c['kind']]} 카드", font=(FONT, 12, "bold"), bg=CARD_BG,
                 fg=rc).pack(anchor="w", pady=(0, 10))
        tk.Label(right, text=describe(c), font=(FONT, 15, "bold"), bg=NEUTRAL_BG, fg=TEXT_DARK, wraplength=wrap - 24,
                 justify="left", padx=12, pady=10).pack(fill="x")
        tk.Label(right, text="자세한 규칙", font=(FONT, 11, "bold"), bg=CARD_BG, fg=TEXT_MUTED
                 ).pack(anchor="w", pady=(14, 4))
        for note in card_notes(c):
            tk.Label(right, text="•  " + note, font=(FONT, 11), bg=CARD_BG, fg=TEXT_DARK, wraplength=wrap,
                     justify="left").pack(anchor="w", pady=2)
        RBtn(right, "닫기 (Esc)", self.close_zoom, w=130, h=40, fc=SECONDARY, hc=SECONDARY_H,
             pc=SECONDARY_P).pack(anchor="w", pady=(16, 0))
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
        return None

    def on_key_down(self, e):
        n = self.key_name(e)
        if not n:
            return
        job = self.key_jobs.pop(n, None)
        if job:
            self.root.after_cancel(job)
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
        title, att_txt, def_txt = AR.HELP[spec["mode"]]
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
        tk.Label(left, text="🖱 마우스: 조준·위치 / 클릭: 발사·확정" if me_att and spec["mode"] != "pick" else
                 ("🖱 마우스 클릭 또는 숫자키(1~)로 상자 고르기" if (not me_att and spec["mode"] == "pick") else
                  ("⌨ WASD / 방향키: 이동" if not me_att else "구경 중…")),
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
        self.click_count = 0
        self.pick_sent = None
        self.remote_in = {}
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
                if r.get("p") is not None:
                    sim.pick(int(r["p"]))
        else:
            sim.set_def_input(*self.move_vec())
            if ar["remote"] and r:
                m = r.get("m", [AR.SIZE / 2, AR.SIZE / 3])
                sim.set_aim(m[0], m[1])
                c = int(r.get("c", 0))
                for _ in range(max(0, c - ar["rc"])):
                    sim.click()
                ar["rc"] = max(ar["rc"], c)

    def _arena_sounds(self, evs):
        names = {"fire": "play", "hit": "hit", "boom": "hit", "heal": "heal"}
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
            elif ar["spec"]["mode"] != "pick":
                view["d"] = self._predict(ar, snap)
        ar["rend"].hover = self.mouse
        ar["rend"].update(view, ar, now)

    # ── 게임 시작/종료 ──
    def start_ai(self):
        if not self.deck_ok():
            return
        self.leave_net()
        self.reset_game_state()
        self.mode = "ai"
        self.g = Game(self.deck, auto_deck())
        self.show("battle")
        self.after_change()

    def reset_game_state(self):
        self.close_arena()
        self.guest_arena = False
        self.close_zoom()
        self.clear_fx()
        if self.ai_job:
            self.root.after_cancel(self.ai_job)
        self.ai_job = None
        self.g = None
        self.view = None
        self.sel_id = None
        self.prev_hp = None
        self.mode = None

    def leave(self):
        self.leave_net()
        self.reset_game_state()
        self.reset_host("")
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
            self.root.after(80, self.poll)

    def on_net(self, ev):
        kind = ev[0]
        net = self.net
        if kind == "listening":
            self.add_code("lan", "와이파이 코드", ev[1])
            self.set_online_status(f"방이 열렸어요! 친구에게 방 코드를 알려 주세요.\n와이파이 코드: {ev[1]}\n(상대가 들어오면 자동으로 시작해요)")
        elif kind == "public":
            self.add_code("net", "인터넷 코드", ev[1])
            self.set_online_status(self.on_status.cget("text") + f"\n인터넷 코드: {ev[1]}  (포트 포워딩 필요)")
        elif kind == "connected":
            self.set_online_status(f"{ev[1]} 접속! 덱을 확인하는 중…")
        elif kind == "error":
            self.leave_net()
            self.reset_host(ev[1], True)
        elif kind == "disc":
            if self.view and not self.view["o"]:
                messagebox.showinfo("연결 끊김", "상대와 연결이 끊어졌어요.")
                self.leave()
            elif not self.view:
                self.leave_net()
                self.reset_host("연결이 끊어졌어요.", True)
        elif kind == "msg":
            m = ev[1]
            if net.role == "host":
                self.host_msg(m)
            else:
                self.guest_msg(m)

    def host_msg(self, m):
        if not self.g:   # 첫 메시지 = hello
            err = validate_hello(m)
            if err:
                self.net.send({"t": "err", "msg": err})
                self.leave_net()
                self.reset_host(f"상대 덱이 올바르지 않아요: {err}", True)
                return
            self.reset_game_state()
            self.mode = "host"
            self.guest_arena = bool(m.get("arena"))
            self.g = Game(self.deck, m["deck"])
            self.net.ready = True
            self.show("battle")
            self.after_change()
        elif m.get("t") == "ai":           # 상대의 아레나 입력
            self.remote_in = m
        else:
            ok, msg = self.g.act(1, m)
            self.after_change()
            if not ok:
                self.net.send({"t": "st", "v": self.g.view_for(1), "n": msg})

    def guest_msg(self, m):
        if m.get("t") == "err":
            self.set_online_status(f"거절됨: {m.get('msg')}", True)
            self.leave_net()
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
            self.reset_game_state()
            self.mode = "guest"
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

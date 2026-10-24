#!/usr/bin/env python3
"""한 장 승부 - 실시간 아레나 (공격 카드를 쓰면 열리는 검은 정사각형 필드)

공격하는 쪽은 카드마다 다른 방식으로 공격을 '조종'하고, 맞는 쪽은 WASD/방향키로 피합니다.
이 파일은 화면(tkinter)과 무관한 순수 시뮬레이션이라, 창 화면·AI·터미널 자동 판정이 모두 같이 씁니다.

공격 방식(mode)
  shoot   조준선으로 총알(돌)을 쏴요           공격자: 마우스 조준 + 클릭 발사
  swarm   개미 떼를 유인해요                   공격자: 마우스로 유인 지점 지정
  zone    위험 구역을 정해 잠시 뒤 폭발시켜요   공격자: 마우스로 위치 지정 + 클릭 확정 (중앙일수록 큰 피해)
  chase   빠른 칼날/손이 쫓아가요              공격자: 마우스로 방향 지정
  bounce  주사위가 튕겨 다녀요                  공격자: 구경 (무작위)
  pick    상자 고르기 (확률 카드)              피하는 쪽이 상자를 직접 골라요
"""
import math
import random

SIZE = 600.0          # 아레나 한 변 (논리 좌표)
DT = 1.0 / 60.0       # 시뮬레이션 고정 시간 간격
DEF_R = 9.0           # 피하는 쪽 판정 반지름
DEF_SPEED = 235.0     # 피하는 쪽 기본 이동 속도 (칸/초)

MODES = ("shoot", "swarm", "zone", "chase", "bounce", "pick")

# 모드별 안내 (확대 보기 / 아레나 시작 안내에 사용): (제목, 공격자 조작, 피하는 쪽 조작)
HELP = {
    "shoot":  ("총알 조준", "마우스로 조준선을 맞추고 클릭해서 발사해요. 포탑은 테두리를 따라 계속 움직여요.",
               "WASD/방향키로 이동해 총알을 피하세요. 빨간 조준선이 총알이 날아올 길이에요."),
    "swarm":  ("개미 떼 유인", "마우스 위치로 개미 떼가 모여들어요. 상대 쪽으로 유인하세요.",
               "WASD/방향키로 이동해 초록 개미에 닿지 않게 피하세요."),
    "zone":   ("범위 폭격", "마우스로 위험 구역을 옮기다가 클릭(또는 시간이 되면 자동)으로 확정해요. 잠시 뒤 폭발! 중앙에 맞을수록 큰 피해예요.",
               "WASD/방향키로 이동해 빨간 구역 밖으로 벗어나세요."),
    "chase":  ("추격", "마우스 위치로 칼날이 쫓아가요. 상대에게 몰아 붙이세요.",
               "WASD/방향키로 이동해 칼날에 닿지 않게 피하세요."),
    "bounce": ("주사위 난무", "이번 공격은 주사위가 알아서 튕겨 다녀요. 지켜보세요.",
               "WASD/방향키로 이동해 튕겨 다니는 주사위를 피하세요."),
    "pick":   ("상자 고르기", "상대가 상자를 고르는 걸 지켜보세요. 운이 따라 줘야 해요.",
               "마우스로 상자를 클릭하거나 숫자키(1~)로 고르세요. 위험 상자면 피해, 안전 상자면 회복!"),
}


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def perimeter_point(u):
    """테두리를 따라 도는 포탑 위치 (u: 0 ~ 4*SIZE)"""
    u %= 4 * SIZE
    if u < SIZE:
        return u, 0.0
    if u < 2 * SIZE:
        return SIZE, u - SIZE
    if u < 3 * SIZE:
        return SIZE - (u - 2 * SIZE), SIZE
    return 0.0, SIZE - (u - 3 * SIZE)


class Arena:
    """아레나 한 판의 상태. step(dt)로 시간을 진행하고 snapshot()으로 화면용 데이터를 얻어요."""

    def __init__(self, spec, seed=0, mods=None):
        self.spec = dict(spec)
        self.mode = spec["mode"]
        self.rng = random.Random(seed)
        m = {"dodge": 0.0, "shrink": 0.0, "atk": 0.0, "foe_slow": 0.0, "proj_slow": 0.0}
        m.update(mods or {})
        self.mods = m #67
        self.t = 0.0
        self.time = float(spec.get("time", 9.0))
        self.done = False
        self.end_t = None
        self.dmg = 0
        self.hits = 0
        self.events = []
        self.safe = None
        # 피하는 쪽
        self.dx, self.dy = SIZE / 2, SIZE * 0.68
        self.dvx = self.dvy = 0.0
        self.dr = DEF_R * max(0.4, 1 - m["shrink"])
        self.dspeed = DEF_SPEED * (1 + m["dodge"]) * max(0.4, 1 - m["foe_slow"])
        self.in_x = self.in_y = 0
        # 공격하는 쪽
        self.mx, self.my = SIZE / 2, SIZE * 0.3
        self.clicks = 0
        self.pspeed = (1 + m["atk"]) * max(0.3, 1 - m["proj_slow"])   # 공격 투사체/개체 속도 배율
        getattr(self, "_init_" + self.mode)()

    # ── 입력 ──
    def set_def_input(self, ix, iy):
        self.in_x, self.in_y = int(clamp(ix, -1, 1)), int(clamp(iy, -1, 1))

    def set_aim(self, x, y):
        self.mx, self.my = clamp(x, 0, SIZE), clamp(y, 0, SIZE)

    def click(self):
        self.clicks += 1

    # ── 시간 진행 ──
    def step(self, dt=DT):
        if self.done:
            return
        self.t += dt
        if self.mode != "pick":
            self._move_defender(dt)
        getattr(self, "_step_" + self.mode)(dt)
        self.clicks = 0
        if not self.done and self.t >= self.time:
            self._finish()

    def _finish(self):
        if not self.done:
            self.done = True
            self.end_t = self.t

    def _move_defender(self, dt):
        ix, iy = self.in_x, self.in_y
        if ix and iy:
            ix *= 0.7071
            iy *= 0.7071
        nx = clamp(self.dx + ix * self.dspeed * dt, self.dr, SIZE - self.dr)
        ny = clamp(self.dy + iy * self.dspeed * dt, self.dr, SIZE - self.dr)
        self.dvx, self.dvy = (nx - self.dx) / dt, (ny - self.dy) / dt
        self.dx, self.dy = nx, ny

    def _hit(self, amount, kind="hit"):
        self.dmg += amount
        self.hits += 1
        self.events.append(kind)

    def _touch(self, x, y, r):
        return (x - self.dx) ** 2 + (y - self.dy) ** 2 <= (r + self.dr) ** 2

    # ── shoot: 총알(돌) ──
    def _init_shoot(self):
        s = self.spec
        self.shots_left = int(s.get("shots", 3))
        self.per_hit = s.get("per_hit", 1)
        self.bspeed = s.get("speed", 320) * self.pspeed
        self.br = s.get("r", 7)
        self.cd_max = s.get("cd", 0.75)
        self.cd = 0.6
        self.tur_u = self.rng.uniform(0, 4 * SIZE)
        self.tur_v = s.get("turret", 150)
        self.bullets = []
        self.tx, self.ty = perimeter_point(self.tur_u)

    def aim_dir(self):
        dx, dy = self.mx - self.tx, self.my - self.ty
        d = math.hypot(dx, dy)
        if d < 1e-6:
            dx, dy, d = SIZE / 2 - self.tx, SIZE / 2 - self.ty, 1.0
            d = math.hypot(dx, dy) or 1.0
        return dx / d, dy / d

    def _step_shoot(self, dt):
        self.tur_u += self.tur_v * dt
        self.tx, self.ty = perimeter_point(self.tur_u)
        self.cd -= dt
        if self.clicks and self.shots_left > 0 and self.cd <= 0:
            ax, ay = self.aim_dir()
            self.bullets.append([self.tx, self.ty, ax * self.bspeed, ay * self.bspeed])
            self.shots_left -= 1
            self.cd = self.cd_max
            self.events.append("fire")
        keep = []
        for b in self.bullets:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if self._touch(b[0], b[1], self.br):
                self._hit(self.per_hit)
                continue
            if -30 <= b[0] <= SIZE + 30 and -30 <= b[1] <= SIZE + 30:
                keep.append(b)
        self.bullets = keep
        if self.shots_left <= 0 and not self.bullets:
            self._finish()

    # ── swarm: 개미 떼 ──
    def _init_swarm(self):
        s = self.spec
        self.ants_total = int(s.get("ants", 6))
        self.ants_spawned = 0
        self.per_hit = s.get("per_hit", 1)
        self.aspeed = s.get("speed", 100) * self.pspeed
        self.ar = s.get("r", 6)
        self.spawn_t = s.get("spawn_t", 1.6)
        self.ants = []

    def _step_swarm(self, dt):
        want = int(self.ants_total * min(1.0, self.t / self.spawn_t) + 0.999)
        while self.ants_spawned < min(want, self.ants_total):
            side = self.rng.randrange(4)
            p = self.rng.uniform(0, SIZE)
            x, y = [(p, 0), (SIZE, p), (p, SIZE), (0, p)][side]
            self.ants.append([x, y, self.rng.uniform(0, 6.28)])
            self.ants_spawned += 1
        keep = []
        for a in self.ants:
            dx, dy = self.mx - a[0], self.my - a[1]
            d = math.hypot(dx, dy) or 1.0
            ang = math.atan2(dy, dx) + math.sin(self.t * 4 + a[2]) * 0.55   # 꿈틀거리는 움직임
            sp = self.aspeed * (0.55 if d < 22 else 1.0)
            a[0] = clamp(a[0] + math.cos(ang) * sp * dt, 0, SIZE)
            a[1] = clamp(a[1] + math.sin(ang) * sp * dt, 0, SIZE)
            if self._touch(a[0], a[1], self.ar):
                self._hit(self.per_hit)
                continue
            keep.append(a)
        self.ants = keep
        if self.ants_spawned >= self.ants_total and not self.ants:
            self._finish()

    # ── zone: 범위 폭격 ──
    def _init_zone(self):
        s = self.spec
        self.z_total = int(s.get("count", 1))
        self.z_placed = 0
        self.z_r = s.get("radius", 60) * (1 + self.mods["atk"])
        self.z_warn = s.get("warn", 0.8) * (1 + self.mods["proj_slow"])   # 시간의 틈: 경고 시간이 길어짐
        self.z_charge = s.get("charge", 2.0)
        self.z_dc = s.get("dc", 3)
        self.z_de = s.get("de", self.z_dc)
        self.z_linger = s.get("linger", 0.0)
        self.z_tick = s.get("tick", 0.5)
        self.z_tickdmg = s.get("tickdmg", 1)
        self.z_cd = 0.0
        self.z_ctimer = 0.0
        self.zones = []     # [x, y, r, state, t, tick_t]  state: 0 경고 / 1 폭발 / 2 안개

    def _step_zone(self, dt):
        self.z_cd -= dt
        if self.z_placed < self.z_total:
            self.z_ctimer += dt
            if self.z_cd <= 0 and (self.clicks or self.z_ctimer >= self.z_charge):
                self.zones.append([self.mx, self.my, self.z_r, 0, 0.0, 0.0])
                self.z_placed += 1
                self.z_ctimer = 0.0
                self.z_cd = 0.45
                self.events.append("fire")
        keep = []
        for z in self.zones:
            z[4] += dt
            if z[3] == 0 and z[4] >= self.z_warn:
                d = math.hypot(self.dx - z[0], self.dy - z[1])
                if d <= z[2] + self.dr:
                    close = 1.0 - min(1.0, d / z[2])
                    amount = int(round(self.z_de + (self.z_dc - self.z_de) * close))
                    self._hit(max(1, amount), "boom")
                else:
                    self.events.append("boom")
                z[3], z[4] = 1, 0.0
            elif z[3] == 1 and z[4] >= 0.3:
                if self.z_linger > 0:
                    z[3], z[4], z[5] = 2, 0.0, 0.0
                else:
                    continue
            elif z[3] == 2:
                z[5] += dt
                if z[5] >= self.z_tick:
                    z[5] = 0.0
                    if math.hypot(self.dx - z[0], self.dy - z[1]) <= z[2] + self.dr * 0.5:
                        self._hit(self.z_tickdmg, "hit")
                if z[4] >= self.z_linger:
                    continue
            keep.append(z)
        self.zones = keep
        if self.z_placed >= self.z_total and not self.zones:
            self._finish()

    # ── chase: 추격 칼날 ──
    def _init_chase(self):
        s = self.spec
        self.per_hit = s.get("per_hit", 2)
        self.c_speed = s.get("speed", 150) * self.pspeed
        self.c_r = s.get("r", 14)
        self.c_cd_max = s.get("cd", 0.9)
        self.c_cd = 0.0
        side = self.rng.randrange(4)
        p = self.rng.uniform(0, SIZE)
        self.cx, self.cy = [(p, 0), (SIZE, p), (p, SIZE), (0, p)][side]
        self.cvx = self.cvy = 0.0

    def _step_chase(self, dt):
        dx, dy = self.mx - self.cx, self.my - self.cy
        d = math.hypot(dx, dy) or 1.0
        wx, wy = dx / d * self.c_speed, dy / d * self.c_speed
        acc = 650.0 * dt
        self.cvx += clamp(wx - self.cvx, -acc, acc)
        self.cvy += clamp(wy - self.cvy, -acc, acc)
        self.cx = clamp(self.cx + self.cvx * dt, 0, SIZE)
        self.cy = clamp(self.cy + self.cvy * dt, 0, SIZE)
        self.c_cd -= dt
        if self.c_cd <= 0 and self._touch(self.cx, self.cy, self.c_r):
            self._hit(self.per_hit)
            self.c_cd = self.c_cd_max

    # ── bounce: 주사위 ──
    def _init_bounce(self):
        s = self.spec
        n = int(s.get("n", 2))
        self.per_hit = s.get("per_hit", 1)
        self.dice_r = s.get("r", 11)
        sp = s.get("speed", 200) * self.pspeed
        self.dice = []
        for _ in range(n):
            a = self.rng.uniform(0, 6.28)
            self.dice.append([self.rng.uniform(60, SIZE - 60), self.rng.uniform(40, SIZE * 0.4),
                              math.cos(a) * sp, math.sin(a) * sp, 0.0])
        if not self.dice:
            self.done = True
            self.end_t = 0.0

    def _step_bounce(self, dt):
        for d in self.dice:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[4] -= dt
            if d[0] < self.dice_r or d[0] > SIZE - self.dice_r:
                d[2] = -d[2]
                d[0] = clamp(d[0], self.dice_r, SIZE - self.dice_r)
            if d[1] < self.dice_r or d[1] > SIZE - self.dice_r:
                d[3] = -d[3]
                d[1] = clamp(d[1], self.dice_r, SIZE - self.dice_r)
            if d[4] <= 0 and self._touch(d[0], d[1], self.dice_r):
                self._hit(self.per_hit)
                d[4] = self.spec.get("cd", 0.9)

    # ── pick: 상자 고르기 ──
    def _init_pick(self):
        s = self.spec
        self.n = int(s.get("n", 2))
        k = int(s.get("k", 1))
        self.danger = set(self.rng.sample(range(self.n), min(k, self.n)))
        self.picked = None
        self.reveal_t = None
        self.time = float(s.get("time", 7.0))

    def pick(self, i):
        if self.mode != "pick" or self.picked is not None or not (0 <= i < self.n):
            return
        self.picked = i
        self.safe = i not in self.danger
        self.reveal_t = self.t
        self.events.append("hit" if not self.safe else "heal")

    def _step_pick(self, dt):
        if self.picked is None and self.t >= self.time:
            self.pick(self.rng.randrange(self.n))      # 시간 초과: 무작위로 골라져요
        if self.reveal_t is not None and self.t - self.reveal_t >= 1.4:
            self._finish()

    # ── 결과 / 화면 데이터 ──
    def result(self):
        cap = self.spec.get("max")
        dmg = min(self.dmg, cap) if cap is not None else self.dmg
        return {"dmg": int(dmg), "hits": int(self.hits), "safe": self.safe}

    def snapshot(self):
        r1 = lambda v: round(v, 1)
        s = {"m": self.mode, "t": round(self.t, 2), "T": self.time, "dmg": self.dmg, "hits": self.hits,
             "done": 1 if self.done else 0, "d": [r1(self.dx), r1(self.dy)], "dr": r1(self.dr),
             "aim": [r1(self.mx), r1(self.my)], "ev": self.events[:]}
        self.events = []
        m = self.mode
        if m == "shoot":
            s.update(tur=[r1(self.tx), r1(self.ty)], br=self.br, left=self.shots_left,
                     b=[[r1(b[0]), r1(b[1])] for b in self.bullets], cd=round(max(0, self.cd), 2))
        elif m == "swarm":
            s.update(a=[[r1(a[0]), r1(a[1])] for a in self.ants], ar=self.ar,
                     left=self.ants_total - self.ants_spawned + len(self.ants))
        elif m == "zone":
            s.update(z=[[r1(z[0]), r1(z[1]), r1(z[2]), z[3], round(z[4], 2)] for z in self.zones],
                     warn=round(self.z_warn, 2), left=self.z_total - self.z_placed, r=r1(self.z_r),
                     ch=round(min(1.0, self.z_ctimer / self.z_charge), 2) if self.z_placed < self.z_total else 1.0)
        elif m == "chase":
            s.update(c=[r1(self.cx), r1(self.cy)], cr=self.c_r)
        elif m == "bounce":
            s.update(dc=[[r1(d[0]), r1(d[1])] for d in self.dice], dcr=self.dice_r)
        elif m == "pick":
            s.update(n=self.n, picked=self.picked, safe=None if self.picked is None else (1 if self.safe else 0),
                     danger=sorted(self.danger) if self.picked is not None else None)
        return s


# ─────────────────────────────────────────────────────────────
# AI 조종 (AI가 공격하거나 피할 때, 그리고 터미널 자동 판정에 사용)
# ─────────────────────────────────────────────────────────────
class AIDefender:
    """가까운 위협에서 멀어지는 방향을 골라 피하는 AI. skill 0~1 (높을수록 반응이 빠르고 정확)"""
    DIRS = [(0, 0)] + [(math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)) for a in range(8)]

    def __init__(self, arena, skill=0.6, seed=1):
        self.a = arena
        self.skill = skill
        self.rng = random.Random(seed)
        self.cool = 0.0
        self.react = 0.30 - 0.22 * skill
        self.cur = (0, 0)

    def _threat(self, px, py, tau):
        a = self.a
        score = 0.0
        m = a.mode
        r = a.dr
        if m == "shoot":
            for b in a.bullets:
                bx, by = b[0] + b[2] * tau, b[1] + b[3] * tau
                d = math.hypot(px - bx, py - by)
                score += max(0.0, 1.0 - d / (a.br + r + 45))
        elif m == "swarm":
            for t in a.ants:
                d = math.hypot(px - t[0], py - t[1])
                score += max(0.0, 1.0 - d / 60) * 0.8
        elif m == "zone":
            for z in a.zones:
                if z[3] == 0 or (z[3] == 2):
                    d = math.hypot(px - z[0], py - z[1])
                    if d < z[2] + 14:
                        score += 2.5 if z[3] == 0 else 0.8
        elif m == "chase":
            d = math.hypot(px - a.cx, py - a.cy)
            score += max(0.0, 1.0 - d / 110) * 2.0
        elif m == "bounce":
            for t in a.dice:
                bx, by = t[0] + t[2] * tau, t[1] + t[3] * tau
                d = math.hypot(px - bx, py - by)
                score += max(0.0, 1.0 - d / 55)
        # 벽 근처 감점
        for edge in (px, SIZE - px, py, SIZE - py):
            if edge < 30:
                score += (30 - edge) / 60
        return score

    def update(self, dt):
        a = self.a
        if a.mode == "pick":
            if a.picked is None and a.t > 1.2 + self.rng.random() * 2:
                a.pick(self.rng.randrange(a.n))
            return
        self.cool -= dt
        if self.cool > 0:
            a.set_def_input(*self.cur)
            return
        self.cool = self.react
        if self.rng.random() < (0.22 - 0.2 * self.skill):    # 가끔 실수
            self.cur = self.rng.choice([(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)])
            a.set_def_input(*self.cur)
            return
        tau = 0.28
        best, bd = 1e9, (0, 0)
        for dx, dy in self.DIRS:
            px = clamp(a.dx + dx * a.dspeed * tau, 0, SIZE)
            py = clamp(a.dy + dy * a.dspeed * tau, 0, SIZE)
            sc = self._threat(px, py, tau) + (0.05 if (dx or dy) else 0.0)
            if sc < best:
                best, bd = sc, (dx, dy)
        self.cur = (int(round(bd[0])), int(round(bd[1])))
        a.set_def_input(*self.cur)


class AIAttacker:
    """상대를 노리는 공격 AI. skill 0~1 (높을수록 정확하고 예측 사격을 해요)"""

    def __init__(self, arena, skill=0.6, seed=2):
        self.a = arena
        self.skill = skill
        self.rng = random.Random(seed)
        self.think = 0.0

    def _target(self, lead):
        a = self.a
        noise = (1.0 - self.skill) * 70
        return (a.dx + a.dvx * lead * self.skill + self.rng.gauss(0, noise),
                a.dy + a.dvy * lead * self.skill + self.rng.gauss(0, noise))

    def update(self, dt):
        a = self.a
        self.think -= dt
        if a.mode in ("pick", "bounce"):
            return
        if self.think > 0:
            return
        self.think = 0.12
        if a.mode == "shoot":
            dist = math.hypot(a.dx - a.tx, a.dy - a.ty)
            tx, ty = self._target(dist / max(a.bspeed, 1))
            a.set_aim(tx, ty)
            if a.cd <= 0.05 and a.shots_left > 0:
                a.click()
        elif a.mode == "swarm":
            tx, ty = self._target(0.6)
            a.set_aim(tx, ty)
        elif a.mode == "zone":
            tx, ty = self._target(a.z_warn)
            a.set_aim(tx, ty)
            if a.z_placed < a.z_total and a.z_ctimer > a.z_charge * (0.35 + 0.35 * self.rng.random()):
                a.click()
        elif a.mode == "chase":
            tx, ty = self._target(0.3)
            a.set_aim(tx, ty)


def auto_resolve(spec, seed=0, mods=None, att_skill=0.55, def_skill=0.55):
    """사람 없이 AI끼리 아레나를 끝까지 돌려 결과를 돌려줍니다 (터미널 버전/상대가 아레나를 못 쓸 때)"""
    ar = Arena(spec, seed, mods)
    att = AIAttacker(ar, att_skill, seed + 1)
    dfn = AIDefender(ar, def_skill, seed + 2)
    for _ in range(int((ar.time + 4) / DT)):
        if ar.done:
            break
        att.update(DT)
        dfn.update(DT)
        ar.step(DT)
    return ar.result()
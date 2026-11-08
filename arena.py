"""한 장 승부 - 실시간 아레나 (공격 카드를 쓰면 열리는 검은 정사각형 필드)

공격하는 쪽은 카드마다 다른 방식(mode)으로 공격을 '조종'하고, 맞는 쪽은 WASD/방향키로 피해요.
화면(tkinter)과 무관한 순수 시뮬레이션이라 창 화면·AI·터미널 자동 판정이 모두 같이 써요.
방식별 조작법은 아래 HELP/CTRL 표에 있고, 카드의 "help": [제목, 공격자, 피하는쪽] 으로 덮어쓸 수 있어요.
모든 공격에 붙이는 변형(spec): twist(reverse/rot/ice/drunk/slow) · tw_at(시작 시각) · fog(시야 반지름)
결과: {dmg: 상대 피해, hits, safe, self: 내가 입는 피해, sheal: 내 회복, fheal: 상대 회복}
"""
import math
import random

SIZE = 600.0          # 아레나 한 변 (논리 좌표)
DT = 1.0 / 60.0       # 시뮬레이션 고정 시간 간격
DEF_R = 9.0           # 피하는 쪽 판정 반지름
DEF_SPEED = 235.0     # 피하는 쪽 기본 이동 속도 (칸/초)
TAU = 2 * math.pi

SHOOTLIKE = ("shoot", "shield", "gamble", "knock")      # 같은 '총알' 엔진을 쓰는 방식들
MODES = SHOOTLIKE + ("swarm", "zone", "rain", "cone", "beam", "chase", "orbit", "duel", "vortex", "warp", "grid",
                     "channel", "bounce", "pick")

# 방식별 안내: (제목, 공격자 설명, 피하는 쪽 설명). 카드의 "help": [제목, 공격자, 피하는쪽] 으로 덮어쓸 수 있어요.
HELP = {
    "shoot":  ("총알 조준", "마우스로 조준선을 맞추고 클릭해서 발사해요. 포탑은 테두리를 따라 계속 움직여요.",
               "WASD/방향키로 이동해 총알을 피하세요. 빨간 조준선이 총알이 날아올 길이에요."),
    "shield": ("발사 vs 방패", "마우스로 조준하고 클릭해서 발사해요. 보라색 관통탄은 방패로 못 막아요!",
               "마우스 방향으로 방패가 향해요. 날아오는 쪽으로 방패를 돌려 막으세요. 막을수록 방패가 금가요."),
    "gamble": ("득실 구슬", "구슬을 쏘면 일부는 초록(상대 회복)이에요. 빨간 구슬만 맞게 쏘세요.",
               "빨간 구슬은 피하고, 초록 구슬은 일부러 먹어서 체력을 회복하세요!"),
    "knock":  ("밀어내기", "맞은 상대는 크게 튕겨 나가요. 벽(가시)에 부딪히게 만들면 큰 피해예요.",
               "총알을 피하세요. 맞더라도 벽에 부딪히기 전에 방향을 틀어 버티세요."),
    "swarm":  ("떼 유인", "마우스 위치로 떼가 모여들어요. 상대 쪽으로 유인하세요.",
               "WASD/방향키로 이동해 몰려오는 떼에 닿지 않게 피하세요."),
    "zone":   ("범위 폭격", "마우스로 위험 구역을 옮기다가 클릭(또는 시간이 되면 자동)으로 확정해요. 잠시 뒤 폭발! 중앙일수록 큰 피해예요.",
               "WASD/방향키로 이동해 빨간 구역 밖으로 벗어나세요."),
    "rain":   ("하늘에서 쏟아짐", "마우스로 떨어뜨릴 지점을 정하고 클릭하면 위에서 한꺼번에 쏟아져요. 바닥의 표식이 착탄 지점이에요.",
               "WASD/방향키로 이동해 바닥 표식(착탄 지점)에서 벗어나세요."),
    "cone":   ("부채꼴 공격", "마우스로 방향을 정하고 클릭하면 부채꼴 경고가 뜨고, 잠시 뒤 터져요. 넓지만 느려요.",
               "WASD/방향키로 이동해 부채꼴 경고 밖으로 벗어나세요."),
    "beam":   ("레이저", "클릭하면 레이저를 충전해서 발사해요. 쏘는 동안 마우스로 천천히 휘두를 수 있어요.",
               "WASD/방향키로 이동해 레이저 선에서 벗어나세요. 닿고 있는 동안 계속 피해를 입어요."),
    "chase":  ("추격", "마우스 위치로 칼날이 쫓아가요. 상대에게 몰아 붙이세요.",
               "WASD/방향키로 이동해 칼날에 닿지 않게 피하세요."),
    "orbit":  ("회전 칼날 구체", "마우스로 공을 움직여요. 공 둘레를 칼날이 360도 돌아요. 클릭하면 역회전하며 잠깐 빨라져요.",
               "WASD/방향키로 이동해 돌아가는 칼날과 공에 닿지 않게 피하세요."),
    "duel":   ("칼싸움", "마우스로 이동하세요(칼은 자동으로 상대를 향해요). 클릭=베기! 상대가 먼저 베면 내가 큰 피해를 받아요.",
               "WASD로 이동하고 클릭/스페이스로 베세요. 상대를 먼저 베면 반격 성공! 동시에 베면 서로 튕겨요."),
    "vortex": ("블랙홀", "마우스로 블랙홀을 움직여요. 상대를 끌어당겨 중심에 가두세요.",
               "WASD/방향키로 블랙홀에서 멀어지세요. 가까울수록 끌려가는 힘이 세져요."),
    "warp":   ("차원문", "클릭한 곳에 차원문이 열려요. 상대가 들어가면 미리 보이는 출구로 순간이동하고, 거기서 폭발해요.",
               "차원문(보라색 원)에 들어가지 마세요. 들어가면 출구로 이동해요 — 폭발 전에 벗어나세요."),
    "grid":   ("심판의 격자", "마우스로 칸을 고르고 클릭하면 그 칸이 잠시 뒤 폭발해요. 상대가 서 있는 칸을 노리세요.",
               "WASD/방향키로 이동해 빨갛게 변한 칸 밖으로 나가세요."),
    "channel": ("치유 의식", "마우스로 의식 원을 옮기고, 클릭하면 그 자리로 순간이동해요. 방해받지 않고 시간이 차면 체력을 회복해요. 상대에게서 멀리!",
                "의식 원 안에 서면 회복이 점점 깎여요. 원을 쫓아가서 방해하세요!"),
    "bounce": ("튕기는 물체", "이번 공격은 알아서 튕겨 다녀요. 지켜보세요.",
               "WASD/방향키로 이동해 튕겨 다니는 물체를 피하세요."),
    "pick":   ("상자 고르기", "상대가 상자를 고르는 걸 지켜보세요. 운이 따라 줘야 해요.",
               "마우스로 상자를 클릭하거나 숫자키(1~)로 고르세요. 위험 상자면 피해, 안전 상자면 회복!"),
}
# 조작 안내: (공격자, 피하는 쪽)
CTRL = {
    "shield": ("🖱 마우스: 조준 / 클릭: 발사", "⌨ WASD: 이동   🖱 마우스: 방패 방향"),
    "duel": ("🖱 마우스: 이동 / 클릭: 베기", "⌨ WASD: 이동   🖱 클릭·스페이스: 베기"),
    "orbit": ("🖱 마우스: 공 이동 / 클릭: 역회전", None),
    "channel": ("🖱 마우스: 의식 원 이동 / 클릭: 순간이동", "⌨ WASD: 이동 (원 안에서 방해!)"),
    "swarm": ("🖱 마우스: 유인 지점", None), "chase": ("🖱 마우스: 방향", None), "vortex": ("🖱 마우스: 블랙홀 이동", None),
    "bounce": ("구경 중…", None), "pick": ("구경 중…", "🖱 클릭 또는 숫자키(1~)로 상자 고르기"),
}
TWIST_TXT = {"reverse": "🙃 조작 반전!", "rot": "🔄 조작이 90도 돌아갔어요!", "ice": "🧊 얼음판! 미끄러져요",
             "drunk": "🍺 비틀비틀 취했어요", "slow": "🐌 몸이 무거워요"}


def help_for(spec):
    h = spec.get("help")
    return tuple(h) if h else HELP[spec["mode"]]


def ctrl_for(spec, me_att):
    c = CTRL.get(spec["mode"], (None, None))[0 if me_att else 1]
    if c:
        return c
    return "🖱 마우스: 조준·위치 / 클릭: 발사·확정" if me_att else "⌨ WASD / 방향키: 이동"


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def adiff(a, b):
    """두 각도의 차이 (-π ~ π)"""
    return (a - b + math.pi) % TAU - math.pi


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


def edge_point(rng):
    side, p = rng.randrange(4), rng.uniform(0, SIZE)
    return [(p, 0), (SIZE, p), (p, SIZE), (0, p)][side]


def seg_dist(px, py, x1, y1, x2, y2):
    """점과 선분 사이의 거리"""
    vx, vy = x2 - x1, y2 - y1
    L = vx * vx + vy * vy
    t = clamp(((px - x1) * vx + (py - y1) * vy) / L, 0.0, 1.0) if L else 0.0
    return math.hypot(px - (x1 + vx * t), py - (y1 + vy * t))


def ray_dist(px, py, ox, oy, ang):
    """점과 (시작점 + 방향) 반직선 사이의 거리"""
    c, s = math.cos(ang), math.sin(ang)
    t = (px - ox) * c + (py - oy) * s
    return math.hypot(px - ox, py - oy) if t < 0 else abs(-(px - ox) * s + (py - oy) * c)


class Arena:
    """아레나 한 판의 상태. step(dt)로 시간을 진행하고 snapshot()으로 화면용 데이터를 얻어요."""

    def __init__(self, spec, seed=0, mods=None):
        self.spec = s = dict(spec)
        self.mode = s["mode"]
        self.impl, self.rng = "shoot" if self.mode in SHOOTLIKE else self.mode, random.Random(seed)
        m = {"dodge": 0.0, "shrink": 0.0, "atk": 0.0, "foe_slow": 0.0, "proj_slow": 0.0}
        m.update(mods or {})
        self.mods, self.t, self.time, self.done = m, 0.0, float(s.get("time", 9.0)), False
        self.dmg = self.hits = 0
        self.sdmg = self.sheal = self.fheal = 0          # 내가 입는 피해 / 내 회복 / 상대 회복
        self.events, self.safe = [], None
        # 피하는 쪽
        self.dx, self.dy = SIZE / 2, SIZE * 0.68
        self.dvx = self.dvy = 0.0
        self.dr = DEF_R * max(0.4, 1 - m["shrink"])
        self.dspeed = DEF_SPEED * (1 + m["dodge"]) * max(0.4, 1 - m["foe_slow"])
        self.in_x = self.in_y = 0
        self.dmx, self.dmy = SIZE / 2, SIZE / 3          # 피하는 쪽의 마우스 (방패 방향 등)
        self.dclicks = 0
        self.dstun, self.dslow = 0.0, 1.0
        self.kv, self.pv, self.iv = [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]   # 밀림 / 끌림 / 얼음판 속도
        self.kwin = 0.0
        # 조작 변형
        self.tw_kind, self.tw_at, self.tw = s.get("twist", ""), s.get("tw_at", 0.0), ""
        self.fog = s.get("fog", 0)
        # 공격하는 쪽
        self.mx, self.my = SIZE / 2, SIZE * 0.3
        self.clicks = 0
        self.pspeed = (1 + m["atk"]) * max(0.3, 1 - m["proj_slow"])   # 공격 투사체/개체 속도 배율
        getattr(self, "_init_" + self.impl)()

    # ── 입력 ──
    def set_def_input(self, ix, iy):
        self.in_x, self.in_y = int(clamp(ix, -1, 1)), int(clamp(iy, -1, 1))

    def set_def_aim(self, x, y):
        self.dmx, self.dmy = clamp(x, 0, SIZE), clamp(y, 0, SIZE)

    def def_click(self):
        self.dclicks += 1

    def set_aim(self, x, y):
        self.mx, self.my = clamp(x, 0, SIZE), clamp(y, 0, SIZE)

    def click(self):
        self.clicks += 1

    def ctrl_for(self, wx, wy):
        """원하는 이동 방향(wx,wy)을 내기 위해 눌러야 할 입력 (조작 변형을 AI가 보정할 때 써요)"""
        if self.tw == "reverse":
            return -wx, -wy
        if self.tw == "rot":
            return wy, -wx
        return wx, wy

    # ── 시간 진행 ──
    def step(self, dt=DT):
        if self.done:
            return
        self.t += dt
        self.tw = self.tw_kind if self.t >= self.tw_at else ""
        if self.mode != "pick":
            self._move_defender(dt)
        getattr(self, "_step_" + self.impl)(dt)
        self.clicks = self.dclicks = 0
        if not self.done and self.t >= self.time:
            self._finish()

    def _finish(self):
        if not self.done:
            self.done = True

    def _move_defender(self, dt):
        ix, iy, tw = self.in_x, self.in_y, self.tw
        if tw == "reverse":
            ix, iy = -ix, -iy
        elif tw == "rot":
            ix, iy = -iy, ix
        if ix and iy:
            ix *= 0.7071
            iy *= 0.7071
        sp = self.dspeed * (0.55 if tw == "slow" else 1.0) * self.dslow
        if self.dstun > 0:
            self.dstun -= dt
            sp = 0.0
        vx, vy = ix * sp, iy * sp
        if tw == "ice":
            k = min(1.0, 1.6 * dt)
            self.iv[0] += (vx - self.iv[0]) * k
            self.iv[1] += (vy - self.iv[1]) * k
            vx, vy = self.iv
        elif tw == "drunk" and sp:
            vx += math.cos(self.t * 1.9) * sp * 0.6
            vy += math.sin(self.t * 2.4 + 1) * sp * 0.6
        k = math.exp(-3.2 * dt)                               # 밀려난 속도는 서서히 줄어요
        self.kv[0] *= k
        self.kv[1] *= k
        vx += self.kv[0] + self.pv[0]
        vy += self.kv[1] + self.pv[1]
        rx, ry = self.dx + vx * dt, self.dy + vy * dt
        nx, ny = clamp(rx, self.dr, SIZE - self.dr), clamp(ry, self.dr, SIZE - self.dr)
        if self.kwin > 0:
            self.kwin -= dt
            if (nx != rx or ny != ry) and math.hypot(*self.kv) > 130:     # 밀려서 벽에 쾅!
                self._hit(self.spec.get("wall", 2), "boom")
                self.kwin, self.kv = 0.0, [0.0, 0.0]
        self.dvx, self.dvy = (nx - self.dx) / dt, (ny - self.dy) / dt
        self.dx, self.dy = nx, ny

    def _hit(self, amount, kind="hit"):
        self.dmg += amount
        self.hits += 1
        self.events.append(kind)

    def _touch(self, x, y, r):
        return (x - self.dx) ** 2 + (y - self.dy) ** 2 <= (r + self.dr) ** 2

    # ── 포탑 (shoot / cone / beam 공용) ──
    def _init_turret(self, v=150):
        self.tur_u, self.tur_v = self.rng.uniform(0, 4 * SIZE), self.spec.get("turret", v)
        self.tx, self.ty = perimeter_point(self.tur_u)
        self.cd_max, self.cd, self.per_hit = self.spec.get("cd", 0.75), 0.6, self.spec.get("per_hit", 1)

    def _turret(self, dt):
        self.tur_u += self.tur_v * dt
        self.tx, self.ty = perimeter_point(self.tur_u)
        self.cd -= dt

    def aim_angle(self, ox=None, oy=None):
        ox, oy = (self.tx, self.ty) if ox is None else (ox, oy)
        dx, dy = self.mx - ox, self.my - oy
        if math.hypot(dx, dy) < 1e-6:
            dx, dy = SIZE / 2 - ox, SIZE / 2 - oy
        return math.atan2(dy, dx)

    def aim_dir(self):
        a = self.aim_angle()
        return math.cos(a), math.sin(a)

    # ── shoot / shield / gamble / knock: 총알 ──
    def _init_shoot(self):
        s = self.spec
        self._init_turret(150)
        self.shots_left, self.bspeed = int(s.get("shots", 3)), s.get("speed", 320) * self.pspeed
        self.br = s.get("r", 7)
        self.bullets = []              # [x, y, vx, vy, 종류(0 일반 / 1 초록(회복) / 2 관통)]
        self.fired, self.heal_amt = 0, s.get("heal", 2)
        if self.mode == "shield":
            self.sh_max = int(s.get("sh_hp", 4))
            self.sh_hp, self.sh_off = self.sh_max, 0.0
            self.shw, self.shr = s.get("sh_w", 0.95), self.dr + 15
            self.sh_ang = 0.0

    def _shield_block(self, b):
        a = math.atan2(b[1] - self.dy, b[0] - self.dx)
        return (math.hypot(b[0] - self.dx, b[1] - self.dy) <= self.shr + self.br and abs(adiff(a, self.sh_ang)) <= self.shw)

    def _step_shoot(self, dt):
        s, mode = self.spec, self.mode
        self._turret(dt)
        if mode == "shield":
            self.sh_ang, self.sh_off = math.atan2(self.dmy - self.dy, self.dmx - self.dx), max(0.0, self.sh_off - dt)
            self.dslow = s.get("slow", 0.7) if self.sh_off <= 0 else 1.0
        if self.clicks and self.shots_left > 0 and self.cd <= 0:
            ax, ay = self.aim_dir()
            self.fired += 1
            kind = 0
            if mode == "gamble" and self.rng.random() < s.get("p_heal", 0.3):
                kind = 1
            elif mode == "shield" and s.get("pierce_every") and self.fired % s["pierce_every"] == 0:
                kind = 2
            self.bullets.append([self.tx, self.ty, ax * self.bspeed, ay * self.bspeed, kind])
            self.shots_left -= 1
            self.cd = self.cd_max
            self.events.append("fire")
        keep = []
        for b in self.bullets:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if mode == "shield" and self.sh_off <= 0 and b[4] != 2 and self._shield_block(b):
                self.events.append("block")
                self.sh_hp -= 1
                if self.sh_hp <= 0:
                    self.sh_hp, self.sh_off = self.sh_max, s.get("sh_break", 2.2)
                    self.events.append("break")
                continue
            if self._touch(b[0], b[1], self.br):
                if b[4] == 1:
                    self.fheal += self.heal_amt
                    self.events.append("heal")
                else:
                    if mode == "knock":
                        L = math.hypot(b[2], b[3]) or 1.0
                        p = s.get("push", 560)
                        self.kv, self.kwin = [b[2] / L * p, b[3] / L * p], 1.0
                    self._hit(self.per_hit)
                continue
            if -30 <= b[0] <= SIZE + 30 and -30 <= b[1] <= SIZE + 30:
                keep.append(b)
        self.bullets = keep
        if self.shots_left <= 0 and not self.bullets:
            self._finish()

    # ── swarm: 떼 ──
    def _init_swarm(self):
        s = self.spec
        self.ants_total, self.ants_spawned, self.per_hit = int(s.get("ants", 6)), 0, s.get("per_hit", 1)
        self.aspeed, self.ar, self.spawn_t = s.get("speed", 100) * self.pspeed, s.get("r", 6), s.get("spawn_t", 1.6)
        self.ants = []

    def _step_swarm(self, dt):
        want = int(self.ants_total * min(1.0, self.t / self.spawn_t) + 0.999)
        while self.ants_spawned < min(want, self.ants_total):
            x, y = edge_point(self.rng)
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
        self.z_total, self.z_placed = int(s.get("count", 1)), 0
        self.z_r = s.get("radius", 60) * (1 + self.mods["atk"])
        self.z_warn = s.get("warn", 0.8) * (1 + self.mods["proj_slow"])   # 시간의 틈: 경고 시간이 길어짐
        self.z_charge, self.z_dc = s.get("charge", 2.0), s.get("dc", 3)
        self.z_de, self.z_linger, self.z_tick = s.get("de", self.z_dc), s.get("linger", 0.0), s.get("tick", 0.5)
        self.z_tickdmg, self.z_cd, self.z_ctimer = s.get("tickdmg", 1), 0.0, 0.0
        self.zones = []     # [x, y, r, state, t, tick_t]  state: 0 경고 / 1 폭발 / 2 안개

    def _step_zone(self, dt):
        self.z_cd -= dt
        if self.z_placed < self.z_total:
            self.z_ctimer += dt
            if self.z_cd <= 0 and (self.clicks or self.z_ctimer >= self.z_charge):
                self.zones.append([self.mx, self.my, self.z_r, 0, 0.0, 0.0])
                self.z_placed += 1
                self.z_ctimer, self.z_cd = 0.0, 0.45
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

    # ── rain: 하늘에서 쏟아짐 (화살비 / 불비 / 운석우) ──
    def _init_rain(self):
        s = self.spec
        self.volleys, self.v_n = int(s.get("volleys", 3)), int(s.get("n", 6))
        self.spread = s.get("spread", 90) * (1 + self.mods["atk"] * 0.5)
        self.fall, self.rr = s.get("fall", 0.8) * (1 + self.mods["proj_slow"]), s.get("r", 22)
        self.per_hit = s.get("per_hit", 1)
        self.slant = s.get("slant", 0.0)             # 0=수직으로 / 양수=비스듬히 (운석)
        self.burn = s.get("burn", 0.0)               # 착탄 뒤 불길이 남는 시간
        self.auto = s.get("auto", 0.0)               # >0: 조종 없이 이 간격마다 상대 쪽으로 자동 낙하 (피하기 힘든 공격)
        self.v_charge = s.get("charge", 2.5)
        self.v_placed, self.v_cd, self.v_t = 0, 0.0, 0.0
        self.arrows = []        # [착탄x, 착탄y, 시간(음수=대기), 낙하시간, 상태 0 낙하/1 착탄/2 불길, 틱]

    def _step_rain(self, dt):
        self.v_cd -= dt
        self.v_t += dt
        if self.v_placed < self.volleys and self.v_cd <= 0:
            if self.auto:
                go = self.v_t >= self.auto
                ax = self.dx + self.dvx * self.fall * 0.7 + self.rng.gauss(0, self.spread * 0.3)
                ay = self.dy + self.dvy * self.fall * 0.7 + self.rng.gauss(0, self.spread * 0.3)
            else:
                go = self.clicks > 0 or self.v_t >= self.v_charge
                ax, ay = self.mx, self.my
            if go:
                for _ in range(self.v_n):
                    a, rad = self.rng.uniform(0, TAU), self.spread * math.sqrt(self.rng.random())
                    self.arrows.append([clamp(ax + math.cos(a) * rad, 0, SIZE), clamp(ay + math.sin(a) * rad, 0, SIZE),
                                        -self.rng.uniform(0, 0.45), self.fall * self.rng.uniform(0.85, 1.15), 0, 0.0])
                self.v_placed += 1
                self.v_t, self.v_cd = 0.0, 0.5
                self.events.append("fire")
        keep = []
        for r in self.arrows:
            r[2] += dt
            if r[4] == 0 and r[2] >= r[3]:
                if self._touch(r[0], r[1], self.rr):
                    self._hit(self.per_hit, "hit")
                else:
                    self.events.append("boom")
                r[4], r[2] = 1, 0.0
            elif r[4] == 1 and r[2] >= 0.25:
                if self.burn > 0:
                    r[4], r[2], r[5] = 2, 0.0, 0.0
                else:
                    continue
            elif r[4] == 2:
                r[5] += dt
                if r[5] >= 0.5:
                    r[5] = 0.0
                    if self._touch(r[0], r[1], self.rr * 0.8):
                        self._hit(1, "hit")
                if r[2] >= self.burn:
                    continue
            keep.append(r)
        self.arrows = keep
        if self.v_placed >= self.volleys and not self.arrows:
            self._finish()

    # ── cone: 부채꼴 ──
    def _init_cone(self):
        s = self.spec
        self._init_turret(110)
        self.shots_left, self.half = int(s.get("shots", 2)), s.get("half", 0.42)
        self.clen = s.get("length", 340) * (1 + self.mods["atk"] * 0.3)
        self.warn, self.de = s.get("warn", 0.75) * (1 + self.mods["proj_slow"]), s.get("de", self.per_hit)
        self.cones = []          # [x, y, 각도, 시간, 상태 0 경고 / 1 폭발]

    def _step_cone(self, dt):
        self._turret(dt)
        if self.clicks and self.shots_left > 0 and self.cd <= 0:
            self.cones.append([self.tx, self.ty, self.aim_angle(), 0.0, 0])
            self.shots_left -= 1
            self.cd = self.cd_max
            self.events.append("fire")
        keep = []
        for c in self.cones:
            c[3] += dt
            if c[4] == 0 and c[3] >= self.warn:
                d = math.hypot(self.dx - c[0], self.dy - c[1])
                off = abs(adiff(math.atan2(self.dy - c[1], self.dx - c[0]), c[2]))
                if d <= self.clen + self.dr and off <= self.half + math.atan2(self.dr, max(d, 1.0)):
                    mid = 1.0 - min(1.0, off / self.half)
                    self._hit(max(1, int(round(self.de + (self.per_hit - self.de) * mid))), "boom")
                else:
                    self.events.append("boom")
                c[4], c[3] = 1, 0.0
            elif c[4] == 1 and c[3] >= 0.4:
                continue
            keep.append(c)
        self.cones = keep
        if self.shots_left <= 0 and not self.cones:
            self._finish()

    # ── beam: 레이저 ──
    def _init_beam(self):
        s = self.spec
        self._init_turret(70)
        self.beams_left, self.bdur, self.bw = int(s.get("shots", 2)), s.get("dur", 2.0), s.get("width", 16)
        self.bwarn, self.swing = s.get("warn", 0.8) * (1 + self.mods["proj_slow"]), s.get("swing", 0.5) * self.pspeed
        self.btick = s.get("tick", 0.25)
        self.beam = None         # [x, y, 각도, 상태 0 충전 / 1 발사, 시간, 틱]

    def _step_beam(self, dt):
        self._turret(dt)
        b = self.beam
        if b is None and self.clicks and self.beams_left > 0 and self.cd <= 0:
            self.beam = b = [self.tx, self.ty, self.aim_angle(), 0, 0.0, 0.0]
            self.beams_left -= 1
            self.events.append("fire")
        if b:
            b[4] += dt
            rate = self.swing * (2.5 if b[3] == 0 else 1.0)
            b[2] += clamp(adiff(self.aim_angle(b[0], b[1]), b[2]), -rate * dt, rate * dt)
            if b[3] == 0 and b[4] >= self.bwarn:
                b[3], b[4], b[5] = 1, 0.0, self.btick
            if b[3] == 1:
                b[5] += dt
                if b[5] >= self.btick and ray_dist(self.dx, self.dy, b[0], b[1], b[2]) <= self.bw / 2 + self.dr:
                    b[5] = 0.0
                    self._hit(self.per_hit, "hit")
                if b[4] >= self.bdur:
                    self.beam, self.cd = None, self.cd_max
        if self.beams_left <= 0 and self.beam is None:
            self._finish()

    # ── chase: 추격 칼날 ──
    def _init_chase(self):
        s = self.spec
        self.per_hit, self.c_speed, self.c_r = s.get("per_hit", 2), s.get("speed", 150) * self.pspeed, s.get("r", 14)
        self.c_cd_max, self.c_cd = s.get("cd", 0.9), 0.0
        self.cx, self.cy = edge_point(self.rng)
        self.cvx = self.cvy = 0.0

    def _step_chase(self, dt):
        dx, dy = self.mx - self.cx, self.my - self.cy
        d = math.hypot(dx, dy) or 1.0
        wx, wy = dx / d * self.c_speed, dy / d * self.c_speed
        acc = 650.0 * dt
        self.cvx += clamp(wx - self.cvx, -acc, acc)
        self.cvy += clamp(wy - self.cvy, -acc, acc)
        self.cx, self.cy = clamp(self.cx + self.cvx * dt, 0, SIZE), clamp(self.cy + self.cvy * dt, 0, SIZE)
        self.c_cd -= dt
        if self.c_cd <= 0 and self._touch(self.cx, self.cy, self.c_r):
            self._hit(self.per_hit)
            self.c_cd = self.c_cd_max

    # ── orbit: 회전 칼날 달린 공 ──
    def _init_orbit(self):
        s = self.spec
        self.ox, self.oy, self.ovx, self.ovy = SIZE / 2, SIZE * 0.2, 0.0, 0.0
        self.o_speed, self.blen = s.get("speed", 170) * self.pspeed, s.get("blade", 90) * (1 + self.mods["atk"] * 0.3)
        self.spin, self.nb = s.get("spin", 5.0) * math.sqrt(self.pspeed), int(s.get("blades", 1))
        self.bw, self.body, self.per_hit = s.get("r", 9), s.get("body", 15), s.get("per_hit", 2)
        self.o_cd_max = s.get("cd", 0.55)
        self.th, self.dirn, self.boost, self.bcd, self.o_cd = 0.0, 1, 0.0, 0.0, 0.0

    def blade_tips(self, th=None):
        th = self.th if th is None else th
        return [(self.ox + math.cos(th + i * TAU / self.nb) * self.blen,
                 self.oy + math.sin(th + i * TAU / self.nb) * self.blen) for i in range(self.nb)]

    def _step_orbit(self, dt):
        dx, dy = self.mx - self.ox, self.my - self.oy
        d = math.hypot(dx, dy) or 1.0
        v = min(self.o_speed, d * 6)
        acc = 900.0 * dt
        self.ovx += clamp(dx / d * v - self.ovx, -acc, acc)
        self.ovy += clamp(dy / d * v - self.ovy, -acc, acc)
        self.ox, self.oy = clamp(self.ox + self.ovx * dt, 0, SIZE), clamp(self.oy + self.ovy * dt, 0, SIZE)
        self.bcd -= dt
        if self.clicks and self.bcd <= 0:
            self.dirn, self.boost, self.bcd = -self.dirn, 0.7, 0.9
            self.events.append("fire")
        self.boost = max(0.0, self.boost - dt)
        self.th += self.spin * (2.2 if self.boost > 0 else 1.0) * self.dirn * dt
        self.o_cd -= dt
        if self.o_cd <= 0:
            hit = self._touch(self.ox, self.oy, self.body) or any(
                seg_dist(self.dx, self.dy, self.ox, self.oy, tx, ty) <= self.bw + self.dr for tx, ty in self.blade_tips())
            if hit:
                self._hit(self.per_hit)
                self.o_cd = self.o_cd_max

    # ── duel: 칼싸움 ──
    def _init_duel(self):
        s = self.spec
        self.ax, self.ay, self.af = SIZE / 2, SIZE * 0.25, math.pi / 2
        self.df, self.reach, self.wind = -math.pi / 2, s.get("reach", 62), s.get("wind", 0.16)
        self.rec, self.stun_t, self.arc = s.get("rec", 0.95), s.get("stun", 1.0), s.get("arc", 0.95)
        self.a_speed, self.per_hit = s.get("a_speed", 175) * self.pspeed, s.get("per_hit", 3)
        self.back = s.get("back", 5)
        self.a_st, self.a_t, self.a_lock, self.a_stun = "idle", 0.0, 0.0, 0.0     # idle / wind / rec / stun
        self.d_st, self.d_t, self.d_lock, self.d_stun = "idle", 0.0, 0.0, 0.0
        self.a_kv, self.time = [0.0, 0.0], float(s.get("time", 10.0))

    def _strike_hits(self, ox, oy, lock, tx, ty, tr):
        d = math.hypot(tx - ox, ty - oy)
        return d <= self.reach + tr and abs(adiff(math.atan2(ty - oy, tx - ox), lock)) <= self.arc

    def _step_duel(self, dt):
        # 칼은 자동으로 상대를 향해요 (베는 중에는 방향 고정)
        if self.a_st != "wind":
            self.af = math.atan2(self.dy - self.ay, self.dx - self.ax)
        if self.d_st != "wind":
            self.df = math.atan2(self.ay - self.dy, self.ax - self.dx)
        # 공격자 이동
        if self.a_st != "stun":
            dx, dy = self.mx - self.ax, self.my - self.ay
            d = math.hypot(dx, dy)
            sp = min(self.a_speed, d * 5) * (0.3 if self.a_st == "wind" else 1.0)
            if d > 1e-6:
                self.ax += dx / d * sp * dt
                self.ay += dy / d * sp * dt
        self.a_kv[0] *= math.exp(-5 * dt)
        self.a_kv[1] *= math.exp(-5 * dt)
        self.ax = clamp(self.ax + self.a_kv[0] * dt, 10, SIZE - 10)
        self.ay, self.dslow = clamp(self.ay + self.a_kv[1] * dt, 10, SIZE - 10), 0.3 if self.d_st == "wind" else 1.0
        # 베기 시작
        if self.clicks and self.a_st == "idle":
            self.a_st, self.a_t, self.a_lock = "wind", 0.0, self.af
            self.events.append("fire")
        if self.dclicks and self.d_st == "idle":
            self.d_st, self.d_t, self.d_lock = "wind", 0.0, self.df
            self.events.append("fire")
        self.a_t += dt
        self.d_t += dt
        a_str = self.a_st == "wind" and self.a_t >= self.wind
        d_str = self.d_st == "wind" and self.d_t >= self.wind
        a_land = a_str and self._strike_hits(self.ax, self.ay, self.a_lock, self.dx, self.dy, self.dr)
        d_land = d_str and self._strike_hits(self.dx, self.dy, self.d_lock, self.ax, self.ay, 10)
        if a_str and d_str and (a_land or d_land):                      # 동시에 베면 칼이 부딪혀요
            for who in "ad":
                self._duel_stun(who, self.stun_t * 0.6)
            self._duel_knock(0.7)
            self.events.append("block")
            a_str = d_str = False
        else:
            if a_land:
                self._hit(self.per_hit, "hit")
                self._duel_stun("d", self.stun_t)
                self._duel_knock(1.0, d_only=True)
            if d_land:
                self.sdmg += self.back
                self.events.append("boom")
                self._duel_stun("a", self.stun_t)
                self._duel_knock(1.0, a_only=True)
        if a_str and self.a_st == "wind":
            self.a_st, self.a_t = "rec", 0.0
        if d_str and self.d_st == "wind":
            self.d_st, self.d_t = "rec", 0.0
        if self.a_st in ("rec", "stun") and self.a_t >= (self.rec if self.a_st == "rec" else self.a_stun):
            self.a_st = "idle"
        if self.d_st in ("rec", "stun") and self.d_t >= (self.rec if self.d_st == "rec" else self.d_stun):
            self.d_st = "idle"

    def _duel_stun(self, who, t):
        if who == "a":
            self.a_st, self.a_t, self.a_stun = "stun", 0.0, t
        else:
            self.d_st, self.d_t, self.d_stun, self.dstun = "stun", 0.0, t, t

    def _duel_knock(self, k, a_only=False, d_only=False):
        ang = math.atan2(self.dy - self.ay, self.dx - self.ax)
        if not a_only:
            self.kv = [math.cos(ang) * 320 * k, math.sin(ang) * 320 * k]
        if not d_only:
            self.a_kv = [-math.cos(ang) * 320 * k, -math.sin(ang) * 320 * k]

    # ── vortex: 블랙홀 ──
    def _init_vortex(self):
        s = self.spec
        self.hx, self.hy = SIZE / 2, SIZE * 0.3
        self.h_speed, self.pull = s.get("speed", 85) * self.pspeed, s.get("pull", 150) * (1 + self.mods["atk"] * 0.3)
        self.rp, self.rc, self.tick = s.get("r_pull", 175), s.get("r_core", 24), s.get("tick", 0.45)
        self.per_hit = s.get("per_hit", 1)
        self.boom = s.get("boom", 0)                  # 마지막에 터지는 폭발 반지름 (0이면 없음)
        self.boom_dmg = s.get("boom_dmg", 4)
        self.tk, self.boomed = 0.0, False

    def _step_vortex(self, dt):
        dx, dy = self.mx - self.hx, self.my - self.hy
        d = math.hypot(dx, dy) or 1.0
        v = min(self.h_speed, d * 4)
        self.hx, self.hy = clamp(self.hx + dx / d * v * dt, 0, SIZE), clamp(self.hy + dy / d * v * dt, 0, SIZE)
        gx, gy = self.hx - self.dx, self.hy - self.dy
        g = math.hypot(gx, gy) or 1.0
        f = self.pull * (1 - g / self.rp) if g < self.rp else 0.0
        self.pv = [gx / g * f, gy / g * f]
        if g <= self.rc + self.dr * 0.6:
            self.tk += dt
            if self.tk >= self.tick:
                self.tk = 0.0
                self._hit(self.per_hit, "hit")
        if self.boom and not self.boomed and self.t >= self.time - 0.35:
            self.boomed = True
            if g <= self.boom + self.dr:
                self._hit(self.boom_dmg, "boom")
            else:
                self.events.append("boom")

    # ── warp: 차원문 ──
    def _init_warp(self):
        s = self.spec
        self.w_total = int(s.get("portals", 3))
        self.w_placed, self.w_cd = 0, 0.0
        self.pr, self.er = s.get("r", 44), s.get("exit_r", 62)
        self.wwarn, self.life = s.get("warn", 0.9) * (1 + self.mods["proj_slow"]), s.get("life", 6.0)
        self.per_hit = s.get("per_hit", 3)
        self.portals = []        # [입구x, 입구y, 출구x, 출구y, 나이]
        self.blasts = []         # [x, y, 시간]

    def _step_warp(self, dt):
        self.w_cd -= dt
        if self.clicks and self.w_placed < self.w_total and self.w_cd <= 0:
            ex, ey = self.mx, self.my
            for _ in range(30):
                x, y = self.rng.uniform(70, SIZE - 70), self.rng.uniform(70, SIZE - 70)
                if math.hypot(x - ex, y - ey) >= 200 and math.hypot(x - self.dx, y - self.dy) >= 110:
                    break
            self.portals.append([ex, ey, x, y, 0.0])
            self.w_placed += 1
            self.w_cd = 0.6
            self.events.append("fire")
        keep = []
        for p in self.portals:
            p[4] += dt
            if p[4] >= 0.35 and self._touch(p[0], p[1], self.pr):           # 순간이동!
                self.dx, self.dy = clamp(p[2], self.dr, SIZE - self.dr), clamp(p[3], self.dr, SIZE - self.dr)
                self.kv, self.iv = [0.0, 0.0], [0.0, 0.0]
                self.blasts.append([p[2], p[3], 0.0])
                self.events.append("warp")
                continue
            if p[4] < self.life:
                keep.append(p)
        self.portals = keep
        nb = []
        for b in self.blasts:
            b[2] += dt
            if b[2] >= self.wwarn:
                if self._touch(b[0], b[1], self.er):
                    self._hit(self.per_hit, "boom")
                else:
                    self.events.append("boom")
                continue
            nb.append(b)
        self.blasts = nb
        if self.w_placed >= self.w_total and not self.portals and not self.blasts:
            self._finish()

    # ── grid: 심판의 격자 ──
    def _init_grid(self):
        s = self.spec
        self.gn = int(s.get("n", 3))
        self.cs, self.g_total = SIZE / self.gn, int(s.get("shots", 6))
        self.g_placed, self.g_cd = 0, 0.0
        self.gwarn, self.per_hit = s.get("warn", 1.0) * (1 + self.mods["proj_slow"]), s.get("per_hit", 2)
        self.auto = s.get("auto", 0)                  # >0: 조종 없이 한꺼번에 N칸만 남기고 전부 심판 (피하기 힘든 공격)
        self.waves = int(s.get("waves", 2))
        self.wave_t, self.waves_done = 0.6, 0
        self.cells = []          # [ix, iy, 시간, 상태 0 경고 / 1 폭발]

    def cell_hits(self, ix, iy, x, y, r):
        cx, cy = clamp(x, ix * self.cs, (ix + 1) * self.cs), clamp(y, iy * self.cs, (iy + 1) * self.cs)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    def _arm(self, ix, iy):
        if not any(c[0] == ix and c[1] == iy and c[3] == 0 for c in self.cells):
            self.cells.append([ix, iy, 0.0, 0])
            self.events.append("fire")

    def _step_grid(self, dt):
        self.g_cd -= dt
        if self.auto:
            if self.waves_done < self.waves and self.t >= self.wave_t and not any(c[3] == 0 for c in self.cells):
                allc = [(i, j) for i in range(self.gn) for j in range(self.gn)]
                safe = set(self.rng.sample(allc, min(self.auto, len(allc))))
                for i, j in allc:
                    if (i, j) not in safe:
                        self._arm(i, j)
                self.waves_done += 1
                self.wave_t = self.t + 0.5
        elif self.clicks and self.g_placed < self.g_total and self.g_cd <= 0:
            self._arm(int(clamp(self.mx // self.cs, 0, self.gn - 1)), int(clamp(self.my // self.cs, 0, self.gn - 1)))
            self.g_placed += 1
            self.g_cd = 0.15
        keep = []
        for c in self.cells:
            c[2] += dt
            if c[3] == 0 and c[2] >= self.gwarn:
                if self.cell_hits(c[0], c[1], self.dx, self.dy, self.dr * 0.7):
                    self._hit(self.per_hit, "boom")
                else:
                    self.events.append("boom")
                c[3], c[2] = 1, 0.0
            elif c[3] == 1 and c[2] >= 0.35:
                continue
            keep.append(c)
        self.cells = keep
        if (self.waves_done >= self.waves if self.auto else self.g_placed >= self.g_total) and not self.cells:
            self._finish()

    # ── channel: 치유 의식 ──
    def _init_channel(self):
        s = self.spec
        self.chx, self.chy = SIZE / 2, SIZE * 0.3
        self.chr, self.ch_speed = s.get("r", 62) * (1 + self.mods["atk"] * 0.3), s.get("speed", 95) * self.pspeed
        self.need, self.ch_heal, self.drain = s.get("need", 6.0), s.get("heal", 8), s.get("drain", 1.8)
        self.tickdmg = s.get("tick", 0)
        self.prog, self.tk, self.inside = 0.0, 0.0, False
        self.blink_cd_max, self.blink_cd = s.get("blink", 2.0), 0.0
        self.time = float(s.get("time", 10.0))

    def _step_channel(self, dt):
        self.blink_cd -= dt
        if self.clicks and self.blink_cd <= 0:                  # 클릭: 의식 원이 그 자리로 순간이동!
            self.chx, self.chy = clamp(self.mx, 40, SIZE - 40), clamp(self.my, 40, SIZE - 40)
            self.blink_cd = self.blink_cd_max
            self.events.append("warp")
        dx, dy = self.mx - self.chx, self.my - self.chy
        d = math.hypot(dx, dy) or 1.0
        v = min(self.ch_speed, d * 4)
        self.chx = clamp(self.chx + dx / d * v * dt, 40, SIZE - 40)
        self.chy = clamp(self.chy + dy / d * v * dt, 40, SIZE - 40)
        self.inside = math.hypot(self.dx - self.chx, self.dy - self.chy) <= self.chr + self.dr * 0.5
        if self.inside:
            self.prog = max(0.0, self.prog - self.drain * dt)
            if self.tickdmg:
                self.tk += dt
                if self.tk >= 0.6:
                    self.tk = 0.0
                    self._hit(self.tickdmg, "hit")
        else:
            self.prog = min(self.need, self.prog + dt)
        self.sheal = int(round(self.ch_heal * self.prog / self.need))
        if self.prog >= self.need:
            self._finish()

    # ── bounce: 튕기는 물체 ──
    def _init_bounce(self):
        s = self.spec
        n = int(s.get("n", 2))
        self.per_hit, self.dice_r = s.get("per_hit", 1), s.get("r", 11)
        sp = s.get("speed", 200) * self.pspeed
        self.dice = []
        for _ in range(n):
            a = self.rng.uniform(0, 6.28)
            self.dice.append([self.rng.uniform(60, SIZE - 60), self.rng.uniform(40, SIZE * 0.4),
                              math.cos(a) * sp, math.sin(a) * sp, 0.0])
        if not self.dice:
            self.done = True

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
        self.danger, self.picked, self.reveal_t = set(self.rng.sample(range(self.n), min(k, self.n))), None, None
        self.time = float(s.get("time", 7.0))

    def pick(self, i):
        if self.mode != "pick" or self.picked is not None or not (0 <= i < self.n):
            return
        self.picked, self.safe, self.reveal_t = i, i not in self.danger, self.t
        self.events.append("hit" if not self.safe else "heal")

    def _step_pick(self, dt):
        if self.picked is None and self.t >= self.time:
            self.pick(self.rng.randrange(self.n))      # 시간 초과: 무작위로 골라져요
        if self.reveal_t is not None and self.t - self.reveal_t >= 1.4:
            self._finish()

    # ── 결과 / 화면 데이터 ──
    def result(self):
        s = self.spec
        cap = s.get("max")
        r = {"dmg": int(min(self.dmg, cap) if cap is not None else self.dmg), "hits": int(self.hits), "safe": self.safe}
        if self.sdmg:
            r["self"] = int(min(self.sdmg, s.get("max_self", 99)))
        if self.sheal:
            r["sheal"] = int(self.sheal)
        if self.fheal:
            r["fheal"] = int(min(self.fheal, s.get("max_fheal", 99)))
        return r

    def snapshot(self):
        r1 = lambda v: round(v, 1)
        s = {"m": self.mode, "t": round(self.t, 2), "T": self.time, "dmg": self.dmg, "hits": self.hits,
             "done": 1 if self.done else 0, "d": [r1(self.dx), r1(self.dy)], "dr": r1(self.dr),
             "aim": [r1(self.mx), r1(self.my)], "da": [r1(self.dmx), r1(self.dmy)], "sp": r1(self.dspeed),
             "ev": self.events[:], "tw": self.tw, "fog": self.fog,
             "np": 1 if (self.tw or self.dstun > 0 or self.mode in ("knock", "vortex", "warp", "duel")
                         or math.hypot(*self.kv) > 5) else 0}
        self.events = []
        m, k = self.impl, self.mode
        if m == "shoot":
            s.update(tur=[r1(self.tx), r1(self.ty)], br=self.br, left=self.shots_left, cd=round(max(0, self.cd), 2),
                     b=[[r1(b[0]), r1(b[1]), b[4], round(math.atan2(b[3], b[2]), 2)] for b in self.bullets])
            if k == "shield":
                s["sh"] = [round(self.sh_ang, 2), self.shw, r1(self.shr), 0 if self.sh_off > 0 else 1,
                           round(self.sh_hp / self.sh_max, 2)]
        elif m == "swarm":
            s.update(a=[[r1(a[0]), r1(a[1])] for a in self.ants], ar=self.ar,
                     left=self.ants_total - self.ants_spawned + len(self.ants))
        elif m == "zone":
            s.update(z=[[r1(z[0]), r1(z[1]), r1(z[2]), z[3], round(z[4], 2)] for z in self.zones],
                     warn=round(self.z_warn, 2), left=self.z_total - self.z_placed, r=r1(self.z_r),
                     ch=round(min(1.0, self.z_ctimer / self.z_charge), 2) if self.z_placed < self.z_total else 1.0)
        elif m == "rain":
            s.update(rn=[[r1(r[0]), r1(r[1]), round(max(0.0, r[2]) / r[3], 2) if r[4] == 0 else round(r[2], 2), r[4]]
                         for r in self.arrows], rr=self.rr, slant=self.slant, left=self.volleys - self.v_placed,
                     r=r1(self.spread), auto=1 if self.auto else 0,
                     ch=round(min(1.0, self.v_t / self.v_charge), 2) if self.v_placed < self.volleys else 1.0)
        elif m == "cone":
            s.update(tur=[r1(self.tx), r1(self.ty)], left=self.shots_left, half=self.half, cl=r1(self.clen),
                     warn=round(self.warn, 2), cn=[[r1(c[0]), r1(c[1]), round(c[2], 3), round(c[3], 2), c[4]] for c in self.cones],
                     aa=round(self.aim_angle(), 3))
        elif m == "beam":
            b = self.beam
            s.update(tur=[r1(self.tx), r1(self.ty)], left=self.beams_left + (1 if b else 0), bw=self.bw,
                     warn=round(self.bwarn, 2), aa=round(self.aim_angle(), 3),
                     bm=None if not b else [r1(b[0]), r1(b[1]), round(b[2], 3), b[3], round(b[4], 2)])
        elif m == "chase":
            s.update(c=[r1(self.cx), r1(self.cy)], cr=self.c_r)
        elif m == "orbit":
            s.update(o=[r1(self.ox), r1(self.oy)], th=round(self.th, 3), bl=r1(self.blen), nb=self.nb, bw=self.bw,
                     body=self.body, bst=1 if self.boost > 0 else 0)
        elif m == "duel":
            code = {"idle": 0, "wind": 1, "rec": 2, "stun": 3}
            s.update(a=[r1(self.ax), r1(self.ay)], af=round(self.af, 3), ast=code[self.a_st],
                     ap=round(min(1.0, self.a_t / self.wind), 2) if self.a_st == "wind" else 0,
                     df=round(self.df, 3), dst=code[self.d_st],
                     dp=round(min(1.0, self.d_t / self.wind), 2) if self.d_st == "wind" else 0,
                     reach=self.reach, arc=self.arc, al=round(self.a_lock, 3), dl=round(self.d_lock, 3))
        elif m == "vortex":
            s.update(h=[r1(self.hx), r1(self.hy)], rp=self.rp, rc=self.rc, boom=self.boom,
                     bp=round(clamp((self.t - (self.time - 1.6)) / 1.25, 0, 1), 2) if self.boom else 0)
        elif m == "warp":
            s.update(pt=[[r1(p[0]), r1(p[1]), r1(p[2]), r1(p[3]), round(p[4], 2)] for p in self.portals], pr=self.pr,
                     er=self.er, bl=[[r1(b[0]), r1(b[1]), round(b[2], 2)] for b in self.blasts],
                     warn=round(self.wwarn, 2), left=self.w_total - self.w_placed)
        elif m == "grid":
            s.update(gc=[[c[0], c[1], round(c[2], 2), c[3]] for c in self.cells], gn=self.gn, warn=round(self.gwarn, 2),
                     left=(self.waves - self.waves_done) if self.auto else self.g_total - self.g_placed)
        elif m == "channel":
            s.update(ch=[r1(self.chx), r1(self.chy), r1(self.chr)], pg=round(self.prog / self.need, 3),
                     inn=1 if self.inside else 0, heal=self.ch_heal, bk=round(max(0.0, self.blink_cd), 2))
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
    """위협에서 멀어지는 방향을 골라 피하는 AI. skill 0~1 (높을수록 반응이 빠르고 정확)"""
    DIRS = [(0, 0)] + [(math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)) for a in range(8)]

    def __init__(self, arena, skill=0.6, seed=1):
        self.a, self.skill, self.rng, self.cool = arena, skill, random.Random(seed), 0.0
        self.react, self.cur = 0.30 - 0.22 * skill, (0, 0)

    def _threat(self, px, py, tau):
        a = self.a
        score = 0.0
        m, k = a.impl, a.mode
        r = a.dr
        if m == "shoot":
            for b in a.bullets:
                bx, by = b[0] + b[2] * tau, b[1] + b[3] * tau
                f = max(0.0, 1.0 - math.hypot(px - bx, py - by) / (a.br + r + 45))
                if b[4] == 1:
                    score -= 0.9 * f                           # 초록 구슬은 먹고 싶어요
                elif k == "shield" and b[4] == 0 and a.sh_off <= 0:
                    score += 0.25 * f                          # 방패로 막을 수 있는 건 덜 무서워요
                else:
                    score += f
        elif m == "swarm":
            for t in a.ants:
                score += max(0.0, 1.0 - math.hypot(px - t[0], py - t[1]) / 60) * 0.8
        elif m == "zone":
            for z in a.zones:
                if z[3] in (0, 2) and math.hypot(px - z[0], py - z[1]) < z[2] + 14:
                    score += 2.5 if z[3] == 0 else 0.8
        elif m == "rain":
            for z in a.arrows:
                if z[4] != 1 and math.hypot(px - z[0], py - z[1]) < a.rr + 14:
                    score += 2.0 if z[4] == 0 else 0.8
        elif m == "cone":
            for c in a.cones:
                if c[4] == 0:
                    d = math.hypot(px - c[0], py - c[1])
                    if d <= a.clen + 20 and abs(adiff(math.atan2(py - c[1], px - c[0]), c[2])) <= a.half + 0.2:
                        score += 2.5
        elif m == "beam":
            b = a.beam
            if b:                                              # 선에서 멀찍이 벗어나야 다시 안 닿아요
                score += max(0.0, 1.0 - ray_dist(px, py, b[0], b[1], b[2]) / (a.bw / 2 + r + 70)) * (2.5 if b[3] == 1 else 1.2)
        elif m == "chase":
            score += max(0.0, 1.0 - math.hypot(px - a.cx, py - a.cy) / 110) * 2.0
        elif m == "orbit":
            for tx, ty in a.blade_tips(a.th + a.spin * a.dirn * tau):
                ox, oy = a.ox + a.ovx * tau, a.oy + a.ovy * tau
                score += max(0.0, 1.0 - seg_dist(px, py, ox, oy, tx, ty) / (a.bw + r + 28)) * 1.6
            score += max(0.0, 1.0 - math.hypot(px - a.ox, py - a.oy) / (a.blen + 70)) * 1.4   # 칼날이 닿기 전부터 멀리
        elif m == "vortex":
            d = math.hypot(px - a.hx, py - a.hy)
            score += max(0.0, 1.0 - d / a.rp) * 1.5 + (2.0 if d < a.rc + 12 else 0.0)
            if a.boom and a.t >= a.time - 1.7 and d < a.boom + 20:
                score += 2.0
        elif m == "warp":
            for p in a.portals:
                if math.hypot(px - p[0], py - p[1]) < a.pr + 18:
                    score += 3.0
            for b in a.blasts:
                if math.hypot(px - b[0], py - b[1]) < a.er + 14:
                    score += 2.5
        elif m == "grid":
            for c in a.cells:
                if c[3] == 0 and a.cell_hits(c[0], c[1], px, py, r * 0.7 + 4):
                    score += 2.5
        elif m == "bounce":
            for t in a.dice:
                bx, by = t[0] + t[2] * tau, t[1] + t[3] * tau
                score += max(0.0, 1.0 - math.hypot(px - bx, py - by) / 55)
        for edge in (px, SIZE - px, py, SIZE - py):             # 벽 근처 감점
            if edge < 30:
                score += (30 - edge) / 60
        if m in ("orbit", "vortex", "beam", "cone"):            # 쫓기는 방식에선 구석에 몰리지 않게 넓은 곳으로
            score += 0.35 * math.hypot(px - SIZE / 2, py - SIZE / 2) / SIZE * (1.0 if score > 0.2 else 0.3)
        return score

    def _goal(self):
        """(x, y, 가중치): 위협 피하기 말고 향하고 싶은 곳이 있으면"""
        a = self.a
        if a.impl == "channel":
            return a.chx, a.chy, 3.0
        if a.impl == "grid":
            if any(c[3] == 0 and a.cell_hits(c[0], c[1], a.dx, a.dy, a.dr) for c in a.cells):
                best = None
                for i in range(a.gn):
                    for j in range(a.gn):
                        if not any(c[3] == 0 and c[0] == i and c[1] == j for c in a.cells):
                            cx, cy = (i + 0.5) * a.cs, (j + 0.5) * a.cs
                            d = math.hypot(cx - a.dx, cy - a.dy)
                            if best is None or d < best[0]:
                                best = (d, cx, cy)
                if best:
                    return best[1], best[2], 3.0
        return None

    def _set(self, wx, wy):
        self.cur = tuple(int(round(v)) for v in self.a.ctrl_for(wx, wy))
        self.a.set_def_input(*self.cur)

    def _duel(self, dt):
        a = self.a
        self.cool -= dt
        if self.cool > 0:
            a.set_def_input(*self.cur)
            return
        self.cool = 0.07
        dist = math.hypot(a.ax - a.dx, a.ay - a.dy) or 1.0
        ux, uy = (a.ax - a.dx) / dist, (a.ay - a.dy) / dist
        if a.a_st == "wind" and dist < a.reach * 1.6 and self.rng.random() < 0.3 + 0.6 * self.skill:
            wx, wy = -ux, -uy                                  # 상대가 베려 하면 물러나요
        elif a.d_st == "idle" and dist > a.reach * 0.9:
            wx, wy = ux, uy
        elif dist < a.reach * 0.55:
            wx, wy = -ux * 0.5, -uy * 0.5
        else:
            wx, wy = 0.0, 0.0
        if a.d_st == "idle" and dist <= a.reach * 0.95 and a.a_st != "wind" and self.rng.random() < 0.2 + 0.35 * self.skill:
            a.def_click()
        if wx or wy:
            best = max(self.DIRS[1:], key=lambda v: v[0] * wx + v[1] * wy)
            self._set(*best)
        else:
            self._set(0, 0)

    def update(self, dt):
        a = self.a
        if a.mode == "pick":
            if a.picked is None and a.t > 1.2 + self.rng.random() * 2:
                a.pick(self.rng.randrange(a.n))
            return
        if a.mode == "duel":
            self._duel(dt)
            return
        if a.mode == "shield":                                 # 방패는 가장 위험한 총알 쪽으로
            tgt = None
            for b in a.bullets:
                if b[4] == 0:
                    d = math.hypot(b[0] - a.dx, b[1] - a.dy)
                    if tgt is None or d < tgt[0]:
                        tgt = (d, b[0], b[1])
            a.set_def_aim(*(tgt[1:] if tgt else (a.tx, a.ty)))
        self.cool -= dt
        if self.cool > 0:
            a.set_def_input(*self.cur)
            return
        self.cool = self.react
        if self.rng.random() < (0.22 - 0.2 * self.skill):    # 가끔 실수
            self._set(*self.rng.choice([(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]))
            return
        tau = 0.28
        goal = self._goal()
        best, bd = 1e9, (0, 0)
        for dx, dy in self.DIRS:
            px = clamp(a.dx + dx * a.dspeed * tau, 0, SIZE)
            py = clamp(a.dy + dy * a.dspeed * tau, 0, SIZE)
            sc = self._threat(px, py, tau) + (0.05 if (dx or dy) else 0.0)
            if goal:
                sc += goal[2] * math.hypot(goal[0] - px, goal[1] - py) / SIZE
            if sc < best:
                best, bd = sc, (dx, dy)
        self._set(*bd)


class AIAttacker:
    """상대를 노리는 공격 AI. skill 0~1 (높을수록 정확하고 예측 사격을 해요)"""

    def __init__(self, arena, skill=0.6, seed=2):
        self.a, self.skill, self.rng, self.think = arena, skill, random.Random(seed), 0.0

    def _target(self, lead):
        a = self.a
        noise = (1.0 - self.skill) * 70
        return (a.dx + a.dvx * lead * self.skill + self.rng.gauss(0, noise),
                a.dy + a.dvy * lead * self.skill + self.rng.gauss(0, noise))

    def update(self, dt):
        a = self.a
        self.think -= dt
        m = a.impl
        if m in ("pick", "bounce"):
            return
        if self.think > 0:
            return
        self.think = 0.07 if m == "duel" else 0.12
        if m == "shoot":
            tx, ty = self._target(math.hypot(a.dx - a.tx, a.dy - a.ty) / max(a.bspeed, 1))
            a.set_aim(tx, ty)
            if a.cd <= 0.05 and a.shots_left > 0:
                a.click()
        elif m == "cone":
            a.set_aim(*self._target(a.warn))
            if a.cd <= 0.05 and a.shots_left > 0:
                a.click()
        elif m == "beam":
            a.set_aim(*self._target(0.4))
            if a.beam is None and a.cd <= 0.05 and a.beams_left > 0:
                a.click()
        elif m in ("swarm", "vortex"):
            a.set_aim(*self._target(0.6 if m == "swarm" else 0.3))
        elif m == "chase":
            a.set_aim(*self._target(0.3))
        elif m == "zone":
            a.set_aim(*self._target(a.z_warn))
            if a.z_placed < a.z_total and a.z_ctimer > a.z_charge * (0.35 + 0.35 * self.rng.random()):
                a.click()
        elif m == "rain":
            if not a.auto:
                a.set_aim(*self._target(a.fall))
                if a.v_placed < a.volleys and a.v_t > a.v_charge * (0.3 + 0.3 * self.rng.random()):
                    a.click()
        elif m == "orbit":
            a.set_aim(*self._target(0.25))
            if math.hypot(a.ox - a.dx, a.oy - a.dy) < a.blen * 1.4 and self.rng.random() < 0.12:
                a.click()
        elif m == "duel":
            dist = math.hypot(a.ax - a.dx, a.ay - a.dy) or 1.0
            ux, uy = (a.dx - a.ax) / dist, (a.dy - a.ay) / dist
            a.set_aim(a.dx - ux * a.reach * 0.75, a.dy - uy * a.reach * 0.75)
            if a.a_st == "idle" and dist <= a.reach * 0.95 and a.d_st != "wind" and self.rng.random() < 0.25 + 0.4 * self.skill:
                a.click()
            elif a.a_st == "idle" and dist <= a.reach * 0.95 and self.rng.random() < 0.08:
                a.click()
        elif m == "warp":
            a.set_aim(*self._target(0.5))
            if a.w_placed < a.w_total and a.w_cd <= 0 and self.rng.random() < 0.5:
                a.click()
        elif m == "grid":
            if not a.auto:
                a.set_aim(*self._target(0.4))
                if a.g_placed < a.g_total and a.g_cd <= 0:
                    a.click()
        elif m == "channel":                                   # 상대에게서 가장 먼 곳으로 도망 다니고, 가까워지면 순간이동
            far = max([(110, 110), (490, 110), (110, 490), (490, 490)], key=lambda c: math.hypot(c[0] - a.dx, c[1] - a.dy))
            a.set_aim(far[0] + self.rng.gauss(0, 20), far[1] + self.rng.gauss(0, 20))
            if a.blink_cd <= 0 and math.hypot(a.chx - a.dx, a.chy - a.dy) < a.chr * 1.8:
                a.click()


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

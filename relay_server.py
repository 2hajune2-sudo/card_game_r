#!/usr/bin/env python3
"""한 장 승부 - 방 번호 중계 서버

방장이 '방 만들기'를 누르면 이 서버가 5자리 무작위 방 번호(예: 73945)를 만들어 주고,
참가자가 같은 번호를 입력하면 두 사람을 이어 줍니다. 이어진 뒤에는 한쪽이 보낸 메시지를
그대로 상대에게 전달만 하므로(게임 규칙은 방장 컴퓨터가 계산) 서버는 가볍고 게임 내용을 몰라요.

실행:   python relay_server.py [포트]        (기본 포트 5051, 파이썬 3.8+, 설치할 것 없음)
필요:   게임을 하는 사람들이 이 컴퓨터의 주소:포트 로 접속할 수 있어야 해요.
        - 같은 와이파이/집 안: 서버를 켠 PC의 IP (예: 192.168.0.12:5051)
        - 인터넷: 공개 주소가 있는 PC/서버(VPS, 클라우드)에서 켜고 포트를 열어 주세요.
게임 화면의 '서버 주소' 칸에 그 주소를 한 번만 적어 두면 저장돼요.

프로토콜 (한 줄에 JSON 하나):
  클라 → 서버   {"t":"r_create"}              방 만들기       → {"t":"r_room","code":"73945"}
                {"t":"r_join","code":"73945"}  방 참가         → 두 사람 모두 {"t":"r_paired","role":"host"|"guest"}
  이어진 뒤      그 외 모든 줄은 상대에게 그대로 전달
  서버 → 클라   {"t":"r_err","msg":"..."} 오류 / {"t":"r_left"} 상대가 나감
"""
import json
import random
import socket
import sys
import threading
import time

MAX_LINE = 262144            # 한 줄 최대 크기 (게임 메시지는 수 KB)
MAX_ROOMS = 2000
ROOM_WAIT = 20 * 60          # 아무도 안 들어오는 방은 20분 뒤 닫아요
HANDSHAKE = 15               # 연결 후 첫 요청까지 기다리는 시간(초)
JOIN_TRIES = 12              # 같은 주소에서 1분에 번호 맞춰 보기 시도 한도 (번호 무작위 대입 방지)

lock = threading.Lock()
rooms = {}                   # 번호 → Room
tries = {}                   # 주소 → [시각...]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Peer:
    def __init__(self, sock, addr):
        self.sock, self.addr = sock, addr
        self.buf = b""
        self.other = None
        self.room = None
        self.wlock = threading.Lock()

    def send(self, obj):
        self.send_raw((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def send_raw(self, data):
        try:
            with self.wlock:
                self.sock.sendall(data)
        except OSError:
            pass

    def lines(self):
        """한 줄씩 읽어 주는 제너레이터 (연결이 끊기면 끝)"""
        while True:
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                if line.strip():
                    yield line
            if len(self.buf) > MAX_LINE:
                return
            try:
                data = self.sock.recv(65536)
            except (OSError, socket.timeout):
                return
            if not data:
                return
            self.buf += data

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Room:
    def __init__(self, code, host):
        self.code, self.host, self.guest, self.t = code, host, None, time.time()


def new_code():
    for _ in range(200):
        c = "%05d" % random.randint(0, 99999)
        if c not in rooms:
            return c
    return None


def too_many_tries(addr):
    now = time.time()
    with lock:
        lst = [t for t in tries.get(addr, []) if now - t < 60]
        lst.append(now)
        tries[addr] = lst
        return len(lst) > JOIN_TRIES


def drop(peer):
    """연결이 끊긴 사람을 방에서 빼고 상대에게 알려요"""
    with lock:
        room, other = peer.room, peer.other
        if room and rooms.get(room.code) is room:
            if room.guest is None or other is None:       # 아직 혼자였으면 방 삭제
                del rooms[room.code]
                log("방 닫힘", room.code)
            elif peer is room.host or peer is room.guest:
                del rooms[room.code]
                log("방 종료", room.code)
        peer.room = peer.other = None
    if other:
        other.send({"t": "r_left"})
        other.other = None
        other.close()
    peer.close()


def serve(peer):
    peer.sock.settimeout(HANDSHAKE)
    try:
        first = next(peer.lines(), None)
        if first is None:
            return peer.close()
        try:
            req = json.loads(first.decode("utf-8"))
        except ValueError:
            return peer.close()
        t = req.get("t")
        if t == "r_create":
            with lock:
                if len(rooms) >= MAX_ROOMS:
                    peer.send({"t": "r_err", "msg": "서버가 꽉 찼어요. 잠시 뒤에 다시 해 주세요."})
                    return peer.close()
                code = new_code()
                room = Room(code, peer)
                rooms[code] = room
                peer.room = room
            peer.send({"t": "r_room", "code": code})
            log("방 생성", code, peer.addr[0])
        elif t == "r_join":
            code = str(req.get("code", "")).strip()
            if too_many_tries(peer.addr[0]):
                peer.send({"t": "r_err", "msg": "시도가 너무 많아요. 1분 뒤에 다시 해 주세요."})
                return peer.close()
            with lock:
                room = rooms.get(code)
                if not room:
                    err = "그런 방이 없어요. 번호를 다시 확인해 주세요."
                elif room.guest is not None:
                    err = "이미 두 명이 들어 있는 방이에요."
                else:
                    err = None
                    room.guest = peer
                    peer.room = room
                    peer.other, room.host.other = room.host, peer
            if err:
                peer.send({"t": "r_err", "msg": err})
                return peer.close()
            room.host.send({"t": "r_paired", "role": "host"})
            peer.send({"t": "r_paired", "role": "guest"})
            log("입장", code, peer.addr[0])
        else:
            return peer.close()
        peer.sock.settimeout(None)
        for line in peer.lines():                           # 이어진 뒤: 상대에게 그대로 전달
            o = peer.other
            if o:
                o.send_raw(line + b"\n")
    finally:
        drop(peer)


def reaper():
    while True:
        time.sleep(30)
        now = time.time()
        with lock:
            old = [r for r in rooms.values() if r.guest is None and now - r.t > ROOM_WAIT]
        for r in old:
            r.host.send({"t": "r_err", "msg": "방이 너무 오래 비어 있어서 닫혔어요."})
            r.host.close()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5051
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", port))
    srv.listen(64)
    threading.Thread(target=reaper, daemon=True).start()
    log(f"중계 서버 시작 — 포트 {port}  (게임의 '서버 주소'에 이 PC의 IP:{port} 를 적으세요)")
    while True:
        sock, addr = srv.accept()
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=serve, args=(Peer(sock, addr),), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

"""Network module for P2P Swarm Game - UDP sockets + STUN discovery."""

import socket
import json
import struct
import time
import os
import time
import select

from .config import STUN_SERVERS, PING_INTERVAL, PING_TIMEOUT, RECONNECT_DELAY, PEER_FILE, HOST_MIGRATION_TIMEOUT, RECV_BUFFER_SIZE


class Network:
    """UDP network handler with STUN public endpoint discovery."""

    def __init__(self, port, stun_servers=None):
        self.port = port
        self.stun_servers = stun_servers or STUN_SERVERS
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(False)
        self.my_ip = self._get_local_ip()
        self.public_ip = None
        self.public_port = None
        self.sock.bind((self.my_ip, self.port))
        self.my_id = f"{self.my_ip}:{self.port}"
        self.pending_pings = {}  # peer_id -> (seq, sent_time)
        self.latencies = {}      # peer_id -> avg_rtt_ms
        self.last_ping_time = 0
        self.sequence = 0

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def discover_public_endpoint(self):
        """Use STUN to discover public IP:port (RFC 5389 Binding Request)."""
        for stun_host, stun_port in self.stun_servers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(2.0)
                sock.bind((self.my_ip, 0))
                # STUN Binding Request
                msg = struct.pack("!HHI", 0x0001, 0, 0x2112A442) + os.urandom(12)
                sock.sendto(msg, (stun_host, stun_port))
                data, _ = sock.recvfrom(1024)
                sock.close()
                # Parse XOR-MAPPED-ADDRESS
                if len(data) >= 20:
                    attr_type = struct.unpack("!H", data[20:22])[0]
                    if attr_type == 0x0020:  # XOR-MAPPED-ADDRESS
                        family = data[24]
                        if family == 1:  # IPv4
                            port = struct.unpack("!H", data[26:28])[0] ^ 0x2112
                            ip_bytes = bytes([b ^ 0x21 for b in data[28:32]])
                            self.public_ip = ".".join(str(b) for b in ip_bytes)
                            self.public_port = port
                            self.my_id = f"{self.public_ip}:{self.public_port}"
                            return True
            except Exception:
                pass
        return False

    def send(self, payload, target_id):
        ip, port = target_id.split(":")
        self.sock.sendto(json.dumps(payload).encode('utf-8'), (ip, int(port)))

    def broadcast(self, payload, peer_ids):
        msg = json.dumps(payload).encode('utf-8')
        for peer_id in peer_ids:
            try:
                ip, port = peer_id.split(":")
                self.sock.sendto(msg, (ip, int(port)))
            except Exception:
                pass

    def receive(self):
        ready, _, _ = select.select([self.sock], [], [], 0.01)
        if ready:
            data, addr = self.sock.recvfrom(RECV_BUFFER_SIZE)
            return json.loads(data.decode('utf-8')), addr
        return None, None

    def send_ping(self, peer_id):
        self.sequence += 1
        seq = self.sequence
        self.pending_pings[peer_id] = (seq, time.time())
        self.send({"type": "ping", "seq": seq, "sender_id": self.my_id}, peer_id)

    def handle_pong(self, message):
        sender_id = message.get("sender_id")
        seq = message.get("seq")
        if sender_id in self.pending_pings:
            pending_seq, sent_time = self.pending_pings.pop(sender_id)
            if pending_seq == seq:
                rtt = (time.time() - sent_time) * 1000
                old = self.latencies.get(sender_id, rtt)
                self.latencies[sender_id] = old * 0.7 + rtt * 0.3

    def get_latency(self, peer_id):
        return self.latencies.get(peer_id, 0)

    def update_pings(self, peer_ids):
        now = time.time()
        if now - self.last_ping_time >= PING_INTERVAL:
            for pid in peer_ids:
                if pid != self.my_id:
                    self.send_ping(pid)
            self.last_ping_time = now

    def close(self):
        self.sock.close()


def create_update_message(player, my_id, known_peers, latency=0):
    return {
        "type": "update",
        "sender_id": my_id,
        "x": player.x,
        "y": player.y,
        "color": player.color,
        "name": player.name,
        "team": player.team,
        "health": player.health,
        "max_health": player.max_health,
        "score": player.score,
        "kills": player.kills,
        "deaths": player.deaths,
        "alive": player.alive,
        "latency": latency,
        "swarm_list": list(known_peers)
    }


def create_handshake_message(player, my_id):
    return {
        "type": "update",
        "sender_id": my_id,
        "x": player.x,
        "y": player.y,
        "color": player.color,
        "name": player.name,
        "team": player.team,
        "health": player.health,
        "max_health": player.max_health,
        "score": player.score,
        "kills": player.kills,
        "deaths": player.deaths,
        "alive": player.alive,
        "latency": 0,
        "swarm_list": [my_id]
    }


def create_chat_message(my_id, text, team):
    return {
        "type": "chat",
        "sender_id": my_id,
        "text": text,
        "team": team
    }


def create_shoot_message(my_id, projectile):
    return {
        "type": "shoot",
        "sender_id": my_id,
        "x": projectile.x,
        "y": projectile.y,
        "vx": projectile.vx,
        "vy": projectile.vy,
        "team": projectile.team,
        "owner_id": projectile.owner_id
    }


def create_hit_message(my_id, target_id, damage):
    return {
        "type": "hit",
        "sender_id": my_id,
        "target_id": target_id,
        "damage": damage
    }


def create_respawn_message(my_id):
    return {
        "type": "respawn",
        "sender_id": my_id
    }


def create_ping_message(my_id, seq):
    return {
        "type": "ping",
        "sender_id": my_id,
        "seq": seq
    }


def create_pong_message(my_id, seq):
    return {
        "type": "pong",
        "sender_id": my_id,
        "seq": seq
    }


def create_host_announce_message(my_id, host_id):
    return {
        "type": "host_announce",
        "sender_id": my_id,
        "host_id": host_id
    }


def process_message(message, peer_manager, network, chat, projectiles, my_id, my_player):
    sender_id = message.get("sender_id")
    if not sender_id:
        return

    peer_manager.add_known_peer(sender_id)

    if "swarm_list" in message:
        peer_manager.merge_swarm_list(message["swarm_list"])

    msg_type = message.get("type")
    if msg_type == "update":
        peer_manager.validate_and_update(sender_id, message)
        if "latency" in message:
            peer_manager.update_peer_latency(sender_id, message["latency"])
    elif msg_type == "chat":
        chat.add_message(sender_id, message["text"], is_self=(sender_id == my_id), team=message.get("team"))
    elif msg_type == "shoot":
        if sender_id != my_id:
            from .projectile import Projectile
            proj = Projectile.from_state(message)
            projectiles.append(proj)
    elif msg_type == "hit":
        if message["target_id"] == my_id:
            from .player import Player
            result = my_player.take_damage(message["damage"], sender_id)
            if result == "death":
                network.broadcast(create_respawn_message(my_id), peer_manager.get_broadcast_targets())
            elif result == "hit":
                pass
    elif msg_type == "respawn":
        pass
    elif msg_type == "ping":
        network.send(create_pong_message(my_id, message["seq"]), sender_id)
    elif msg_type == "pong":
        network.handle_pong(message)
    elif msg_type == "host_announce":
        if message["host_id"] != peer_manager.get_host_id():
            peer_manager.host_id = message["host_id"]
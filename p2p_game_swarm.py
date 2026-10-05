import socket
import threading
import time
import json
import random
import pygame
import math
import argparse
import os
import struct
import select


# ============================
# CONFIGURATION
# ============================
DEFAULT_PORT = 55555
WIDTH, HEIGHT = 800, 600
PLAYER_SPEED = 5
MAX_FPS = 30
MAX_ALLOWED_DISTANCE_PER_FRAME = PLAYER_SPEED * 2.5
PEER_TIMEOUT = 3.0
MAX_STRIKES = 5
PLAYER_SIZE = 24
RECV_BUFFER_SIZE = 2048
CHAT_HISTORY_MAX = 50
CHAT_INPUT_HEIGHT = 30
CHAT_HISTORY_HEIGHT = 120

# Gameplay
MAX_HEALTH = 100
PROJECTILE_SPEED = 12
PROJECTILE_SIZE = 6
PROJECTILE_DAMAGE = 25
FIRE_COOLDOWN = 0.3
RESPAWN_TIME = 3.0
INVULNERABLE_TIME = 1.5
TEAM_COLORS = {
    "red": (220, 60, 60),
    "blue": (60, 120, 220),
    "green": (60, 200, 80),
    "yellow": (220, 200, 40),
}
DEFAULT_TEAM = "red"
FRIENDLY_FIRE = False

# Network
PING_INTERVAL = 1.0
PING_TIMEOUT = 2.0
RECONNECT_DELAY = 5.0
PEER_FILE = "peers.json"
STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
]
HOST_MIGRATION_TIMEOUT = 5.0


# ============================
# NETWORK MODULE
# ============================
class Network:
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
        """Use STUN to discover public IP:port"""
        for stun_host, stun_port in self.stun_servers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(2.0)
                sock.bind((self.my_ip, 0))
                # STUN Binding Request (RFC 5389)
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
                            print(f"[STUN] Public endpoint: {self.my_id}")
                            return True
            except Exception as e:
                print(f"[STUN] Failed {stun_host}: {e}")
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
                # Exponential moving average
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


# ============================
# PEER MANAGEMENT MODULE
# ============================
class PeerManager:
    def __init__(self, my_id, max_distance, max_strikes, timeout):
        self.my_id = my_id
        self.max_distance = max_distance
        self.max_strikes = max_strikes
        self.timeout = timeout
        self.peers = {}
        self.known_peers = set()
        self.host_id = my_id
        self.host_candidates = set()
        self.last_host_change = 0

    def add_known_peer(self, peer_id):
        if peer_id != self.my_id and peer_id not in self.known_peers:
            self.known_peers.add(peer_id)
            self.host_candidates.add(peer_id)
            print(f"[🌐 PEER BARU] {peer_id}")
            return True
        return False

    def merge_swarm_list(self, swarm_list):
        for peer_id in swarm_list:
            self.add_known_peer(peer_id)

    def validate_and_update(self, sender_id, data):
        if sender_id == self.my_id:
            return

        is_valid = True
        if sender_id in self.peers:
            old_x = self.peers[sender_id]["x"]
            old_y = self.peers[sender_id]["y"]
            distance = math.sqrt((data["x"] - old_x) ** 2 + (data["y"] - old_y) ** 2)
            if distance > self.max_distance:
                print(f"[⚠️ VALIDASI GAGAL] {sender_id} jarak: {distance:.2f}px")
                is_valid = False

        if is_valid:
            self.peers[sender_id] = {
                "x": data["x"], "y": data["y"],
                "color": tuple(data["color"]),
                "name": data.get("name", sender_id.split(":")[-1]),
                "team": data.get("team", DEFAULT_TEAM),
                "health": data.get("health", MAX_HEALTH),
                "max_health": data.get("max_health", MAX_HEALTH),
                "score": data.get("score", 0),
                "kills": data.get("kills", 0),
                "deaths": data.get("deaths", 0),
                "alive": data.get("alive", True),
                "last_seen": time.time(),
                "strike_count": 0,
                "latency": data.get("latency", 0)
            }
            self.host_candidates.add(sender_id)
        else:
            strikes = self.peers[sender_id].get("strike_count", 0) + 1
            self.peers[sender_id]["strike_count"] = strikes
            if strikes > self.max_strikes:
                print(f"[❌ KICKED] {sender_id} indikasi cheat")
                self.remove_peer(sender_id)

    def update_peer_health(self, sender_id, health, alive):
        if sender_id in self.peers:
            self.peers[sender_id]["health"] = health
            self.peers[sender_id]["alive"] = alive

    def update_peer_score(self, sender_id, score, kills, deaths):
        if sender_id in self.peers:
            self.peers[sender_id]["score"] = score
            self.peers[sender_id]["kills"] = kills
            self.peers[sender_id]["deaths"] = deaths

    def update_peer_latency(self, sender_id, latency):
        if sender_id in self.peers:
            self.peers[sender_id]["latency"] = latency

    def remove_peer(self, peer_id):
        self.peers.pop(peer_id, None)
        self.known_peers.discard(peer_id)
        self.host_candidates.discard(peer_id)
        if peer_id == self.host_id:
            self.elect_new_host()

    def elect_new_host(self):
        now = time.time()
        if now - self.last_host_change < HOST_MIGRATION_TIMEOUT:
            return
        # Elect lowest IP:port as host (deterministic)
        candidates = [self.my_id] + list(self.host_candidates)
        candidates = [c for c in candidates if c in self.known_peers or c == self.my_id]
        if candidates:
            new_host = min(candidates)
            if new_host != self.host_id:
                print(f"[👑 HOST MIGRATION] New host: {new_host}")
                self.host_id = new_host
                self.last_host_change = now

    def is_host(self):
        return self.host_id == self.my_id

    def get_host_id(self):
        return self.host_id

    def cleanup_timed_out(self):
        now = time.time()
        for peer_id in list(self.peers.keys()):
            if now - self.peers[peer_id]["last_seen"] > self.timeout:
                print(f"[🚪 TIMEOUT] {peer_id}")
                self.remove_peer(peer_id)

    def get_broadcast_targets(self):
        return list(self.known_peers)

    def get_render_data(self):
        return self.peers

    def get_alive_peers(self):
        return {pid: p for pid, p in self.peers.items() if p.get("alive", True)}

    def save_peers(self, filename=PEER_FILE):
        try:
            with open(filename, 'w') as f:
                json.dump(list(self.known_peers), f)
        except Exception:
            pass

    def load_peers(self, filename=PEER_FILE):
        try:
            with open(filename, 'r') as f:
                peers = json.load(f)
                for p in peers:
                    self.add_known_peer(p)
                print(f"[📂] Loaded {len(peers)} peers from {filename}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[📂] Failed to load peers: {e}")


# ============================
# PLAYER MODULE
# ============================
class Player:
    def __init__(self, name=None, team=DEFAULT_TEAM):
        self.x = random.randint(50, WIDTH - 50)
        self.y = random.randint(50, HEIGHT - 50)
        self.team = team
        self.color = TEAM_COLORS.get(team, TEAM_COLORS[DEFAULT_TEAM])
        self.name = name or f"Player_{random.randint(1000, 9999)}"
        self.health = MAX_HEALTH
        self.max_health = MAX_HEALTH
        self.score = 0
        self.kills = 0
        self.deaths = 0
        self.alive = True
        self.last_shot = 0
        self.invulnerable_until = 0
        self.respawn_timer = 0

    def move(self, keys, speed, width, height, size):
        if not self.alive:
            return
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.x = max(0, self.x - speed)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.x = min(width - size, self.x + speed)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.y = max(0, self.y - speed)
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.y = min(height - size, self.y + speed)

    def can_shoot(self):
        return time.time() - self.last_shot >= FIRE_COOLDOWN

    def shoot(self, target_x, target_y):
        if not self.alive or not self.can_shoot():
            return None
        self.last_shot = time.time()
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist == 0:
            return None
        return Projectile(
            self.x + PLAYER_SIZE // 2,
            self.y + PLAYER_SIZE // 2,
            dx / dist * PROJECTILE_SPEED,
            dy / dist * PROJECTILE_SPEED,
            self.team,
            self.my_id if hasattr(self, 'my_id') else "unknown"
        )

    def take_damage(self, amount, attacker_id=None):
        if not self.alive:
            return False
        now = time.time()
        if now < self.invulnerable_until:
            return False
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.alive = False
            self.deaths += 1
            self.respawn_timer = now + RESPAWN_TIME
            if attacker_id and attacker_id != self.my_id:
                return "death"
        return "hit"

    def heal(self, amount):
        self.health = min(self.max_health, self.health + amount)

    def respawn(self):
        self.x = random.randint(50, WIDTH - 50)
        self.y = random.randint(50, HEIGHT - 50)
        self.health = self.max_health
        self.alive = True
        self.invulnerable_until = time.time() + INVULNERABLE_TIME

    def add_kill(self):
        self.kills += 1
        self.score += 100

    def get_state(self):
        return {
            "x": self.x, "y": self.y,
            "color": self.color,
            "name": self.name,
            "team": self.team,
            "health": self.health,
            "max_health": self.max_health,
            "score": self.score,
            "kills": self.kills,
            "deaths": self.deaths,
            "alive": self.alive
        }

    def set_id(self, my_id):
        self.my_id = my_id


# ============================
# PROJECTILE MODULE
# ============================
class Projectile:
    def __init__(self, x, y, vx, vy, team, owner_id):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.team = team
        self.owner_id = owner_id
        self.color = TEAM_COLORS.get(team, (255, 255, 255))
        self.alive = True
        self.spawn_time = time.time()
        self.max_life = 3.0

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if time.time() - self.spawn_time > self.max_life:
            self.alive = False
        if self.x < 0 or self.x > WIDTH or self.y < 0 or self.y > HEIGHT:
            self.alive = False

    def get_rect(self):
        return pygame.Rect(self.x - PROJECTILE_SIZE // 2, self.y - PROJECTILE_SIZE // 2,
                          PROJECTILE_SIZE, PROJECTILE_SIZE)

    def get_state(self):
        return {
            "x": self.x, "y": self.y,
            "vx": self.vx, "vy": self.vy,
            "team": self.team,
            "owner_id": self.owner_id
        }

    @staticmethod
    def from_state(state):
        p = Projectile(state["x"], state["y"], state["vx"], state["vy"],
                      state["team"], state["owner_id"])
        return p


# ============================
# CHAT MODULE
# ============================
class Chat:
    def __init__(self, max_history=CHAT_HISTORY_MAX):
        self.messages = []
        self.max_history = max_history
        self.input_active = False
        self.input_text = ""
        self.font = None
        self.small_font = None

    def init_fonts(self):
        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 16)
        self.small_font = pygame.font.SysFont("consolas", 14)

    def add_message(self, sender_id, text, is_self=False, team=None):
        timestamp = time.strftime("%H:%M:%S")
        self.messages.append({
            "sender": sender_id,
            "text": text,
            "time": timestamp,
            "is_self": is_self,
            "team": team
        })
        if len(self.messages) > self.max_history:
            self.messages.pop(0)

    def activate_input(self):
        self.input_active = True
        self.input_text = ""
        pygame.key.start_text_input()

    def deactivate_input(self):
        self.input_active = False
        self.input_text = ""
        pygame.key.stop_text_input()

    def handle_text_input(self, event):
        if event.type == pygame.TEXTINPUT:
            self.input_text += event.text
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif event.key == pygame.K_RETURN:
                text = self.input_text.strip()
                self.deactivate_input()
                return text
            elif event.key == pygame.K_ESCAPE:
                self.deactivate_input()
        return None

    def draw(self, screen, width, height, my_id):
        if not self.font:
            self.init_fonts()

        history_y = height - CHAT_INPUT_HEIGHT - CHAT_HISTORY_HEIGHT
        pygame.draw.rect(screen, (20, 20, 20, 180), (0, history_y, width, CHAT_HISTORY_HEIGHT))

        y = history_y + 5
        for msg in reversed(self.messages):
            team_color = TEAM_COLORS.get(msg.get("team", ""), (200, 200, 200))
            color = (100, 255, 100) if msg["is_self"] else team_color
            prefix = f"[{msg['time']}] "
            if msg["is_self"]:
                sender_text = "You"
            else:
                sender_text = msg["sender"].split(":")[-1]
            text_surface = self.small_font.render(f"{prefix}{sender_text}: {msg['text']}", True, color)
            screen.blit(text_surface, (10, y))
            y += 20
            if y > height - CHAT_INPUT_HEIGHT - 5:
                break

        if self.input_active:
            pygame.draw.rect(screen, (40, 40, 60), (0, height - CHAT_INPUT_HEIGHT, width, CHAT_INPUT_HEIGHT))
            pygame.draw.rect(screen, (100, 100, 150), (0, height - CHAT_INPUT_HEIGHT, width, CHAT_INPUT_HEIGHT), 2)
            prompt = self.font.render(f"> {self.input_text}_", True, (255, 255, 255))
            screen.blit(prompt, (10, height - CHAT_INPUT_HEIGHT + 5))


# ============================
# RENDERER MODULE
# ============================
class Renderer:
    def __init__(self, width, height, caption):
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(caption)
        self.clock = pygame.time.Clock()
        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 14)
        self.small_font = pygame.font.SysFont("consolas", 12)
        self.big_font = pygame.font.SysFont("consolas", 24, bold=True)

    def clear(self, bg_color=(25, 25, 30)):
        self.screen.fill(bg_color)

    def draw_player(self, x, y, color, size=PLAYER_SIZE, name="", health=MAX_HEALTH, max_health=MAX_HEALTH,
                    team="", alive=True, invulnerable=False, latency=0, is_host=False):
        if not alive:
            return
        alpha = 180 if invulnerable else 255
        player_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(player_surf, (*color, alpha), (0, 0, size, size), border_radius=4)
        self.screen.blit(player_surf, (x, y))

        # Name
        name_surf = self.small_font.render(name, True, (255, 255, 255))
        self.screen.blit(name_surf, (x + size // 2 - name_surf.get_width() // 2, y - 18))

        # Health bar
        bar_w = size
        bar_h = 4
        bar_x = x
        bar_y = y - 8
        pygame.draw.rect(self.screen, (80, 20, 20), (bar_x, bar_y, bar_w, bar_h))
        hp_w = int(bar_w * health / max_health)
        pygame.draw.rect(self.screen, (60, 220, 60), (bar_x, bar_y, hp_w, bar_h))
        pygame.draw.rect(self.screen, (100, 100, 100), (bar_x, bar_y, bar_w, bar_h), 1)

        # Team indicator
        team_surf = self.small_font.render(team[0].upper(), True, (255, 255, 255))
        self.screen.blit(team_surf, (x - 14, y + 2))

        # Host crown
        if is_host:
            crown = self.small_font.render("♔", True, (255, 215, 0))
            self.screen.blit(crown, (x + size // 2 - 4, y - 28))

        # Latency
        if latency > 0:
            lat_color = (60, 220, 60) if latency < 100 else (220, 200, 40) if latency < 200 else (220, 60, 60)
            lat_surf = self.small_font.render(f"{latency:.0f}ms", True, lat_color)
            self.screen.blit(lat_surf, (x + size + 2, y))

    def draw_projectile(self, x, y, color, size=PROJECTILE_SIZE):
        pygame.draw.circle(self.screen, color, (int(x), int(y)), size // 2)
        pygame.draw.circle(self.screen, (255, 255, 255), (int(x), int(y)), size // 2, 1)

    def draw_leaderboard(self, peers, my_id, my_data, host_id):
        lb_width = 240
        lb_height = 30 + len(peers) * 22 + 40
        lb_x = WIDTH - lb_width - 10
        lb_y = 10
        pygame.draw.rect(self.screen, (20, 20, 30, 220), (lb_x, lb_y, lb_width, lb_height), border_radius=8)
        pygame.draw.rect(self.screen, (80, 80, 120), (lb_x, lb_y, lb_width, lb_height), 2, border_radius=8)

        title = self.font.render("LEADERBOARD", True, (220, 220, 240))
        self.screen.blit(title, (lb_x + lb_width // 2 - title.get_width() // 2, lb_y + 8))

        all_players = []
        all_players.append(("You", my_data["team"], my_data["score"], my_data["kills"], my_data["deaths"], True, my_id == host_id))
        for pid, p in peers.items():
            if p.get("alive", True) or p.get("score", 0) > 0:
                all_players.append((p["name"], p["team"], p["score"], p["kills"], p["deaths"], False, pid == host_id))

        all_players.sort(key=lambda x: x[2], reverse=True)

        y = lb_y + 32
        for i, (name, team, score, kills, deaths, is_self, is_host) in enumerate(all_players[:8]):
            color = TEAM_COLORS.get(team, (200, 200, 200))
            prefix = f"{i+1}. "
            if is_host:
                prefix = "♔ "
            text = f"{prefix}{name[:10]}  {score}  K:{kills} D:{deaths}"
            surf = self.small_font.render(text, True, color if not is_self else (100, 255, 100))
            self.screen.blit(surf, (lb_x + 10, y))
            y += 22

    def draw_respawn_timer(self, screen, respawn_timer):
        if respawn_timer > 0:
            remaining = max(0, respawn_timer - time.time())
            if remaining > 0:
                text = self.big_font.render(f"Respawning in {remaining:.1f}s...", True, (255, 100, 100))
                rect = text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
                pygame.draw.rect(screen, (20, 0, 0, 200), rect.inflate(20, 10), border_radius=8)
                screen.blit(text, rect)

    def draw_hud(self, player, is_host, latency_avg):
        hp_text = self.font.render(f"HP: {player.health}/{player.max_health}", True, (220, 60, 60))
        self.screen.blit(hp_text, (10, 10))
        score_text = self.font.render(f"Score: {player.score}  K:{player.kills} D:{player.deaths}", True, (220, 220, 100))
        self.screen.blit(score_text, (10, 32))
        team_text = self.font.render(f"Team: {player.team.upper()}", True, TEAM_COLORS.get(player.team, (200,200,200)))
        self.screen.blit(team_text, (10, 54))
        cd = FIRE_COOLDOWN - (time.time() - player.last_shot)
        if cd > 0:
            cd_text = self.font.render(f"Reload: {cd:.1f}s", True, (200, 100, 100))
            self.screen.blit(cd_text, (10, 76))
        host_text = self.small_font.render(f"{'👑 HOST' if is_host else 'Client'}  Avg Ping: {latency_avg:.0f}ms", True, (150, 150, 180))
        self.screen.blit(host_text, (10, 98))

    def draw_network_info(self, network, peer_manager):
        y = HEIGHT - CHAT_INPUT_HEIGHT - CHAT_HISTORY_HEIGHT - 120
        x = 10
        pygame.draw.rect(self.screen, (20, 20, 30, 200), (x, y, 200, 110), border_radius=4)
        pygame.draw.rect(self.screen, (60, 60, 100), (x, y, 200, 110), 1, border_radius=4)
        
        info = [
            f"Local: {network.my_ip}:{network.port}",
            f"Public: {network.my_id}",
            f"Peers: {len(peer_manager.known_peers)}",
            f"Host: {peer_manager.get_host_id().split(':')[-1]}",
        ]
        for i, line in enumerate(info):
            surf = self.small_font.render(line, True, (200, 200, 220))
            self.screen.blit(surf, (x + 8, y + 8 + i * 22))
        
        # Peer latencies
        for pid, pdata in peer_manager.get_render_data().items():
            lat = pdata.get("latency", 0)
            if lat > 0:
                lat_color = (60, 220, 60) if lat < 100 else (220, 200, 40) if lat < 200 else (220, 60, 60)
                name = pdata["name"][:8]
                surf = self.small_font.render(f"  {name}: {lat:.0f}ms", True, lat_color)
                self.screen.blit(surf, (x + 8, y + 8 + len(info) * 22))

    def present(self, fps):
        pygame.display.flip()
        self.clock.tick(fps)

    def quit(self):
        pygame.quit()


# ============================
# MESSAGE HANDLING
# ============================
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
        # Update latency from peer's reported latency
        if "latency" in message:
            peer_manager.update_peer_latency(sender_id, message["latency"])
    elif msg_type == "chat":
        chat.add_message(sender_id, message["text"], is_self=(sender_id == my_id), team=message.get("team"))
    elif msg_type == "shoot":
        if sender_id != my_id:
            proj = Projectile.from_state(message)
            projectiles.append(proj)
    elif msg_type == "hit":
        if message["target_id"] == my_id:
            result = my_player.take_damage(message["damage"], sender_id)
            if result == "death":
                network.broadcast(create_respawn_message(my_id), peer_manager.get_broadcast_targets())
                chat.add_message("SYSTEM", f"You were killed by {sender_id.split(':')[-1]}!", is_self=True)
            elif result == "hit":
                chat.add_message("SYSTEM", f"Hit for {message['damage']} damage!", is_self=True)
    elif msg_type == "respawn":
        pass
    elif msg_type == "ping":
        # Reply with pong
        network.send(create_pong_message(my_id, message["seq"]), sender_id)
    elif msg_type == "pong":
        network.handle_pong(message)
    elif msg_type == "host_announce":
        if message["host_id"] != peer_manager.get_host_id():
            print(f"[👑 HOST ANNOUNCE] Host is now {message['host_id']}")
            peer_manager.host_id = message["host_id"]


# ============================
# RECEIVER THREAD
# ============================
def receiver_loop(network, peer_manager, chat, projectiles, my_id, my_player, running_flag):
    while running_flag[0]:
        try:
            message, addr = network.receive()
            if message:
                process_message(message, peer_manager, network, chat, projectiles, my_id, my_player)
        except Exception as e:
            if running_flag[0]:
                print(f"[Network Error] {e}")
            break


# ============================
# RECONNECTION MODULE
# ============================
class ReconnectionManager:
    def __init__(self, network, peer_manager, player):
        self.network = network
        self.peer_manager = peer_manager
        self.player = player
        self.last_attempt = 0
        self.running = True

    def attempt_reconnect(self):
        if not self.peer_manager.known_peers:
            return
        now = time.time()
        if now - self.last_attempt < RECONNECT_DELAY:
            return
        self.last_attempt = now
        print(f"[🔄] Attempting reconnection to {len(self.peer_manager.known_peers)} peers...")
        for peer_id in self.peer_manager.get_broadcast_targets():
            self.network.send(create_handshake_message(self.player, self.network.my_id), peer_id)

    def save_state(self):
        self.peer_manager.save_peers()

    def load_state(self):
        self.peer_manager.load_peers()


# ============================
# MAIN
# ============================
def main():
    parser = argparse.ArgumentParser(description="P2P Swarm Network Multiplayer Game")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("-n", "--name", type=str, default=None, help="Player name")
    parser.add_argument("-t", "--team", type=str, default=DEFAULT_TEAM, choices=list(TEAM_COLORS.keys()), help="Team")
    parser.add_argument("--no-stun", action="store_true", help="Disable STUN public IP discovery")
    args = parser.parse_args()

    network = Network(args.port)
    if not args.no_stun:
        print("[*] Discovering public endpoint via STUN...")
        network.discover_public_endpoint()

    player = Player(name=args.name, team=args.team)
    player.set_id(network.my_id)
    peer_manager = PeerManager(
        network.my_id, MAX_ALLOWED_DISTANCE_PER_FRAME, MAX_STRIKES, PEER_TIMEOUT
    )
    renderer = Renderer(WIDTH, HEIGHT, f"P2P Swarm Game | Port: {args.port} | {player.name} ({player.team})")
    chat = Chat()
    projectiles = []
    reconnect = ReconnectionManager(network, peer_manager, player)

    print(f"[*] Game Swarm P2P berjalan di ID: {network.my_id}")
    print(f"[*] Name: {player.name} | Team: {player.team}")

    # Load saved peers for reconnection
    reconnect.load_state()

    # Initial connection
    print("\n=== MENU KONEKSI SWARM P2P ===")
    target_input = input("Masukkan ID P2P Teman (IP:PORT) atau ENTER jika pertama: ").strip()
    if target_input:
        peer_manager.add_known_peer(target_input)
        network.send(create_handshake_message(player, network.my_id), target_input)

    # Start receiver thread
    running = [True]
    recv_thread = threading.Thread(
        target=receiver_loop, args=(network, peer_manager, chat, projectiles, network.my_id, player, running), daemon=True
    )
    recv_thread.start()

    # Start reconnection thread
    def reconnect_loop():
        while running[0]:
            reconnect.attempt_reconnect()
            time.sleep(1)
    reconnect_thread = threading.Thread(target=reconnect_loop, daemon=True)
    reconnect_thread.start()

    # Main game loop
    last_save = time.time()
    while running[0]:
        mouse_x, mouse_y = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running[0] = False
                reconnect.save_state()

            if chat.input_active:
                sent_text = chat.handle_text_input(event)
                if sent_text is not None and sent_text:
                    chat.add_message(network.my_id, sent_text, is_self=True, team=player.team)
                    network.broadcast(create_chat_message(network.my_id, sent_text, player.team), peer_manager.get_broadcast_targets())
            else:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SLASH:
                        chat.activate_input()
                    elif event.key == pygame.K_TAB:
                        teams = list(TEAM_COLORS.keys())
                        idx = teams.index(player.team)
                        player.team = teams[(idx + 1) % len(teams)]
                        player.color = TEAM_COLORS[player.team]
                        renderer = Renderer(WIDTH, HEIGHT, f"P2P Swarm Game | Port: {args.port} | {player.name} ({player.team})")
                    elif event.key == pygame.K_F5:
                        reconnect.save_state()
                        print("[💾] Peers saved manually")

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    proj = player.shoot(mouse_x, mouse_y)
                    if proj:
                        projectiles.append(proj)
                        network.broadcast(create_shoot_message(network.my_id, proj), peer_manager.get_broadcast_targets())

        if not chat.input_active:
            keys = pygame.key.get_pressed()
            player.move(keys, PLAYER_SPEED, WIDTH, HEIGHT, PLAYER_SIZE)

        # Respawn handling
        if not player.alive:
            if time.time() >= player.respawn_timer:
                player.respawn()
                network.broadcast(create_respawn_message(network.my_id), peer_manager.get_broadcast_targets())

        # Update projectiles
        for proj in projectiles[:]:
            proj.update()
            if not proj.alive:
                projectiles.remove(proj)
                continue
            if proj.owner_id == network.my_id:
                for peer_id, pdata in peer_manager.get_alive_peers().items():
                    if not FRIENDLY_FIRE and pdata["team"] == player.team:
                        continue
                    peer_rect = pygame.Rect(pdata["x"], pdata["y"], PLAYER_SIZE, PLAYER_SIZE)
                    if proj.get_rect().colliderect(peer_rect):
                        proj.alive = False
                        network.send(create_hit_message(network.my_id, peer_id, PROJECTILE_DAMAGE), peer_id)
                        break

        # Host migration
        peer_manager.elect_new_host()
        if peer_manager.is_host():
            network.broadcast(create_host_announce_message(network.my_id, network.my_id), peer_manager.get_broadcast_targets())

        # Ping for latency
        network.update_pings(peer_manager.get_broadcast_targets())
        # Update peer latencies from network
        for pid, lat in network.latencies.items():
            peer_manager.update_peer_latency(pid, lat)

        peer_manager.cleanup_timed_out()

        # Calculate average latency for HUD
        latencies = [p.get("latency", 0) for p in peer_manager.peers.values() if p.get("latency", 0) > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Broadcast with local latency
        network.broadcast(create_update_message(player, network.my_id, peer_manager.known_peers, avg_latency), peer_manager.get_broadcast_targets())

        # Auto-save peers periodically
        if time.time() - last_save > 30:
            reconnect.save_state()
            last_save = time.time()

        renderer.clear()

        # Draw projectiles
        for proj in projectiles:
            renderer.draw_projectile(proj.x, proj.y, proj.color)

        # Draw local player
        invuln = time.time() < player.invulnerable_until
        renderer.draw_player(player.x, player.y, player.color, PLAYER_SIZE, player.name,
                            player.health, player.max_health, player.team, player.alive, invuln,
                            latency=0, is_host=peer_manager.is_host())

        # Draw peers
        for peer_id, data in peer_manager.get_render_data().items():
            if data.get("alive", True):
                lat = data.get("latency", 0)
                renderer.draw_player(data["x"], data["y"], data["color"], PLAYER_SIZE,
                                    data["name"], data["health"], data["max_health"],
                                    data["team"], data["alive"], False,
                                    latency=lat, is_host=(peer_id == peer_manager.get_host_id()))

        # Leaderboard
        renderer.draw_leaderboard(peer_manager.get_render_data(), network.my_id, player.get_state(), peer_manager.get_host_id())

        # HUD
        renderer.draw_hud(player, peer_manager.is_host(), avg_latency)

        # Network info panel
        renderer.draw_network_info(network, peer_manager)

        # Respawn timer
        if not player.alive:
            renderer.draw_respawn_timer(renderer.screen, player.respawn_timer)

        # Chat
        chat.draw(renderer.screen, WIDTH, HEIGHT, network.my_id)

        renderer.present(MAX_FPS)

    reconnect.save_state()
    renderer.quit()
    network.close()


if __name__ == "__main__":
    main()
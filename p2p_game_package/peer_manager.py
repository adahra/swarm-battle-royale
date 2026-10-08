"""Peer Management module for P2P Swarm Game."""

import time
import json
from .config import MAX_ALLOWED_DISTANCE_PER_FRAME, MAX_STRIKES, PEER_TIMEOUT, DEFAULT_TEAM, MAX_HEALTH, HOST_MIGRATION_TIMEOUT


class PeerManager:
    """Manages peer connections, host election, timeouts, and anti-cheat validation."""

    def __init__(self, my_id, max_distance=MAX_ALLOWED_DISTANCE_PER_FRAME, max_strikes=MAX_STRIKES, timeout=PEER_TIMEOUT):
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
            return True
        return False

    def merge_swarm_list(self, swarm_list):
        for peer_id in swarm_list:
            self.add_known_peer(peer_id)

    def validate_and_update(self, sender_id, data):
        if sender_id == self.my_id:
            return
        try:
            nx, ny = float(data["x"]), float(data["y"])
        except (KeyError, TypeError, ValueError):
            return

        is_valid = True
        if sender_id in self.peers:
            old_x = self.peers[sender_id]["x"]
            old_y = self.peers[sender_id]["y"]
            distance = ((nx - old_x) ** 2 + (ny - old_y) ** 2) ** 0.5
            if distance > self.max_distance:
                is_valid = False

        if is_valid:
            prev_strikes = self.peers.get(sender_id, {}).get("strike_count", 0)
            try:
                color = tuple(data["color"])
            except (KeyError, TypeError, ValueError):
                return
            self.peers[sender_id] = {
                "x": nx, "y": ny,
                "color": color,
                "name": data.get("name", sender_id.split(":")[-1]),
                "team": data.get("team", DEFAULT_TEAM),
                "health": data.get("health", MAX_HEALTH),
                "max_health": data.get("max_health", MAX_HEALTH),
                "score": data.get("score", 0),
                "kills": data.get("kills", 0),
                "deaths": data.get("deaths", 0),
                "alive": data.get("alive", True),
                "last_seen": time.time(),
                "strike_count": prev_strikes,
                "latency": data.get("latency", 0)
            }
            self.host_candidates.add(sender_id)
        else:
            strikes = self.peers.get(sender_id, {}).get("strike_count", 0) + 1
            self.peers.setdefault(sender_id, {})["strike_count"] = strikes
            if strikes > self.max_strikes:
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
            self.elect_new_host(force=True)

    def elect_new_host(self, force=False):
        now = time.time()
        if not force and now - self.last_host_change < HOST_MIGRATION_TIMEOUT:
            return
        candidates = [self.my_id] + list(self.host_candidates)
        candidates = [c for c in candidates if c in self.known_peers or c == self.my_id]
        if candidates:
            new_host = min(candidates)
            if new_host != self.host_id:
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
                self.remove_peer(peer_id)

    def get_broadcast_targets(self):
        return list(self.known_peers)

    def get_render_data(self):
        return self.peers

    def get_alive_peers(self):
        return {pid: p for pid, p in self.peers.items() if p.get("alive", True)}

    def save_peers(self, filename="peers.json"):
        try:
            with open(filename, 'w') as f:
                json.dump(list(self.known_peers), f)
        except Exception:
            pass

    def load_peers(self, filename="peers.json"):
        try:
            with open(filename, 'r') as f:
                peers = json.load(f)
                for p in peers:
                    self.add_known_peer(p)
        except FileNotFoundError:
            pass
        except Exception:
            pass
"""Reconnection module for P2P Swarm Game."""

import time
from .config import RECONNECT_DELAY
from .network import create_handshake_message


class ReconnectionManager:
    """Manages auto-reconnection and session state persistence."""

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
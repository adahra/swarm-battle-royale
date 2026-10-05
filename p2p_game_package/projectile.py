"""Projectile module for P2P Swarm Game."""

"""Projectile module for P2P Swarm Game."""

import time
from .config import PROJECTILE_SPEED, PROJECTILE_SIZE, PROJECTILE_DAMAGE, WIDTH, HEIGHT


class Projectile:
    """Represents a projectile fired by a player."""

    def __init__(self, x, y, vx, vy, team, owner_id):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.team = team
        self.owner_id = owner_id
        self.color = (255, 255, 255)
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
        import pygame
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
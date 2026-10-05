"""Player module for P2P Swarm Game."""

import random
import math
import time
import pygame
from .config import WIDTH, HEIGHT, PLAYER_SIZE, MAX_HEALTH, PROJECTILE_SPEED, FIRE_COOLDOWN, TEAM_COLORS, DEFAULT_TEAM, RESPAWN_TIME, INVULNERABLE_TIME
from .projectile import Projectile


class Player:
    """Represents a player in the P2P swarm game."""

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
        self.my_id = None

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
            self.my_id if self.my_id else "unknown"
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
            self.respawn_timer = time.time() + RESPAWN_TIME
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
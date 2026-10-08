"""Renderer module for P2P Swarm Game - pygame rendering."""

import time
import pygame
from .config import WIDTH, HEIGHT, PLAYER_SIZE, PROJECTILE_SIZE, TEAM_COLORS, FIRE_COOLDOWN, MAX_HEALTH, CHAT_INPUT_HEIGHT, CHAT_HISTORY_HEIGHT


class Renderer:
    """Pygame renderer for the P2P swarm game visuals."""

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

    def _panel(self, rect, alpha=170, fill=(20, 20, 30), border=(80, 80, 120), radius=8):
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((*fill, alpha))
        self.screen.blit(surf, rect.topleft)
        if border:
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=radius)

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

    def draw_leaderboard(self, peers, my_id, my_data, host_id, alpha=170):
        lb_width = 240
        lb_height = 30 + len(peers) * 22 + 40
        lb_x = WIDTH - lb_width - 10
        lb_y = 10
        self._panel(pygame.Rect(lb_x, lb_y, lb_width, lb_height), alpha=alpha)

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
        team_text = self.font.render(f"Team: {player.team.upper()}", True, TEAM_COLORS.get(player.team, (200, 200, 200)))
        self.screen.blit(team_text, (10, 54))
        cd = FIRE_COOLDOWN - (time.time() - player.last_shot)
        if cd > 0:
            cd_text = self.font.render(f"Reload: {cd:.1f}s", True, (200, 100, 100))
            self.screen.blit(cd_text, (10, 76))
        host_text = self.small_font.render(f"{'👑 HOST' if is_host else 'Client'}  Avg Ping: {latency_avg:.0f}ms", True, (150, 150, 180))
        self.screen.blit(host_text, (10, 98))

    def draw_network_info(self, network, peer_manager, alpha=170):
        y = HEIGHT - CHAT_INPUT_HEIGHT - CHAT_HISTORY_HEIGHT - 120
        x = 10
        self._panel(pygame.Rect(x, y, 200, 110), alpha=alpha, radius=4, border=(60, 60, 100))

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
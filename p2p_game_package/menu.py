"""Main menu for P2P Swarm Game - in-game pygame menu (no terminal input)."""

import pygame
from .config import WIDTH, HEIGHT, TEAM_COLORS, DEFAULT_TEAM

MENU_FIELDS = ["name", "team", "friend_id"]


class MainMenu:
    """Simple keyboard-driven main menu.

    Fields: player name, team (Left/Right to cycle), friend ID (IP:PORT).
    Navigation: Up/Down or Tab to move, Enter on [ START ] begins game,
    Esc quits. Returns dict with action: 'start' or 'quit'.
    """

    def __init__(self, screen, name="", team=DEFAULT_TEAM):
        pygame.font.init()
        self.screen = screen
        self.title_font = pygame.font.SysFont("consolas", 40, bold=True)
        self.font = pygame.font.SysFont("consolas", 20)
        self.small_font = pygame.font.SysFont("consolas", 14)
        self.name = name
        self.team = team if team in TEAM_COLORS else DEFAULT_TEAM
        self.friend_id = ""
        self.selected = 0  # index into MENU_FIELDS + start button
        self.done = False
        self.quit_requested = False

    @property
    def field_count(self):
        return len(MENU_FIELDS) + 1  # + start button

    def selected_name(self):
        if self.selected < len(MENU_FIELDS):
            return MENU_FIELDS[self.selected]
        return "start"

    def _current_text(self):
        return {"name": self.name, "team": self.team,
                "friend_id": self.friend_id}.get(self.selected_name(), "")

    def handle_event(self, event):
        """Process one pygame event. Returns 'start'/'quit'/None."""
        if event.type == pygame.QUIT:
            self.quit_requested = True
            return "quit"
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            self.quit_requested = True
            return "quit"
        if event.key in (pygame.K_TAB, pygame.K_DOWN):
            self.selected = (self.selected + 1) % self.field_count
            return None
        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % self.field_count
            return None
        if self.selected_name() == "start":
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.done = True
                return "start"
            return None
        if self.selected_name() == "team":
            teams = list(TEAM_COLORS.keys())
            idx = teams.index(self.team)
            if event.key in (pygame.K_LEFT, pygame.K_BACKSPACE):
                self.team = teams[(idx - 1) % len(teams)]
            elif event.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.team = teams[(idx + 1) % len(teams)]
            return None
        # text fields: name / friend_id
        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            self.selected = (self.selected + 1) % self.field_count
            return None
        if event.key == pygame.K_BACKSPACE:
            if self.selected_name() == "name":
                self.name = self.name[:-1]
            else:
                self.friend_id = self.friend_id[:-1]
            return None
        ch = event.unicode
        if ch and ch.isprintable():
            if self.selected_name() == "name" and len(self.name) < 16:
                self.name += ch
            elif self.selected_name() == "friend_id" and len(self.friend_id) < 32:
                self.friend_id += ch
        return None

    def get_result(self):
        return {"action": "quit" if self.quit_requested else "start",
                "name": self.name.strip(),
                "team": self.team,
                "friend_id": self.friend_id.strip()}

    def valid_friend_id(self):
        """Basic IP:PORT validation for the friend field."""
        parts = self.friend_id.strip().split(":")
        if len(parts) != 2:
            return False
        ip_parts = parts[0].split(".")
        if len(ip_parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in ip_parts):
            # allow hostnames too
            if not parts[0]:
                return False
        return parts[1].isdigit() and 0 < int(parts[1]) < 65536

    def draw(self, my_id=""):
        self.screen.fill((15, 15, 25))
        title = self.title_font.render("P2P SWARM ARENA", True, (100, 220, 255))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 60))
        if my_id:
            id_surf = self.small_font.render(f"Your ID: {my_id}", True, (150, 150, 180))
            self.screen.blit(id_surf, (WIDTH // 2 - id_surf.get_width() // 2, 115))

        rows = [
            ("name", f"Name  : {self.name or ''}_" if self.selected_name() == "name" else f"Name  : {self.name}"),
            ("team", f"Team  : < {self.team.upper()} >  (Left/Right)"),
            ("friend_id", f"Friend: {self.friend_id or ''}_" if self.selected_name() == "friend_id" else f"Friend: {self.friend_id or '(empty = host new swarm)'}"),
        ]
        y = 180
        for key, text in rows:
            active = self.selected_name() == key
            color = (255, 255, 100) if active else (200, 200, 200)
            prefix = "> " if active else "  "
            surf = self.font.render(prefix + text, True, color)
            self.screen.blit(surf, (WIDTH // 2 - 220, y))
            if key == "team":
                box = pygame.Rect(WIDTH // 2 - 220, y - 4, 440, 34)
                pygame.draw.rect(self.screen, TEAM_COLORS.get(self.team, (200, 200, 200)), box, 2, border_radius=6)
            y += 48

        # Start button
        active = self.selected_name() == "start"
        btn = pygame.Rect(WIDTH // 2 - 120, y + 10, 240, 48)
        pygame.draw.rect(self.screen, (40, 160, 60) if active else (30, 90, 45), btn, border_radius=8)
        pygame.draw.rect(self.screen, (100, 255, 150) if active else (60, 140, 80), btn, 2, border_radius=8)
        label = self.font.render("[  START  ]", True, (255, 255, 255))
        self.screen.blit(label, (WIDTH // 2 - label.get_width() // 2, y + 22))

        hint = self.small_font.render("Up/Down/Tab: pilih | Enter: mulai | Esc: keluar", True, (130, 130, 150))
        self.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 40))
        if self.friend_id and not self.valid_friend_id():
            warn = self.small_font.render("Format Friend: IP:PORT  (contoh 192.168.1.5:55555)", True, (255, 120, 120))
            self.screen.blit(warn, (WIDTH // 2 - warn.get_width() // 2, HEIGHT - 65))
        pygame.display.flip()


class PauseMenu:
    """In-game pause overlay: resume / panel settings / exit to menu / quit.

    Navigation: Up/Down pilih, Left/Right toggle & ubah alpha,
    Enter/Z konfirmasi, P/Esc tutup (resume).
    handle_event returns: None | 'resume' | 'to_menu' | 'quit_app'.
    """

    OPTIONS = ["leaderboard", "netinfo", "chat", "alpha", "to_menu", "quit_app"]

    LABELS = {
        "leaderboard": "Leaderboard",
        "netinfo": "Info Jaringan",
        "chat": "Kotak Chat",
        "alpha": "Transparansi",
        "to_menu": "Exit: ke Menu Awal",
        "quit_app": "Exit: Keluar Aplikasi",
    }

    def __init__(self, screen, settings):
        pygame.font.init()
        self.screen = screen
        self.settings = settings
        self.selected = 0
        self.title_font = pygame.font.SysFont("consolas", 32, bold=True)
        self.font = pygame.font.SysFont("consolas", 20)
        self.small_font = pygame.font.SysFont("consolas", 14)

    def _toggle(self, opt):
        if opt == "leaderboard":
            self.settings.show_leaderboard = not self.settings.show_leaderboard
        elif opt == "netinfo":
            self.settings.show_netinfo = not self.settings.show_netinfo
        elif opt == "chat":
            self.settings.show_chat = not self.settings.show_chat

    def _value_text(self, opt):
        if opt == "leaderboard":
            return "ON" if self.settings.show_leaderboard else "OFF"
        if opt == "netinfo":
            return "ON" if self.settings.show_netinfo else "OFF"
        if opt == "chat":
            return "ON" if self.settings.show_chat else "OFF"
        if opt == "alpha":
            return f"< {self.settings.panel_alpha} >"
        return ""

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return "quit_app"
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_p, pygame.K_ESCAPE):
            return "resume"
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(self.OPTIONS)
            return None
        if event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(self.OPTIONS)
            return None
        opt = self.OPTIONS[self.selected]
        if event.key in (pygame.K_LEFT, pygame.K_a):
            if opt == "alpha":
                self.settings.alpha_down()
            elif opt in ("leaderboard", "netinfo", "chat"):
                self._toggle(opt)
            self.settings.save()
            return None
        if event.key in (pygame.K_RIGHT, pygame.K_d):
            if opt == "alpha":
                self.settings.alpha_up()
            elif opt in ("leaderboard", "netinfo", "chat"):
                self._toggle(opt)
            self.settings.save()
            return None
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_z):
            if opt in ("leaderboard", "netinfo", "chat"):
                self._toggle(opt)
                self.settings.save()
                return None
            if opt in ("to_menu", "quit_app"):
                return opt
            return None
        return None

    def draw(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 220, 90, 440, 380)
        panel = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
        panel.fill((18, 18, 28, 225))
        self.screen.blit(panel, box.topleft)
        pygame.draw.rect(self.screen, (90, 90, 140), box, 2, border_radius=10)
        title = self.title_font.render("PAUSE", True, (255, 255, 255))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 110))
        hint = self.small_font.render("P/Esc: lanjut | Up/Down: pilih | Left/Right: ubah", True, (150, 150, 170))
        self.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 150))
        y = 190
        for i, opt in enumerate(self.OPTIONS):
            active = i == self.selected
            if opt in ("to_menu", "quit_app") and i == 4:
                sep = self.small_font.render("--- EXIT ---", True, (150, 120, 120))
                self.screen.blit(sep, (WIDTH // 2 - sep.get_width() // 2, y))
                y += 26
            color = (255, 255, 100) if active else (200, 200, 200)
            prefix = "> " if active else "  "
            val = self._value_text(opt)
            text = f"{prefix}{self.LABELS[opt]}" + (f": {val}" if val else "")
            surf = self.font.render(text, True, color)
            self.screen.blit(surf, (WIDTH // 2 - 190, y))
            y += 40
        pygame.display.flip()

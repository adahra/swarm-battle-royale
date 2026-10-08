"""Persistent UI settings for P2P Swarm Game."""

import json

SETTINGS_FILE = "settings.json"
MIN_ALPHA = 60
MAX_ALPHA = 230
ALPHA_STEP = 10


class GameSettings:
    """Toggles + transparency for HUD panels. Persisted to settings.json."""

    def __init__(self, show_leaderboard=True, show_netinfo=True,
                 show_chat=True, panel_alpha=170):
        self.show_leaderboard = show_leaderboard
        self.show_netinfo = show_netinfo
        self.show_chat = show_chat
        self.panel_alpha = int(panel_alpha)

    def to_dict(self):
        return {
            "show_leaderboard": self.show_leaderboard,
            "show_netinfo": self.show_netinfo,
            "show_chat": self.show_chat,
            "panel_alpha": self.panel_alpha,
        }

    def alpha_up(self):
        self.panel_alpha = min(MAX_ALPHA, self.panel_alpha + ALPHA_STEP)

    def alpha_down(self):
        self.panel_alpha = max(MIN_ALPHA, self.panel_alpha - ALPHA_STEP)

    def save(self, filename=SETTINGS_FILE):
        try:
            with open(filename, "w") as f:
                json.dump(self.to_dict(), f)
        except OSError:
            pass

    @classmethod
    def load(cls, filename=SETTINGS_FILE):
        try:
            with open(filename) as f:
                d = json.load(f)
            s = cls()
            for k in ("show_leaderboard", "show_netinfo", "show_chat"):
                if isinstance(d.get(k), bool):
                    setattr(s, k, d[k])
            if isinstance(d.get("panel_alpha"), (int, float)):
                s.panel_alpha = max(MIN_ALPHA, min(MAX_ALPHA, int(d["panel_alpha"])))
            return s
        except (OSError, ValueError):
            return cls()

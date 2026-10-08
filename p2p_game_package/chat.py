"""Chat module for P2P Swarm Game."""

import pygame
import time
from .config import CHAT_HISTORY_MAX, CHAT_INPUT_HEIGHT, CHAT_HISTORY_HEIGHT, TEAM_COLORS, CHAT_MAX_LENGTH


class Chat:
    """Chat system for player communication."""

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
        if not isinstance(text, str):
            return
        text = text.strip()[:CHAT_MAX_LENGTH]
        if not text:
            return
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

    def draw(self, screen, width, height, my_id, alpha=170):
        if not self.font:
            self.init_fonts()

        history_y = height - CHAT_INPUT_HEIGHT - CHAT_HISTORY_HEIGHT
        bg = pygame.Surface((width, CHAT_HISTORY_HEIGHT), pygame.SRCALPHA)
        bg.fill((20, 20, 20, alpha))
        screen.blit(bg, (0, history_y))

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
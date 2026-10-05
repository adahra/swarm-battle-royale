"""Main entry point for P2P Swarm Game."""

import argparse
import sys
import time
import threading
import pygame

from .config import DEFAULT_PORT, WIDTH, HEIGHT, MAX_FPS, TEAM_COLORS, DEFAULT_TEAM, FRIENDLY_FIRE, MAX_ALLOWED_DISTANCE_PER_FRAME, MAX_STRIKES, PEER_TIMEOUT, PLAYER_SPEED, PLAYER_SIZE, PROJECTILE_DAMAGE
from .network import Network, create_handshake_message, create_chat_message, create_respawn_message, create_shoot_message, create_hit_message, create_host_announce_message, create_update_message
from .player import Player
from .peer_manager import PeerManager
from .renderer import Renderer
from .chat import Chat
from .projectile import Projectile
from .menu import MainMenu
from .reconnection import ReconnectionManager


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

    # In-game main menu (replaces terminal prompt)
    menu = MainMenu(renderer.screen, name=player.name, team=player.team)
    menu_result = None
    clock = pygame.time.Clock()
    while menu_result is None:
        for event in pygame.event.get():
            menu_result = menu.handle_event(event)
            if menu_result is not None:
                break
        menu.draw(my_id=network.my_id)
        clock.tick(MAX_FPS)
    result = menu.get_result()
    if result["action"] == "quit":
        network.close()
        renderer.quit()
        return
    if result["name"]:
        player.name = result["name"]
    player.team = result["team"]
    player.color = TEAM_COLORS[player.team]
    pygame.display.set_caption(f"P2P Swarm Game | Port: {args.port} | {player.name} ({player.team})")
    print(f"[*] Name: {player.name} | Team: {player.team}")

    # Load saved peers for reconnection
    reconnect.load_state()

    # Initial connection (friend ID from menu, or empty = host new swarm)
    target_input = result["friend_id"]
    if target_input:
        peer_manager.add_known_peer(target_input)
        network.send(create_handshake_message(player, network.my_id), target_input)

    # Start receiver thread
    running = [True]
    recv_thread = threading.Thread(
        target=_receiver_loop, args=(network, peer_manager, chat, projectiles, network.my_id, player, running), daemon=True
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


def _receiver_loop(network, peer_manager, chat, projectiles, my_id, my_player, running_flag):
    import select
    while running_flag[0]:
        try:
            message, addr = network.receive()
            if message:
                from .network import process_message
                process_message(message, peer_manager, network, chat, projectiles, my_id, my_player)
        except Exception:
            if running_flag[0]:
                pass
            break


if __name__ == "__main__":
    main()
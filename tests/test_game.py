"""Unit tests for P2P Swarm Game package (no pygame display / no real network)."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from p2p_game_package.config import MAX_ALLOWED_DISTANCE_PER_FRAME, MAX_STRIKES
from p2p_game_package.player import Player
from p2p_game_package.projectile import Projectile
from p2p_game_package.peer_manager import PeerManager
from p2p_game_package.chat import Chat
from p2p_game_package import network as netmod


def test_player_take_damage_and_death():
    p = Player(name="A", team="red")
    assert p.health == 100 and p.alive
    assert p.take_damage(25) == "hit"
    assert p.health == 75
    assert p.take_damage(75, attacker_id="enemy:1") == "death"
    assert not p.alive and p.health == 0
    # dead player ignores damage
    assert p.take_damage(10) is False


def test_player_invulnerable():
    p = Player(name="B")
    p.invulnerable_until = time.time() + 10
    assert p.take_damage(50) is False
    assert p.health == 100


def test_player_respawn_and_heal_and_kill():
    p = Player(name="C")
    p.take_damage(200)
    assert not p.alive
    p.respawn()
    assert p.alive and p.health == p.max_health
    p.take_damage(60)
    p.heal(100)
    assert p.health == p.max_health
    p.add_kill()
    assert p.kills == 1 and p.score == 100


def test_player_shoot_direction():
    p = Player(name="D")
    p.x, p.y = 100, 100
    p.last_shot = 0
    proj = p.shoot(200, 100)
    assert proj is not None
    assert proj.vx > 0 and abs(proj.vy) < 1e-6
    # cooldown blocks immediate second shot
    assert p.shoot(200, 100) is None
    # dead player cannot shoot
    p.alive = False
    p.last_shot = 0
    assert p.shoot(200, 100) is None


def test_projectile_update_and_from_state():
    pr = Projectile(100, 100, 5, 0, "red", "1.2.3.4:5")
    pr.update()
    assert pr.x == 105
    st = pr.get_state()
    pr2 = Projectile.from_state(st)
    assert (pr2.x, pr2.vx, pr2.team, pr2.owner_id) == (pr.x, pr.vx, pr.team, pr.owner_id)
    # out of bounds kills
    pr3 = Projectile(-5, 100, -10, 0, "red", "x")
    pr3.update()
    assert not pr3.alive
    # expiry kills
    pr4 = Projectile(100, 100, 0, 0, "red", "x")
    pr4.spawn_time -= 10
    pr4.update()
    assert not pr4.alive


def _valid_update(x=10, y=10):
    return {"x": x, "y": y, "color": [255, 0, 0], "name": "P",
            "team": "red", "health": 100, "max_health": 100,
            "score": 0, "kills": 0, "deaths": 0, "alive": True, "latency": 5}


def test_peer_validate_and_strikes():
    pm = PeerManager("me:1", max_distance=12.5, max_strikes=2, timeout=10)
    assert pm.add_known_peer("peer:2") is True
    assert pm.add_known_peer("peer:2") is False  # duplicate
    assert pm.add_known_peer("me:1") is False  # self
    pm.validate_and_update("peer:2", _valid_update(10, 10))
    assert "peer:2" in pm.peers
    # teleport far -> strike, position unchanged
    pm.validate_and_update("peer:2", _valid_update(500, 500))
    assert pm.peers["peer:2"]["strike_count"] == 1
    assert pm.peers["peer:2"]["x"] == 10
    pm.validate_and_update("peer:2", _valid_update(500, 500))
    pm.validate_and_update("peer:2", _valid_update(500, 500))
    assert pm.peers["peer:2"]["strike_count"] == 3  # exceeds max


def test_peer_timeout_and_host_election():
    pm = PeerManager("b:2", timeout=0.05)
    pm.add_known_peer("a:1")
    pm.validate_and_update("a:1", _valid_update())
    time.sleep(0.08)
    pm.cleanup_timed_out()
    assert "a:1" not in pm.peers
    # host election picks lowest id
    pm2 = PeerManager("b:2")
    pm2.last_host_change = 0
    pm2.host_id = "zzz"
    pm2.add_known_peer("a:1")
    pm2.elect_new_host()
    assert pm2.get_host_id() == "a:1"
    assert not pm2.is_host()
    # remove host triggers re-election attempt
    pm2.remove_peer("a:1")
    assert "a:1" not in pm2.known_peers


def test_peer_save_load(tmp_path):
    pm = PeerManager("me:1")
    pm.add_known_peer("x:1")
    f = str(tmp_path / "peers.json")
    pm.save_peers(f)
    assert json.load(open(f)) == ["x:1"]
    pm2 = PeerManager("me:1")
    pm2.load_peers(f)
    assert "x:1" in pm2.known_peers
    pm2.load_peers(str(tmp_path / "missing.json"))  # should not raise


def test_network_messages_and_ping_pong():
    p = Player(name="N")
    p.x, p.y = 5, 6
    m = netmod.create_update_message(p, "me:1", {"a:1"}, latency=9)
    assert m["sender_id"] == "me:1" and m["swarm_list"] == ["a:1"] and m["latency"] == 9
    assert netmod.create_handshake_message(p, "me:1")["swarm_list"] == ["me:1"]
    assert netmod.create_chat_message("me:1", "hi", "red")["text"] == "hi"
    pr = Projectile(1, 2, 3, 4, "blue", "me:1")
    sm = netmod.create_shoot_message("me:1", pr)
    assert sm["vx"] == 3 and sm["owner_id"] == "me:1"
    assert netmod.create_hit_message("me:1", "t:1", 25)["damage"] == 25
    assert netmod.create_host_announce_message("me:1", "h:1")["host_id"] == "h:1"

    # ping/pong EMA without sockets: stub send
    n = netmod.Network.__new__(netmod.Network)
    n.my_id, n.sequence, n.pending_pings, n.latencies = "me:1", 0, {}, {}
    n.send = lambda payload, target: setattr(n, "_last", (payload, target))
    n.send_ping("p:1")
    assert n.pending_pings["p:1"][0] == 1
    n.pending_pings["p:1"] = (1, time.time() - 0.1)
    n.handle_pong({"sender_id": "p:1", "seq": 1})
    assert "p:1" not in n.pending_pings and n.latencies["p:1"] > 0
    # wrong seq ignored for latency but still popped
    n.pending_pings["p:1"] = (5, time.time())
    n.handle_pong({"sender_id": "p:1", "seq": 99})
    assert "p:1" not in n.pending_pings


def test_network_receive_uses_buffer_size():
    # regression: receive() referenced RECV_BUFFER_SIZE which was not imported
    import socket
    n = netmod.Network.__new__(netmod.Network)
    s1, s2 = socket.socketpair()
    try:
        s1.setblocking(False)
        n.sock = s1
        s2.send(json.dumps({"hello": 1}).encode())
        msg, _ = n.receive()
        assert msg == {"hello": 1}
    finally:
        s1.close(); s2.close()


def test_main_imports_projectile_damage():
    # regression: main.py game loop sends hit with PROJECTILE_DAMAGE;
    # missing import crashed the shooter on hit -> looked like "shooter exits"
    import ast
    tree = ast.parse(open("p2p_game_package/main.py").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("config"):
            imported.update(a.asname or a.name for a in node.names)
    src = open("p2p_game_package/main.py").read()
    assert "PROJECTILE_DAMAGE" in src
    assert "PROJECTILE_DAMAGE" in imported


def test_main_menu_navigation_and_result():
    import pygame
    pygame.display.init()
    screen = pygame.display.set_mode((100, 100))
    from p2p_game_package.menu import MainMenu
    m = MainMenu(screen, name="Bob", team="red")
    assert m.selected_name() == "name"
    # type into name
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_x, "unicode": "x"}))
    assert m.name == "Bobx"
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_BACKSPACE, "unicode": ""}))
    assert m.name == "Bob"
    # down to team, cycle right
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN, "unicode": ""}))
    assert m.selected_name() == "team"
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RIGHT, "unicode": ""}))
    assert m.team == "blue"
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_LEFT, "unicode": ""}))
    assert m.team == "red"
    # down to friend, type, validate
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN, "unicode": ""}))
    assert m.selected_name() == "friend_id"
    for ch in "1.2.3.4:5555":
        m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": 0, "unicode": ch}))
    assert m.valid_friend_id() is True
    m.friend_id = "oops"
    assert m.valid_friend_id() is False
    m.friend_id = "1.2.3.4:5555"
    # down to start, press enter
    m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN, "unicode": ""}))
    assert m.selected_name() == "start"
    assert m.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "unicode": ""})) == "start"
    r = m.get_result()
    assert (r["action"], r["name"], r["team"], r["friend_id"]) == ("start", "Bob", "red", "1.2.3.4:5555")
    # esc quits
    m2 = MainMenu(screen)
    assert m2.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE, "unicode": ""})) == "quit"
    assert m2.get_result()["action"] == "quit"
    m.draw(my_id="1.2.3.4:55555")  # must not crash
    pygame.display.quit()


def test_chat_history_capped():
    c = Chat(max_history=3)
    for i in range(5):
        c.add_message("p:1", f"m{i}")
    assert len(c.messages) == 3 and c.messages[-1]["text"] == "m4"


def test_process_message_update_chat_shoot_ping():
    pm = PeerManager("me:1")
    n = netmod.Network.__new__(netmod.Network)
    n.my_id = "me:1"
    sent = []
    n.send = lambda payload, target: sent.append((payload, target))
    n.handle_pong = lambda m: sent.append(("pong-handled", m))
    chat = Chat()
    projectiles = []
    me = Player(name="Me")

    netmod.process_message({**_valid_update(20, 20), "type": "update",
                            "sender_id": "p:1", "swarm_list": ["p:1", "q:1"]},
                           pm, n, chat, projectiles, "me:1", me)
    assert "p:1" in pm.peers and "q:1" in pm.known_peers

    netmod.process_message({"type": "chat", "sender_id": "p:1", "text": "yo", "team": "red"},
                           pm, n, chat, projectiles, "me:1", me)
    assert chat.messages[-1]["text"] == "yo"

    netmod.process_message({"type": "shoot", "sender_id": "p:1", "x": 1, "y": 2,
                            "vx": 3, "vy": 4, "team": "red", "owner_id": "p:1"},
                           pm, n, chat, projectiles, "me:1", me)
    assert len(projectiles) == 1

    netmod.process_message({"type": "ping", "sender_id": "p:1", "seq": 7},
                           pm, n, chat, projectiles, "me:1", me)
    assert sent[-1][0]["type"] == "pong"

    netmod.process_message({"type": "host_announce", "sender_id": "p:1", "host_id": "p:1"},
                           pm, n, chat, projectiles, "me:1", me)
    assert pm.host_id == "p:1"

    # message without sender ignored
    netmod.process_message({"type": "chat", "text": "x"}, pm, n, chat, projectiles, "me:1", me)

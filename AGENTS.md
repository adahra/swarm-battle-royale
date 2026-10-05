# P2P Game - Agent Instructions

## Project Overview
Two entry points for the same UDP battle arena game (pygame rendering):
- **Modular (recommended)**: `p2p_game_package/` — `main.py` (entry), `menu.py`, `config.py`, `network.py`, `peer_manager.py`, `player.py`, `projectile.py`, `renderer.py`, `chat.py`, `reconnection.py`.
- **Legacy**: `p2p_game_swarm.py` (~1060 lines, single file). No menu; uses a terminal `input()` connect prompt. Do NOT add new features here — keep it as-is unless asked.
- **Tests**: `tests/test_game.py` (headless, `SDL_VIDEODRIVER=dummy`). Run with `python -m pytest tests/ -q`.

## Running the Game
```bash
python -m p2p_game_package.main [-p PORT] [-n NAME] [-t TEAM] [--no-stun]
python p2p_game_swarm.py [-p PORT] [-n NAME] [-t TEAM] [--no-stun]   # legacy
```

- **Default port**: 55555. Multiple instances on one machine require unique `-p` values.
- **STUN discovery**: Auto-detects public IP:port via RFC 5389 Binding Request. Disable with `--no-stun`.
- ** Startup flow (modular)**: CLI flags prefill the in-game `MainMenu` (name/team/friend `IP:PORT`) → START → receiver + reconnect threads → game loop. Empty friend field = host new swarm.

## Flags
| Flag | Description | Default |
|------|-------------|---------|
| `-p, --port` | Local UDP port | 55555 |
| `-n, --name` | Display name (menu prefill) | `Player_XXXX` |
| `-t, --team` | Team (red/blue/green/yellow, menu prefill) | red |
| `--no-stun` | Disable STUN public IP discovery | (enabled) |

## Dependencies
- `pip install pygame pytest` (pytest for tests only)
- Stdlib: `socket`, `threading`, `json`, `argparse`, `math`, `random`, `time`, `os`, `struct`, `select`

## Architecture & Key Conventions

### Network (`network.py`)
- **UDP sockets** with STUN for public endpoint discovery. Binds to local IP, XOR-encodes public IP:port for clients.
- `Network.my_id` format: `IP:PORT` — updated if STUN discovers a public endpoint.
- Message factories: `create_update/handshake/chat/shoot/hit/respawn/ping/pong/host_announce_message()`; inbound routing in `process_message()`.
- `receive()` requires `RECV_BUFFER_SIZE` imported from `config` (was a past `NameError` — covered by regression test).

### Peer Management (`peer_manager.py`)
- **Peer ID format**: `IP:PORT` persistently stored in `peers.json`.
- **Movement validation**: Max distance per frame = `PLAYER_SPEED * 2.5` = 12.5px. > 5 strikes triggers kick (anti-cheat).
- **Peer timeout**: Removed if no updates received for 3.0s total (`PEER_TIMEOUT`).
- **Ping mechanism**: 1s interval per peer; sequence-based RTT tracking with exponential moving average (EMA).
- **Swarm discovery**: Host broadcasts `swarm_list` on every update; clients merge lists via RPC.
- **Broadcast scope**: Sends to `known_peers` set only — not a global broadcast.

### Host Election
- Lowest IP:port elected deterministically as host.
- Auto-migrates on host disappearance — 5s timeout before re-election (`HOST_MIGRATION_TIMEOUT`).
- Host announces its ID via `host_announce` messages.

### Reconnections (`reconnection.py`)
- Auto-reconnects to known peers after disconnect.
- Session state saved to `peers.json`; loaded on startup via `ReconnectionManager.load_state()`.
- Reconnection loop runs every 1s; sends handshake messages to known peers.

### Menu (`menu.py`)
- `MainMenu(screen, name, team)` — keyboard-driven: `Tab`/`↑`/`↓` select, `←`/`→` cycle team, `Enter` start, `Esc` quit. `get_result()` → `{action, name, team, friend_id}`. `valid_friend_id()` checks `IP:PORT` format.

### Combat (`player.py`, `projectile.py`, `main.py` loop)
- `main.py` game loop MUST import every `config` name it uses (past crash: missing `PROJECTILE_DAMAGE` killed the shooter on first hit — regression-tested via AST check in `tests/test_game.py`).
- Shooter checks only its own projectiles (`proj.owner_id == my_id`) against alive peers; respect `FRIENDLY_FIRE=False` (skip same team); send `create_hit_message(..., PROJECTILE_DAMAGE)`.
- `take_damage()` returns `"death"` only when `attacker_id != my_id`; tests must pass `attacker_id` to assert death.

## Controls
### Menu
| Key | Action |
|-----|--------|
| `Tab` / `↑` / `↓` | Select field |
| `←` / `→` (Team) | Change team |
| `Enter` | Confirm / Start |
| `Esc` | Quit |

### In game
| Key | Action |
|-----|--------|
| WASD / Arrow Keys | Move |
| Mouse Click | Shoot |
| `/` | Open chat |
| `Tab` | Switch team |
| `F5` | Manual save peers |

## File Structure
```
p2p_game_swarm.py         # Legacy single-file executable (~1060 lines)
p2p_game_package/         # Modular version: main/menu/config/network/peer_manager/player/projectile/renderer/chat/reconnection.py
tests/test_game.py        # Unit tests (headless, no sockets/display)
peers.json                # Persisted known_peer list (auto-generated)
```

## Verification
- Tests: `python -m pytest tests/ -q` (must be green before/after changes).
- Static check: `python -m pyflakes p2p_game_package/*.py` (only unused-import warnings acceptable; zero undefined names).
- Run locally: `python -m p2p_game_package.main -p 60000 -n TestPlayer`
- Port conflicts → change with `-p`. Unique ports required per instance.
- Reconnect behavior: Disconnect, restart game — it will auto-reconnect to peers from `peers.json`.

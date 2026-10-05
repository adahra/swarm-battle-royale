# P2P Game - Swarm Multiplayer Battle Arena

A UDP P2P multiplayer game with pygame rendering. Features host migration, STUN public IP discovery, anti-cheat movement validation, automatic peer reconnection, and an in-game main menu.

Two entry points: the legacy single-file `p2p_game_swarm.py`, and the modular `p2p_game_package/` (same game, split into modules + menu + tests).

## Quick Start

```bash
# Install dependencies
pip install pygame pytest

# Run modular version (recommended, has main menu + all fixes)
python -m p2p_game_package.main -n "YourName" -t red

# ...or legacy single file
python p2p_game_swarm.py -n "YourName" -t red
```

### Multiple instances (same machine)
```bash
# Terminal 1
python -m p2p_game_package.main -p 55555 -n Player1 -t red

# Terminal 2
python -m p2p_game_package.main -p 55556 -n Player2 -t blue
```

### Connect across LAN/Internet
1. Launch the game — the **main menu** shows your public `IP:PORT`.
2. Fill in **Name**, pick **Team** (`←`/`→`), and enter a friend's `IP:PORT` — or leave Friend empty to host a new swarm.
3. Press **START**. Peers auto-discover each other via swarm list broadcast. Known peers persist to `peers.json` and auto-reconnect on restart.

### Flags
| Flag | Description | Default |
|------|-------------|---------|
| `-p, --port` | Local UDP port | 55555 |
| `-n, --name` | Display name (prefilled in menu) | `Player_XXXX` |
| `-t, --team` | Team (prefilled in menu) | red |
| `--no-stun` | Disable STUN public IP discovery | enabled |

## Features

- **P2P UDP networking** - No central server required
- **STUN support** - Auto-discovers public IP:port for internet play
- **In-game main menu** - Name/team/friend setup with `IP:PORT` validation (modular version; legacy file still uses a terminal prompt)
- **Host migration** - Deterministic election (lowest IP:port); auto-failover on host loss
- **Swarm discovery** - Host broadcasts `known_peers` list; all clients merge
- **Reconnection** - Persists peer list to `peers.json`, auto-reconnects on restart
- **Anti-cheat** - Movement validated (max 12.5px/frame, 5 strikes = kick)
- **Ping/RTT tracking** - 1s interval, sequence-based, EMA latency average

## Controls

### Menu
| Key | Action |
|-----|--------|
| `Tab` / `↑` / `↓` | Select field |
| `←` / `→` (on Team) | Change team |
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

## Project Structure

```
p2p_game_swarm.py         # Legacy single-file executable (~1060 lines)
p2p_game_package/         # Modular version (recommended)
  main.py                 # Entry point: menu -> receiver threads -> game loop
  menu.py                 # In-game main menu (MainMenu)
  config.py               # Constants (ports, gameplay, teams, timeouts)
  network.py              # UDP + STUN + message factories + process_message
  peer_manager.py         # Peers, anti-cheat, host election, timeouts
  player.py               # Player state, movement, shooting, damage/respawn
  projectile.py           # Projectile physics + serialization
  renderer.py             # pygame drawing (players, HUD, leaderboard, chat)
  chat.py                 # Chat history + input
  reconnection.py         # Auto-reconnect + peers.json persistence
tests/
  test_game.py            # Unit tests (14 tests, no display/network needed)
peers.json                # Persisted peer list (auto-generated)
```

## Tests

```bash
python -m pytest tests/ -q
```

Headless-safe (`SDL_VIDEODRIVER=dummy`): covers player damage/death/respawn/shoot, projectile physics, peer validation/strikes/timeout/host-election/save-load, message factories, ping/pong EMA, `process_message`, chat cap, menu navigation, and import-regression checks.

## Requirements

- Python 3.8+
- pygame (`pip install pygame`)
- pytest (`pip install pytest`, tests only)

No build step, no CI - runs directly as Python script.

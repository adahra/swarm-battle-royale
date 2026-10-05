# P2P Game - Swarm Multiplayer Battle Arena

A single-file UDP P2P multiplayer game with pygame rendering. Features host migration, STUN public IP discovery, anti-cheat movement validation, and automatic peer reconnection.

## Quick Start

```bash
# Install dependency
pip install pygame

# Run (default port 55555)
python p2p_game_swarm.py -n "YourName" -t red
```

### Multiple instances (same machine)
```bash
# Terminal 1
python p2p_game_swarm.py -p 55555 -n Player1 -t red

# Terminal 2  
python p2p_game_swarm.py -p 55556 -n Player2 -t blue
```

### Connect across LAN/Internet
1. First player runs game, shares their public `IP:PORT` (shown on startup)
2. Second player runs game, then at prompt enters: `Masukkan ID P2P Teman (IP:PORT)`
3. Peers auto-discover each other via swarm list broadcast

### Flags
| Flag | Description | Default |
|------|-------------|---------|
| `-p, --port` | Local UDP port | 55555 |
| `-n, --name` | Display name | Player_XXXX |
| `-t, --team` | Team (red/blue/green/yellow) | red |
| `--no-stun` | Disable STUN public IP discovery | enabled |

## Features

- **P2P UDP networking** - No central server required
- **STUN support** - Auto-discovers public IP:port for internet play
- **Host migration** - Deterministic election (lowest IP:port); auto-failover on host loss
- **Swarm discovery** - Host broadcasts `known_peers` list; all clients merge
- **Reconnection** - Persists peer list to `peers.json`, auto-reconnects on restart
- **Anti-cheat** - Movement validated server-side (max 12.5px/frame, 5 strikes = kick)
- **Ping/RTT tracking** - 1s interval, sequence-based, EMA latency average

## Controls

| Key | Action |
|-----|--------|
| WASD / Arrow Keys | Move |
| Mouse Click | Shoot |
| `/` | Open chat |
| `Tab` | Switch team |
| `F5` | Manual save peers |

## Project Structure

```
p2p_game_swarm.py    # Single executable (~1060 lines)
peers.json           # Persisted peer list (auto-generated)
```

## Requirements

- Python 3.8+
- pygame (`pip install pygame`)

No build step, no tests, no CI - runs directly as Python script.
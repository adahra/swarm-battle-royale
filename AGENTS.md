# P2P Game - Agent Instructions

## Project Overview
**Single file**: `p2p_game_swarm.py` (1060 lines, UDP battle arena with pygame rendering)

## Running the Game
```bash
python p2p_game_swarm.py [-p PORT] [-n NAME] [-t TEAM] [--no-stun]
```

**Ports**: Default 55555. Each instance needs unique port if running multiple on same machine.  
**STUN discovery**: Auto-detects public IP via STUN (RFC 5389 Binding Request); disable with `--no-stun`.

## Dependencies
- **Installed**: `pygame` only (`pip install pygame`)
- **Stdlib**: `socket`, `threading`, `json`, `argparse`, `math`, `random`, `time`, `os`, `struct`, `select`

## Architecture Notes
- **Network class**: UDP sockets + STUN for public endpoint discovery (binds to local IP, XOR encodes public IP:port for clients)
- **Reconnection management**: Auto-reconnects to known peers after disconnect; uses session state saved to `peers.json`
- **Host election system**: Lowest IP:port elected deterministically as host; auto-migrates on host disappearance (5s timeout)
- **Threading model**: 
  - `receiver_loop()` daemon thread: network receive/process loop  
  - `reconnect` daemon loop: periodic reconnection attempts (1s interval)  
  - Main = game loop with pygame events and logic

## Key Conventions & Guardrails
- **Peer ID format**: `IP:PORT` (e.g., `192.168.1.5:55555`) persistently stored in `peers.json`
- **Movement validation**: Max distance = 5px/frame * 2.5 = 12.5px; > 5 strikes triggers kick (anti-cheat)
- **Peer timeout**: Removed if no updates received for 3 seconds total
- **Ping mechanism**: 1s ping interval per peer, sequence-based RTT tracking with exponential moving average (EMA)
- **Swarm discovery**: Host broadcasts `swarm_list` on every update; clients merge lists via remote procedure call
- **Broadcast scope**: Sends to `known_peers` set only (not global broadcast)

## Testing & Verification
- Run locally: `python p2p_game_swarm.py -p 60000 -n TestPlayer`
- Port conflicts → change with `-p`. Unique ports required per instance.
- Reconnect behavior: Disconnect, reconnect to same peer ID via peers.json.

## File Structure
```
p2p_game_swarm.py    # Single executable (1060 lines)
peers.json           # Persisted known_peer list
```

No additional files, no tests, no CI/CD, no build step.

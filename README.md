# Waystone MUD

A Multi-User Dungeon set in Patrick Rothfuss's Kingkiller Chronicle universe.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the server
uv run python -m waystone

# Connect (in another terminal)
telnet localhost 4000
```

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/
```

## Project Structure

```
waystone/
├── src/waystone/
│   ├── network/       # Telnet/WebSocket servers
│   ├── database/      # SQLAlchemy models
│   ├── game/
│   │   ├── world/     # Rooms, areas, navigation
│   │   └── commands/  # Player command handlers
│   └── utils/         # Helpers and formatters
├── data/world/        # YAML world definitions
├── tests/             # pytest test suite
└── scripts/           # Admin and setup scripts
```

## Deployment (DigitalOcean Droplet)

### Prerequisites

- DigitalOcean account
- SSH key configured
- Domain (optional)

### 1. Create Droplet

```bash
# Create a $6/month droplet (1GB RAM, 1 vCPU)
doctl compute droplet create waystone-mud \
  --image ubuntu-24-04-x64 \
  --size s-1vcpu-1gb \
  --region nyc1 \
  --ssh-keys <your-ssh-key-id>
```

Or via the DigitalOcean web console:
- Image: Ubuntu 24.04 LTS
- Plan: Basic $6/mo (1GB RAM, 1 vCPU, 25GB SSD)
- Region: Choose closest to your players

### 2. Initial Server Setup

```bash
# SSH into your droplet
ssh root@<droplet-ip>

# Update system
apt update && apt upgrade -y

# Install Python 3.12+ and dependencies
apt install -y python3.12 python3.12-venv git

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Create app user (don't run as root)
useradd -m -s /bin/bash waystone
```

### 3. Deploy Application

```bash
# Switch to app user
su - waystone

# Clone repository
git clone https://github.com/<your-username>/waystone.git
cd waystone

# Install dependencies
uv sync

# Test run
uv run python -m waystone
# Ctrl+C to stop
```

### 4. Create Systemd Service

```bash
# Back to root
exit

# Create service file
cat > /etc/systemd/system/waystone.service << 'EOF'
[Unit]
Description=Waystone MUD Server
After=network.target

[Service]
Type=simple
User=waystone
WorkingDirectory=/home/waystone/waystone
ExecStart=/home/waystone/.local/bin/uv run python -m waystone
Restart=always
RestartSec=5
Environment=WAYSTONE_HOST=0.0.0.0
Environment=WAYSTONE_PORT=4000

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable waystone
systemctl start waystone

# Check status
systemctl status waystone
```

### 5. Configure Firewall

```bash
# Allow SSH and MUD port
ufw allow 22/tcp
ufw allow 4000/tcp
ufw enable
```

### 6. Connect

```bash
# From your local machine
telnet <droplet-ip> 4000
```

### Maintenance Commands

```bash
# View logs
journalctl -u waystone -f

# Restart server
systemctl restart waystone

# Update code
su - waystone
cd waystone
git pull
exit
systemctl restart waystone
```

### Optional: Domain Setup

If you have a domain, add an A record pointing to your droplet IP:
```
mud.yourdomain.com -> <droplet-ip>
```

Then connect with:
```bash
telnet mud.yourdomain.com 4000
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WAYSTONE_HOST` | `0.0.0.0` | Server bind address |
| `WAYSTONE_PORT` | `4000` | Server port |
| `WAYSTONE_DB_URL` | `sqlite:///data/waystone.db` | Database connection string |
| `WAYSTONE_LOG_LEVEL` | `INFO` | Logging level |

## License

MIT

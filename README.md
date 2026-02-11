# 🤖 AIDEV-OPS-Server

**Remote Autonomous AI Development System** — A self-hosted daemon that processes GitHub issues, generates code fixes using AI, reviews them for safety, and pushes validated commits automatically.

---

## ⚡ Quick Start

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/your-user/AIDEV-OPS.git
cd AIDEV-OPS
pip install -r requirements.txt
```

### 2. Configure API Keys

Copy the example and add your real keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
NVIDIA_API_KEY_1=nvapi-your-first-key
NVIDIA_API_KEY_2=nvapi-your-second-key
GITHUB_PAT=ghp_your-github-personal-access-token
```

### 3. Verify Setup

```bash
python main.py status
```

You should see:

```
═══════════════════════════════════════
  AIDEV-OPS System Status
═══════════════════════════════════════
  AI Keys:  2 configured
  AI Roles: planner, architect, coder, reviewer
═══════════════════════════════════════
```

### 4. Test AI Connection

```bash
python main.py ai test
python main.py ai health
```

---

## 📦 Managing Projects

### Add a Project

```bash
python main.py project add myapp --repo https://github.com/user/myapp --branch main
```

This will:

- Create a project directory under `/opt/aidev/projects/myapp/`
- Clone the repository
- Register it for issue polling

### List Projects

```bash
python main.py project list
```

### Remove a Project

```bash
python main.py project remove myapp
```

---

## 🚀 Running the System

### Foreground (Development)

```bash
python main.py start -f
```

Press `Ctrl+C` to stop.

### Background (Production on Linux)

```bash
python main.py start
```

### Stop the Daemon

```bash
python main.py stop
```

---

## 🐧 Server Deployment (AlmaLinux / RHEL)

### One-Command Install

```bash
sudo bash scripts/install.sh
```

This installs all system deps, Docker, creates the `aidev` user, Python venv, and systemd service.

### Manage with systemd

```bash
sudo systemctl start aidev      # Start
sudo systemctl stop aidev       # Stop
sudo systemctl status aidev     # Check status
sudo journalctl -u aidev -f     # Follow logs
```

### Use the CLI Anywhere

After installation, the `aidev` command is available globally:

```bash
aidev status
aidev project add myapp --repo https://github.com/user/myapp
aidev start
```

## 🔄 Full Reset (Fresh Install on Server)

If things get messy, nuke everything and start fresh:

```bash
# Download and run the reset script
curl -O https://raw.githubusercontent.com/aiko-codex/AIDEV-OPS/main/scripts/reset.sh
sudo bash reset.sh
```

This will:

1. Stop the aidev service
2. Delete `/opt/aidev` completely
3. Fresh `git clone` from GitHub
4. Setup Python venv + install deps
5. Create `.env` from example
6. Setup aidev user + systemd service
7. Create the `aidev` CLI command

After reset:

```bash
nano /opt/aidev/.env                  # Add your API keys
aidev status                          # Verify setup
aidev ai test                         # Test AI connection
aidev project add todox --repo https://github.com/aiko-codex/todox.git
aidev start -f                        # Start in foreground
```

### Updating Code (after git push from local)

```bash
cd /opt/aidev
git pull
aidev status    # New code is used immediately
```

Since the install now runs directly from the git clone (not a copy), `git pull` is all you need.

### Next when you make some changes

```bash
# Pull latest code
cd /opt/aidev && git pull

# Tell AIDEV-OPS to read the PRD and start building
aidev kickstart todox
```

---

## 🔄 How It Works

```
1. AIDEV-OPS polls your GitHub repos for open issues labeled "aidev"
2. Planner AI (Kimi K2.5) analyzes the issue and creates a fix plan
3. Coder AI (Qwen3-Coder-480B) generates the code changes
4. Reviewer checks for safety (no destructive SQL, no hardcoded secrets)
5. Changes are applied as patches with automatic backup
6. Git Agent commits and pushes the fix
7. Issue is closed with a resolution comment
```

### AI Roles

| Role | Model | What It Does |
|------|-------|-------------|
| **Planner** | Kimi K2.5 | Breaks down issues into actionable plans |
| **Architect** | Kimi K2.5 | Designs system-level solutions |
| **Coder** | Qwen3-Coder-480B | Generates code patches |
| **Reviewer** | Qwen3-80B | Validates safety and quality |

### Labeling Issues for Auto-Processing

Add the `aidev` label to any GitHub issue you want the system to pick up automatically. It will be processed on the next poll cycle (every 5 minutes).

---

## 📋 CLI Reference

| Command | Description |
|---------|-------------|
| `python main.py status` | Show system status |
| `python main.py start -f` | Start in foreground |
| `python main.py start` | Start as daemon |
| `python main.py stop` | Stop the daemon |
| `python main.py logs` | View system logs |
| `python main.py logs -m core` | View logs for a specific module |
| `python main.py project add NAME --repo URL` | Add a project |
| `python main.py project list` | List all projects |
| `python main.py project remove NAME` | Remove a project |
| `python main.py ai test` | Test AI gateway |
| `python main.py ai test -r coder -p "Write hello world"` | Test a specific role |
| `python main.py ai health` | Health check all providers |
| `python main.py ai stats` | Show API usage stats |

---

## ⚙️ Configuration

Edit `config.yaml` to customize:

- **AI models & roles** — Change which model handles each role
- **Docker limits** — Memory (`512m`), CPU, max containers (`2`)
- **GitHub polling** — Poll interval (default: `300` seconds)
- **Logging** — Level, rotation size, backup count

---

## 🛡️ Safety Checks

The Reviewer automatically blocks:

- ❌ `DROP TABLE` / `TRUNCATE TABLE` — Destructive SQL
- ❌ Hardcoded API keys, passwords, tokens
- ❌ `rm -rf /` — Dangerous shell commands
- ❌ `curl | bash` — Remote code execution
- ⚠️ PHP 7.0+ syntax (when targeting PHP 5.6)

---

## 📁 Project Structure

```
AIDEV-OPS/
├── main.py                  # Entry point
├── config.yaml              # Configuration
├── .env                     # API keys (not in git)
├── src/
│   ├── config.py            # Config loader
│   ├── logger.py            # Logging system
│   ├── core.py              # Main orchestrator
│   ├── cli.py               # CLI commands
│   ├── ai/                  # AI Gateway + Roles
│   ├── project/             # Project lifecycle
│   ├── docker_engine/       # Container management
│   ├── git/                 # Git operations
│   ├── issues/              # GitHub issue polling
│   └── workflow/            # Pipeline + Review + Patching
├── scripts/
│   ├── install.sh           # AlmaLinux installer
│   └── aidev.service        # systemd unit
└── tests/                   # 28 unit tests
```

---

## 📄 License

MIT

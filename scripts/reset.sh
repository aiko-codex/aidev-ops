#!/bin/bash
# ============================================================
# AIDEV-OPS Full Reset & Fresh Install
# Run this on your AlmaLinux server as root
# ============================================================

set -e

INSTALL_DIR="/opt/aidev"
REPO_URL="https://github.com/aiko-codex/AIDEV-OPS.git"
BRANCH="main"

echo "═══════════════════════════════════════"
echo "  AIDEV-OPS Full Reset"
echo "═══════════════════════════════════════"

# Stop service if running
echo ""
echo "Step 1: Stopping service..."
systemctl stop aidev 2>/dev/null || true

# Nuke everything
echo ""
echo "Step 2: Removing old installation..."
rm -rf ${INSTALL_DIR}

# Fresh clone
echo ""
echo "Step 3: Cloning fresh from GitHub..."
git clone -b ${BRANCH} ${REPO_URL} ${INSTALL_DIR}

# Setup Python venv
echo ""
echo "Step 4: Setting up Python environment..."
cd ${INSTALL_DIR}
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# Create directories
echo ""
echo "Step 5: Creating data directories..."
mkdir -p ${INSTALL_DIR}/{projects,logs,data}

# Setup .env from example
echo ""
echo "Step 6: Setting up .env..."
if [ ! -f ${INSTALL_DIR}/.env ]; then
    cp ${INSTALL_DIR}/.env.example ${INSTALL_DIR}/.env
    echo "  ⚠ Created .env from example — EDIT IT with your real keys!"
    echo "  → nano ${INSTALL_DIR}/.env"
else
    echo "  .env already exists"
fi
chmod 600 ${INSTALL_DIR}/.env

# Setup user
echo ""
echo "Step 7: Setting up aidev user..."
id -u aidev &>/dev/null || useradd -r -s /sbin/nologin -d ${INSTALL_DIR} aidev
chown -R aidev:aidev ${INSTALL_DIR}
usermod -aG docker aidev 2>/dev/null || true

# Install systemd service
echo ""
echo "Step 8: Installing systemd service..."
cp ${INSTALL_DIR}/scripts/aidev.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aidev

# Create CLI shortcut
echo ""
echo "Step 9: Creating aidev command..."
cat > /usr/local/bin/aidev << 'EOF'
#!/bin/bash
cd /opt/aidev
source venv/bin/activate
python main.py "$@"
EOF
chmod +x /usr/local/bin/aidev

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Fresh Install Complete!"
echo "═══════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  1. nano /opt/aidev/.env        ← Add your API keys"
echo "  2. aidev status                 ← Verify setup"
echo "  3. aidev ai test                ← Test AI connection"
echo "  4. aidev project add todox --repo https://github.com/aiko-codex/todox.git"
echo "  5. aidev start -f               ← Start in foreground"
echo ""

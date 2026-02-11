#!/bin/bash
# ============================================================
# AIDEV-OPS Installation Script for AlmaLinux 9.x
# ============================================================

set -e

INSTALL_DIR="/opt/aidev"
SERVICE_NAME="aidev"
PYTHON_MIN="3.9"

echo "═══════════════════════════════════════"
echo "  AIDEV-OPS Installer (AlmaLinux 9.x)"
echo "═══════════════════════════════════════"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo)"
    exit 1
fi

# Check OS
if ! grep -q "AlmaLinux" /etc/os-release 2>/dev/null; then
    echo "⚠  Warning: This script is designed for AlmaLinux 9.x"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

echo ""
echo "Step 1: Installing system dependencies..."
dnf install -y \
    python3 \
    python3-pip \
    python3-devel \
    git \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    2>/dev/null || {
    # If Docker repo not available, add it
    dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf install -y python3 python3-pip python3-devel git docker-ce docker-ce-cli containerd.io
}

echo ""
echo "Step 2: Setting up Docker..."
systemctl enable docker
systemctl start docker

echo ""
echo "Step 3: Creating directory structure..."
mkdir -p ${INSTALL_DIR}/{projects,logs,data}
mkdir -p ${INSTALL_DIR}/logs

echo ""
echo "Step 4: Copying application files..."
# Copy source files to install directory
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp -r "${SCRIPT_DIR}/src" ${INSTALL_DIR}/
cp -r "${SCRIPT_DIR}/main.py" ${INSTALL_DIR}/
cp -r "${SCRIPT_DIR}/config.yaml" ${INSTALL_DIR}/
cp -r "${SCRIPT_DIR}/requirements.txt" ${INSTALL_DIR}/

# Copy .env if it exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
    cp "${SCRIPT_DIR}/.env" ${INSTALL_DIR}/
    chmod 600 ${INSTALL_DIR}/.env
fi

echo ""
echo "Step 5: Setting up Python virtual environment..."
cd ${INSTALL_DIR}
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Step 6: Creating aidev user..."
id -u aidev &>/dev/null || useradd -r -s /sbin/nologin -d ${INSTALL_DIR} aidev
chown -R aidev:aidev ${INSTALL_DIR}
# Add aidev user to docker group
usermod -aG docker aidev

echo ""
echo "Step 7: Installing systemd service..."
cp "${SCRIPT_DIR}/scripts/aidev.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}

echo ""
echo "Step 8: Creating CLI symlink..."
cat > /usr/local/bin/aidev << 'EOF'
#!/bin/bash
cd /opt/aidev
source venv/bin/activate
python main.py "$@"
EOF
chmod +x /usr/local/bin/aidev

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ AIDEV-OPS Installed!"
echo "═══════════════════════════════════════"
echo ""
echo "  Install dir: ${INSTALL_DIR}"
echo "  Config:      ${INSTALL_DIR}/config.yaml"
echo "  Secrets:     ${INSTALL_DIR}/.env"
echo "  Logs:        ${INSTALL_DIR}/logs/"
echo ""
echo "  Next steps:"
echo "  1. Edit ${INSTALL_DIR}/.env with your API keys"
echo "  2. Edit ${INSTALL_DIR}/config.yaml as needed"
echo "  3. Start:  aidev start"
echo "  4. Status: aidev status"
echo ""

#!/usr/bin/env python3
"""
AIDEV-OPS-Server — Remote Autonomous AI Development System

Entry point for the system. Usage:
    python main.py start [-f]     Start the daemon
    python main.py stop           Stop the daemon
    python main.py status         Show system status
    python main.py logs           View logs
    python main.py project add    Add a project
    python main.py project list   List projects
    python main.py ai test        Test AI gateway
    python main.py ai health      Check AI health
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import main

if __name__ == '__main__':
    main()

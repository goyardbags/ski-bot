#!/usr/bin/env python3
"""
Ski Bot Launcher
Run this script to start the crypto bot
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the bot
from main_storage import main

if __name__ == "__main__":
    main() 
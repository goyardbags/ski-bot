#!/usr/bin/env python3
"""
Ski Bot Launcher
Run this script to start the crypto bot
"""

import sys
import os
import threading

# Minimal Flask web server for Render
try:
    from flask import Flask
    def start_web():
        app = Flask(__name__)

        @app.route('/')
        def home():
            return "bot is running!"

        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    threading.Thread(target=start_web, daemon=True).start()
except ImportError:
    pass  # Flask not installed, skip web server

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from main_storage import main
    if __name__ == "__main__":
        main()
except Exception as e:
    print("Startup error:", e) 
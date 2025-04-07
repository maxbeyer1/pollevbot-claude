#!/usr/bin/env python
"""
PollEvBot Web GUI

This script launches a web interface for configuring and controlling PollEvBot.
It provides a user-friendly way to manage environment variables, bot settings,
and view response history.

Usage:
    python webgui.py [--host HOST] [--port PORT] [--debug]

Options:
    --host HOST    Host interface to listen on [default: 0.0.0.0]
    --port PORT    Port to listen on [default: 5000]
    --debug        Enable debug mode [default: False]
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from pollevbot.web_gui import WebGUI


def main():
    # Load environment variables from .env file if present
    load_dotenv()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='PollEvBot Web Interface')
    parser.add_argument('--host', default='0.0.0.0', help='Host interface to listen on')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    # Create and run the web GUI
    gui = WebGUI(host=args.host, port=args.port, debug=args.debug)
    print(f"PollEvBot Web Interface running at http://{args.host}:{args.port}")
    gui.run()


if __name__ == '__main__':
    main()
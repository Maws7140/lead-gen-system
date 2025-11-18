#!/usr/bin/env python3
"""
LeadGen Pro - Startup Script
Run this script to start the web application
"""

import os
import sys
import subprocess


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║     ██╗     ███████╗ █████╗ ██████╗  ██████╗ ███████╗███╗   ██╗║
    ║     ██║     ██╔════╝██╔══██╗██╔══██╗██╔════╝ ██╔════╝████╗  ██║║
    ║     ██║     █████╗  ███████║██║  ██║██║  ███╗█████╗  ██╔██╗ ██║║
    ║     ██║     ██╔══╝  ██╔══██║██║  ██║██║   ██║██╔══╝  ██║╚██╗██║║
    ║     ███████╗███████╗██║  ██║██████╔╝╚██████╔╝███████╗██║ ╚████║║
    ║     ╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝║
    ║                                                               ║
    ║                    PRO v2.0 - AI-Powered                      ║
    ║              Lead Generation & Web Scraping System            ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    # Check for .env file
    if not os.path.exists('.env'):
        print("Warning: .env file not found!")
        print("Please create a .env file with your API keys.")
        print("See env_template.txt for required variables.\n")

    # Check for required packages
    try:
        import fastapi
        import uvicorn
        import openai
    except ImportError as e:
        print(f"Missing required package: {e}")
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Dependencies installed. Restarting...\n")

    # Start the application
    print("Starting LeadGen Pro...")
    print("Dashboard: http://localhost:8000")
    print("API Docs:  http://localhost:8000/api/docs")
    print("\nPress Ctrl+C to stop the server.\n")

    try:
        import uvicorn
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\nShutting down LeadGen Pro...")
        sys.exit(0)


if __name__ == "__main__":
    main()

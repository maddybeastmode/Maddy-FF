#!/bin/bash
# Free Fire Like Bot Pro — Termux Setup Script
# Run this in Termux after installing it from F-Droid

echo "🔥 Free Fire Like Bot Pro — Termux Setup"
echo "========================================="

# Update packages
echo "[1/5] Updating packages..."
pkg update -y && pkg upgrade -y

# Install Python and dependencies
echo "[2/5] Installing Python..."
pkg install -y python python-pip git

# Install required Python packages
echo "[3/5] Installing Python dependencies..."
pip install httpx[http2] pycryptodome protobuf aiosqlite pyyaml pydantic rich typer anyio

echo "[4/5] Setup complete!"
echo ""
echo "========================================="
echo "✅ Setup done! Now:"
echo "  1. Clone this repo: git clone https://github.com/ISMAILdz13/FreeFireLikesBot.git"
echo "  2. cd FreeFireLikesBot"
echo "  3. Edit data/guests.json with your guest accounts"
echo "  4. python3 run_likes.py --target UID --count 15 --region ME"
echo "========================================="

#!/bin/bash
# Setup script for TeraBox Downloader Bot
# Run this on your VPS: bash setup.sh

echo "=== TeraBox Bot Setup ==="

# Install system dependencies
echo "Installing system dependencies..."
apt update -qq
apt install -y ffmpeg fonts-dejavu-core python3-pip python3-venv -qq

# Create virtual environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "Installing Python packages..."
pip install -r requirements.txt -q

# Create downloads directory
mkdir -p downloads

echo "=== Setup Complete ==="
echo "Run the bot with: nohup python -u main.py > bot.log 2>&1 &"

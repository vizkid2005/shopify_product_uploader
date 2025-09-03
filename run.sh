#!/bin/bash

# Shopify Product Uploader - Run Script

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run ./setup.sh first"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please create it from .env.example"
    exit 1
fi

# Run the main script with all arguments passed to this script
python main.py "$@"

# Deactivate virtual environment
deactivate
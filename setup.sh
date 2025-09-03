#!/bin/bash

# Shopify Product Uploader - Virtual Environment Setup Script

echo "================================================"
echo "Shopify Product Uploader - Setup Script"
echo "================================================"

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then 
    echo "❌ Error: Python 3.11 or higher is required (found $python_version)"
    exit 1
fi
echo "✅ Python $python_version found"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists. Removing old one..."
    rm -rf venv
fi

python3 -m venv venv
echo "✅ Virtual environment created"

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✅ pip upgraded"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt
if [ $? -eq 0 ]; then
    echo "✅ All dependencies installed successfully"
else
    echo "❌ Error installing dependencies"
    exit 1
fi

# Create .env file if it doesn't exist
echo ""
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created"
    echo "⚠️  Please edit .env file with your API credentials"
else
    echo "✅ .env file already exists"
fi

# Create necessary directories
echo ""
echo "Creating required directories..."
mkdir -p data/images logs
echo "✅ Directories created"

# Make main.py executable
chmod +x main.py
echo "✅ Made main.py executable"

echo ""
echo "================================================"
echo "✅ Setup completed successfully!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API credentials"
echo "2. Activate the virtual environment: source venv/bin/activate"
echo "3. Test the setup: python main.py --help"
echo "4. Run dry test: python main.py --dry-run --limit 1"
echo ""
echo "To deactivate the virtual environment later: deactivate"
echo "================================================"
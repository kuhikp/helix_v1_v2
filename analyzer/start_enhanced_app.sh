#!/bin/bash

# Helix V1 to V2 Analyzer v3.0 Startup Script
echo "🚀 Starting Helix V1 to V2 Analyzer v3.0..."
echo "🗺️  Focus: Sitemap-Powered Site-Wide Analysis"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run the setup first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if required packages are installed
echo "📦 Checking required packages..."
python -c "import flask, pandas, openpyxl, requests, bs4" 2>/dev/null || {
    echo "❌ Required packages not found. Installing..."
    pip install -r requirements.txt
}

# Create necessary directories
mkdir -p downloads
mkdir -p static
mkdir -p templates

echo "✅ Setup complete!"
echo "🌐 Starting Enhanced Flask application on http://localhost:5002"
echo "📝 Press Ctrl+C to stop the server"
echo ""
echo "🆕 New Features in v3.0:"
echo "   🗺️  Automatic Sitemap Discovery"
echo "   🌐 Whole-Site Processing"
echo "   📊 Real-Time Progress Tracking"
echo "   🔄 Auto-Reconnection & Error Recovery"
echo "   � Live Statistics & Time Estimates"
echo "   � Step-by-Step Processing Log"
echo "   🎯 Max Pages Limit for Large Sites"
echo "   📁 Enhanced CSV Export with Site Coverage"
echo ""

# Run the Enhanced Flask app
python enhanced_web_scraper.py

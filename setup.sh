#!/usr/bin/env bash
set -e

echo "=========================================="
echo "🚀 WATCHER TEST SUITE SETUP"
echo "=========================================="

# 1. Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment (venv)..."
    python3 -m venv venv
else
    echo "📦 Virtual environment already exists."
fi

# 2. Activate virtual environment
source venv/bin/activate

# 3. Upgrade pip & Install requirements
echo "📥 Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright browser binaries (for viewer QA tests)
if command -v playwright &> /dev/null; then
    echo "🎭 Installing/updating Playwright browsers..."
    playwright install chromium
fi

# 5. Handle .env setup for API keys
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file detected. Creating default .env file..."
    cat <<EOT > .env
# PageSpeed Insights API Key
PAGESPEED_API_KEY=
EOT
    echo "📄 Created .env file. Add your Google PageSpeed API key to .env if needed."
else
    echo "🔑 Found existing .env file."
fi

# 6. Ensure required output directories exist
mkdir -p output tmp

echo ""
echo "=========================================="
echo "✅ Setup finished successfully!"
echo "=========================================="
echo "To run performance tests manually:"
echo "  source venv/bin/activate"
echo "  python run.py"
echo "=========================================="
echo ""
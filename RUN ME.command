#!/bin/bash
cd "$(dirname "$0")"
echo "============================================"
echo "  MAKEMYDRUMKIT"
echo "  by LOSTINLIMERENCE"
echo "============================================"
echo ""

PYTHON=python3
if ! command -v $PYTHON &> /dev/null; then
    echo "Python isn't installed on this computer yet."
    echo ""
    echo "  1. Go to https://www.python.org/downloads/"
    echo "  2. Download and run the installer"
    echo "  3. Once it finishes, run this file again"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

echo "Checking requirements — first run only, takes a minute or two..."
$PYTHON -m pip install --quiet --disable-pip-version-check -r requirements.txt
if [ $? -ne 0 ]; then
    echo ""
    echo "Something went wrong installing requirements. Scroll up to see the"
    echo "error, or ask whoever gave you this for help."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

$PYTHON run_server.py

echo ""
echo "App stopped. You can close this window."
read -p "Press Enter to close..."

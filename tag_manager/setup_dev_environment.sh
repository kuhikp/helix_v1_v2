#!/bin/bash

# Helix Tag Manager - Developer Setup Script
# This script sets up sample data for first-time developers

set -e

echo "========================================="
echo "Helix Tag Manager - Developer Setup"
echo "========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    print_error "manage.py not found. Please run this script from the tag_manager directory."
    exit 1
fi

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_warning "Virtual environment not detected. It's recommended to activate your virtual environment first."
    echo "Run: source venv/bin/activate"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_error ".env file not found. Please create one based on the README instructions."
    exit 1
fi

echo
echo "Step 1: Installing dependencies..."
pip install -r requirements.txt
print_status "Dependencies installed"

echo
echo "Step 2: Running database migrations..."
python manage.py migrate
print_status "Database migrations completed"

echo
echo "Step 3: Importing sample data..."
python manage.py import_sample_data
print_status "Sample data imported successfully"

echo
echo "========================================="
echo "Setup completed successfully!"
echo "========================================="
echo
echo "You can now:"
echo "1. Start the development server: python manage.py runserver"
echo "2. Access the application at: http://127.0.0.1:8000/"
echo "3. Access the admin interface at: http://127.0.0.1:8000/admin/"
echo
echo "Login credentials:"
echo "  Admin User: admin / Password copy from the terminal"
echo "  Tag Manager: tagmanager / Password copy from the terminal"
echo
echo "Happy coding! 🚀"

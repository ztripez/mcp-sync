#!/bin/bash
# Development setup script for mcp-sync
# Automatically sets up development environment with git hooks

set -e

echo "🚀 Setting up mcp-sync development environment..."

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
uv sync

# Install pre-commit hooks
echo "🎯 Installing pre-commit hooks..."
uv run pre-commit install

echo ""
echo "🎉 Development setup complete!"
echo ""
echo "Pre-commit hooks are now active and will run automatically on:"
echo "  • git commit (linting, formatting, etc.)"
echo ""
echo "To run hooks manually:"
echo "  uv run pre-commit run --all-files"
echo ""
echo "To test your setup:"
echo "  uv run ruff check ."
echo "  uv run ruff format ."
echo ""
echo "Happy coding! 🚀"

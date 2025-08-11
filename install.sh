#!/bin/bash

# Paw Control Installation Script for Home Assistant
# This script helps install Paw Control integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default paths
DEFAULT_HA_CONFIG="/config"
CUSTOM_COMPONENTS_DIR="custom_components"
INTEGRATION_NAME="pawcontrol"

echo -e "${GREEN}🐾 Paw Control Installation Script${NC}"
echo "======================================"
echo ""

# Check if running in Home Assistant
if [ -d "/config" ]; then
    HA_CONFIG_PATH="/config"
elif [ -d "$HOME/.homeassistant" ]; then
    HA_CONFIG_PATH="$HOME/.homeassistant"
elif [ -d "$HOME/homeassistant" ]; then
    HA_CONFIG_PATH="$HOME/homeassistant"
else
    echo -e "${YELLOW}Home Assistant configuration directory not found.${NC}"
    read -p "Enter your Home Assistant configuration path: " HA_CONFIG_PATH
fi

# Validate path
if [ ! -d "$HA_CONFIG_PATH" ]; then
    echo -e "${RED}Error: Directory $HA_CONFIG_PATH does not exist!${NC}"
    exit 1
fi

echo -e "${GREEN}Using Home Assistant config path: $HA_CONFIG_PATH${NC}"

# Create custom_components directory if it doesn't exist
CUSTOM_COMP_PATH="$HA_CONFIG_PATH/$CUSTOM_COMPONENTS_DIR"
if [ ! -d "$CUSTOM_COMP_PATH" ]; then
    echo "Creating custom_components directory..."
    mkdir -p "$CUSTOM_COMP_PATH"
fi

# Check if integration already exists
if [ -d "$CUSTOM_COMP_PATH/$INTEGRATION_NAME" ]; then
    echo -e "${YELLOW}Warning: Paw Control is already installed!${NC}"
    read -p "Do you want to update/reinstall? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    echo "Removing existing installation..."
    rm -rf "$CUSTOM_COMP_PATH/$INTEGRATION_NAME"
fi

# Copy integration files
echo "Installing Paw Control integration..."
cp -r "custom_components/$INTEGRATION_NAME" "$CUSTOM_COMP_PATH/"

# Check if installation was successful
if [ -d "$CUSTOM_COMP_PATH/$INTEGRATION_NAME" ]; then
    echo -e "${GREEN}✅ Paw Control installed successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Restart Home Assistant"
    echo "2. Go to Settings → Devices & Services"
    echo "3. Click '+ Add Integration'"
    echo "4. Search for 'Paw Control'"
    echo "5. Follow the setup wizard"
    echo ""
    echo -e "${YELLOW}Note: If using HACS, you can also install via HACS instead of this script.${NC}"
else
    echo -e "${RED}❌ Installation failed!${NC}"
    exit 1
fi

# Optional: Install blueprints
read -p "Do you want to install the blueprint examples? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    BLUEPRINTS_PATH="$HA_CONFIG_PATH/blueprints/automation"
    mkdir -p "$BLUEPRINTS_PATH"
    
    if [ -d "blueprints/automation" ]; then
        cp blueprints/automation/*.yaml "$BLUEPRINTS_PATH/" 2>/dev/null || true
        echo -e "${GREEN}✅ Blueprints installed!${NC}"
    else
        echo -e "${YELLOW}No blueprints found to install.${NC}"
    fi
fi

echo ""
echo -e "${GREEN}🐾 Installation complete! Enjoy Paw Control!${NC}"

"""Test environment configuration for PawControl."""

import os

# Prevent external pytest plugins from auto-loading during test collection.
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

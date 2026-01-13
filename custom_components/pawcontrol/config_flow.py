"""Config flow entrypoint for the PawControl integration.

This file is intentionally kept small. The full implementation lives in
:mod:`custom_components.pawcontrol.config_flow_main` and composes themed mixins
(e.g. dogs/modules/profile/dashboard/reauth) to keep responsibilities separated.
"""

from __future__ import annotations

from .config_flow_main import ConfigFlow, PawControlConfigFlow

__all__ = ["ConfigFlow", "PawControlConfigFlow"]

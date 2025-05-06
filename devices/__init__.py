"""
Device-specific firmware upgrade modules.
Each device module should implement an upgrade_device() function with the following signature:
    upgrade_device(device_ip: str, computer_ip: str, firmware_path: str, credentials: dict) -> None
"""

from .base import DeviceType, BaseDeviceUpgrader

__all__ = ['DeviceType', 'BaseDeviceUpgrader'] 
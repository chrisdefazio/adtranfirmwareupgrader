"""
Base interface for device firmware upgraders.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any

class DeviceUpgrader(ABC):
    """Base class for device firmware upgraders."""
    
    def __init__(self, device_ip: str, username: str, password: str):
        """Initialize the device upgrader.
        
        Args:
            device_ip: IP address of the device
            username: SSH username
            password: SSH password
        """
        self.device_ip = device_ip
        self.username = username
        self.password = password
        self.ssh_client = None
        self.channel = None
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the device.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the device."""
        pass
    
    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """Get device information.
        
        Returns:
            Dict containing device information (model, serial, etc.)
        """
        pass
    
    @abstractmethod
    def check_firmware_version(self) -> str:
        """Check current firmware version.
        
        Returns:
            str: Current firmware version
        """
        pass
    
    @abstractmethod
    def upgrade_firmware(self, firmware_path: str) -> bool:
        """Upgrade device firmware.
        
        Args:
            firmware_path: Path to firmware file
            
        Returns:
            bool: True if upgrade successful, False otherwise
        """
        pass
    
    @abstractmethod
    def verify_upgrade(self) -> bool:
        """Verify the firmware upgrade was successful.
        
        Returns:
            bool: True if upgrade verified, False otherwise
        """
        pass
    
    @abstractmethod
    def backup_config(self) -> Optional[str]:
        """Backup device configuration.
        
        Returns:
            Optional[str]: Path to backup file if successful, None otherwise
        """
        pass
    
    @abstractmethod
    def restore_config(self, backup_path: str) -> bool:
        """Restore device configuration from backup.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            bool: True if restore successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_upgrade_progress(self) -> Tuple[bool, bool, str]:
        """Get current upgrade progress.
        
        Returns:
            Tuple containing:
                - bool: Whether download has started
                - bool: Whether upgrade is complete
                - str: Progress output
        """
        pass 
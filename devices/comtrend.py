"""
Comtrend device firmware upgrader implementation.
"""

import os
import time
from typing import Dict, Any, Optional, Tuple
from .base import DeviceUpgrader
from ..utils import (
    wait_for_ping,
    ssh_connect_with_shell,
    execute_ssh_command,
    monitor_upgrade_progress,
    extract_device_info
)

class ComtrendUpgrader(DeviceUpgrader):
    """Comtrend device firmware upgrader."""
    
    def __init__(self, device_ip: str, username: str = "admin", password: str = "admin"):
        """Initialize Comtrend upgrader.
        
        Args:
            device_ip: IP address of the device
            username: SSH username (default: admin)
            password: SSH password (default: admin)
        """
        super().__init__(device_ip, username, password)
    
    def connect(self) -> bool:
        """Connect to the Comtrend device.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        # Wait for device to be reachable
        if not wait_for_ping(self.device_ip):
            return False
        
        # Connect via SSH
        self.ssh_client, self.channel = ssh_connect_with_shell(
            self.device_ip,
            self.username,
            self.password
        )
        
        return self.ssh_client is not None and self.channel is not None
    
    def disconnect(self) -> None:
        """Disconnect from the Comtrend device."""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
            self.channel = None
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get Comtrend device information.
        
        Returns:
            Dict containing device information
        """
        if not self.channel:
            return {}
        
        # Get device info
        info = {}
        
        # Get model info
        model_output = execute_ssh_command(self.channel, "cat /proc/cmdline")
        if model_output:
            for line in model_output.split('\n'):
                if "model" in line.lower():
                    info['model'] = line.split("model=")[1].split()[0]
        
        # Get serial and MAC
        mfg_output = execute_ssh_command(self.channel, "cat /proc/mfg")
        if mfg_output:
            for line in mfg_output.split('\n'):
                if "MFG_SERIAL" in line:
                    info['serial'] = line.split("=")[1].strip()
                if "MFG_MAC" in line:
                    info['mac'] = line.split("=")[1].strip()
        
        # Get WiFi info
        wifi_output = execute_ssh_command(self.channel, "cat /etc/config/wireless")
        if wifi_output:
            for line in wifi_output.split('\n'):
                if "option ssid" in line:
                    info['ssid'] = line.split("'")[1]
                if "option key" in line:
                    info['wifi_password'] = line.split("'")[1]
        
        return info
    
    def check_firmware_version(self) -> str:
        """Check current firmware version.
        
        Returns:
            str: Current firmware version
        """
        if not self.channel:
            return ""
        
        output = execute_ssh_command(self.channel, "cat /etc/version")
        if output:
            return output.strip()
        
        return ""
    
    def upgrade_firmware(self, firmware_path: str) -> bool:
        """Upgrade Comtrend device firmware.
        
        Args:
            firmware_path: Path to firmware file
            
        Returns:
            bool: True if upgrade successful, False otherwise
        """
        if not self.channel:
            return False
        
        if not os.path.exists(firmware_path):
            print(f"Firmware file not found: {firmware_path}")
            return False
        
        # Backup current configuration
        backup_path = self.backup_config()
        if not backup_path:
            print("Warning: Failed to backup configuration")
        
        # Start firmware upgrade
        print(f"\nStarting firmware upgrade with file: {firmware_path}")
        upgrade_cmd = f"sysupgrade {firmware_path}"
        execute_ssh_command(self.channel, upgrade_cmd)
        
        # Monitor upgrade progress
        download_started, upgrade_complete, _ = self.get_upgrade_progress()
        
        if not download_started:
            print("Firmware download did not start")
            return False
        
        if not upgrade_complete:
            print("Firmware upgrade did not complete successfully")
            return False
        
        # Wait for device to reboot
        print("\nWaiting for device to reboot...")
        time.sleep(30)
        
        # Wait for device to be reachable again
        if not wait_for_ping(self.device_ip):
            print("Device did not come back online after upgrade")
            return False
        
        # Reconnect to device
        if not self.connect():
            print("Failed to reconnect to device after upgrade")
            return False
        
        # Verify upgrade
        if not self.verify_upgrade():
            print("Upgrade verification failed")
            return False
        
        # Restore configuration if backup was created
        if backup_path:
            if not self.restore_config(backup_path):
                print("Warning: Failed to restore configuration")
        
        return True
    
    def verify_upgrade(self) -> bool:
        """Verify the firmware upgrade was successful.
        
        Returns:
            bool: True if upgrade verified, False otherwise
        """
        if not self.channel:
            return False
        
        # Check if device is responsive
        output = execute_ssh_command(self.channel, "cat /etc/version")
        if not output:
            return False
        
        # Check for any error messages
        if "error" in output.lower() or "fail" in output.lower():
            return False
        
        return True
    
    def backup_config(self) -> Optional[str]:
        """Backup Comtrend device configuration.
        
        Returns:
            Optional[str]: Path to backup file if successful, None otherwise
        """
        if not self.channel:
            return None
        
        # Create backup directory if it doesn't exist
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate backup filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"comtrend_config_{self.device_ip.replace('.', '_')}_{timestamp}.txt")
        
        # Get configuration
        config_output = execute_ssh_command(self.channel, "cat /etc/config/*")
        if not config_output:
            return None
        
        # Save configuration to file
        try:
            with open(backup_file, 'w') as f:
                f.write(config_output)
            print(f"\nConfiguration backed up to: {backup_file}")
            return backup_file
        except Exception as e:
            print(f"Error saving configuration backup: {e}")
            return None
    
    def restore_config(self, backup_path: str) -> bool:
        """Restore Comtrend device configuration from backup.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            bool: True if restore successful, False otherwise
        """
        if not self.channel:
            return False
        
        if not os.path.exists(backup_path):
            print(f"Backup file not found: {backup_path}")
            return False
        
        # Read backup file
        try:
            with open(backup_path, 'r') as f:
                config = f.read()
        except Exception as e:
            print(f"Error reading backup file: {e}")
            return False
        
        # Restore configuration
        print("\nRestoring configuration...")
        
        # Split config into sections and apply each section
        current_section = None
        section_content = []
        
        for line in config.split('\n'):
            if line.startswith('config '):
                # Apply previous section if exists
                if current_section and section_content:
                    section_cmd = f"uci set {current_section}='{''.join(section_content)}'"
                    execute_ssh_command(self.channel, section_cmd)
                
                # Start new section
                current_section = line.strip()
                section_content = []
            else:
                section_content.append(line)
        
        # Apply last section
        if current_section and section_content:
            section_cmd = f"uci set {current_section}='{''.join(section_content)}'"
            execute_ssh_command(self.channel, section_cmd)
        
        # Commit changes
        execute_ssh_command(self.channel, "uci commit")
        
        return True
    
    def get_upgrade_progress(self) -> Tuple[bool, bool, str]:
        """Get current upgrade progress.
        
        Returns:
            Tuple containing:
                - bool: Whether download has started
                - bool: Whether upgrade is complete
                - str: Progress output
        """
        if not self.channel:
            return False, False, ""
        
        return monitor_upgrade_progress(self.channel) 
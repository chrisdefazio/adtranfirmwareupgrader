#!/usr/bin/env python3
"""
Unified firmware upgrader for network devices.
Supports multiple device types and provides a guided upgrade experience.
"""

import os
import sys
import time
from typing import Dict, Any, Optional, Type
from devices.base import DeviceUpgrader
from devices.adtran import ADTRANUpgrader
from devices.comtrend import ComtrendUpgrader
from utils import get_network_interfaces

class FirmwareUpgrader:
    """Main firmware upgrader class."""
    
    # Map of device types to their upgrader classes
    DEVICE_TYPES = {
        "ADTRAN": ADTRANUpgrader,
        "Comtrend": ComtrendUpgrader
    }
    
    def __init__(self):
        """Initialize the firmware upgrader."""
        self.device_upgrader = None
    
    def select_device_type(self) -> Optional[Type[DeviceUpgrader]]:
        """Prompt user to select device type.
        
        Returns:
            Optional[Type[DeviceUpgrader]]: Selected device upgrader class
        """
        print("\n===== SELECT DEVICE TYPE =====")
        print("Available device types:")
        
        for i, device_type in enumerate(self.DEVICE_TYPES.keys(), 1):
            print(f"{i}. {device_type}")
        
        while True:
            try:
                choice = int(input("\nEnter device type number: "))
                if 1 <= choice <= len(self.DEVICE_TYPES):
                    device_type = list(self.DEVICE_TYPES.keys())[choice - 1]
                    return self.DEVICE_TYPES[device_type]
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a number.")
    
    def get_device_ip(self) -> str:
        """Prompt user for device IP address.
        
        Returns:
            str: Device IP address
        """
        print("\n===== DEVICE IP ADDRESS =====")
        print("Available network interfaces:")
        
        interfaces = get_network_interfaces()
        for i, (iface, ip) in enumerate(interfaces, 1):
            print(f"{i}. {iface}: {ip}")
        
        while True:
            try:
                choice = int(input("\nSelect your network interface number: "))
                if 1 <= choice <= len(interfaces):
                    computer_ip = interfaces[choice - 1][1]
                    break
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a number.")
        
        device_ip = input("\nEnter device IP address (default: 192.168.1.1): ").strip()
        return device_ip or "192.168.1.1"
    
    def get_credentials(self) -> Dict[str, str]:
        """Prompt user for device credentials.
        
        Returns:
            Dict containing username and password
        """
        print("\n===== DEVICE CREDENTIALS =====")
        username = input("Enter username (default: admin): ").strip() or "admin"
        password = input("Enter password (default: admin): ").strip() or "admin"
        
        return {
            "username": username,
            "password": password
        }
    
    def get_firmware_path(self) -> Optional[str]:
        """Prompt user for firmware file path.
        
        Returns:
            Optional[str]: Path to firmware file
        """
        print("\n===== FIRMWARE FILE =====")
        
        while True:
            firmware_path = input("Enter path to firmware file: ").strip()
            
            if not firmware_path:
                print("Please enter a firmware file path.")
                continue
            
            if not os.path.exists(firmware_path):
                print(f"File not found: {firmware_path}")
                continue
            
            if not os.path.isfile(firmware_path):
                print(f"Not a file: {firmware_path}")
                continue
            
            return firmware_path
    
    def run(self) -> None:
        """Run the firmware upgrade process."""
        print("\n===== FIRMWARE UPGRADER =====")
        print("This tool will guide you through upgrading your device's firmware.")
        
        # Select device type
        device_class = self.select_device_type()
        if not device_class:
            print("No device type selected. Exiting.")
            return
        
        # Get device IP
        device_ip = self.get_device_ip()
        
        # Get credentials
        credentials = self.get_credentials()
        
        # Create device upgrader instance
        self.device_upgrader = device_class(
            device_ip,
            credentials["username"],
            credentials["password"]
        )
        
        # Connect to device
        print("\nConnecting to device...")
        if not self.device_upgrader.connect():
            print("Failed to connect to device. Please check the connection and try again.")
            return
        
        try:
            # Get device info
            print("\nGetting device information...")
            device_info = self.device_upgrader.get_device_info()
            if device_info:
                print("\nDevice Information:")
                for key, value in device_info.items():
                    print(f"{key}: {value}")
            
            # Check current firmware version
            current_version = self.device_upgrader.check_firmware_version()
            if current_version:
                print(f"\nCurrent firmware version: {current_version}")
            
            # Get firmware file
            firmware_path = self.get_firmware_path()
            if not firmware_path:
                print("No firmware file selected. Exiting.")
                return
            
            # Confirm upgrade
            print("\n===== CONFIRM UPGRADE =====")
            print("WARNING: This will upgrade the device's firmware.")
            print("Make sure you have selected the correct firmware file.")
            print("The device will reboot during the upgrade process.")
            
            confirm = input("\nDo you want to proceed with the upgrade? (y/N): ").strip().lower()
            if confirm != "y":
                print("Upgrade cancelled.")
                return
            
            # Perform upgrade
            print("\nStarting firmware upgrade...")
            if self.device_upgrader.upgrade_firmware(firmware_path):
                print("\n===== UPGRADE COMPLETE =====")
                print("The device has been successfully upgraded.")
                
                # Get new firmware version
                new_version = self.device_upgrader.check_firmware_version()
                if new_version:
                    print(f"New firmware version: {new_version}")
            else:
                print("\n===== UPGRADE FAILED =====")
                print("The firmware upgrade was not successful.")
                print("Please check the device and try again.")
        
        finally:
            # Disconnect from device
            if self.device_upgrader:
                self.device_upgrader.disconnect()

def main():
    """Main entry point."""
    try:
        upgrader = FirmwareUpgrader()
        upgrader.run()
    except KeyboardInterrupt:
        print("\nUpgrade cancelled by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
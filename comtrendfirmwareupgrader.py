#!/usr/bin/env python3
import os
import sys
import tftpy
import logging
import time
import threading
import paramiko
import platform
import subprocess
from dotenv import load_dotenv
from simple_term_menu import TerminalMenu

from network_utils import (
    drain_tty_input,
    get_gateway_for_connection,
    get_network_interfaces,
    get_wired_interface_ip,
    wait_for_ethernet_connection,
    wait_for_ping,
)

# Load environment variables from .env file
load_dotenv()

def setup_tftp_server(directory, ip='0.0.0.0', port=69, verbose=False):
    """
    Set up and run a TFTP server.
    
    Args:
        directory: Directory containing files to serve
        ip: IP address to bind to (default: 0.0.0.0 - all interfaces)
        port: Port to listen on (default: 69, the standard TFTP port)
        verbose: Enable verbose logging
    """
    # Set up logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Ensure the directory exists and is absolute
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory")
        sys.exit(1)
    
    # Display server info
    print(f"Starting TFTP server:")
    print(f"  - Serving files from: {directory}")
    print(f"  - Listening on: {ip}:{port}")
    print(f"  - Available files:")
    
    # List available files in the directory
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if files:
        for file in files:
            file_path = os.path.join(directory, file)
            file_size = os.path.getsize(file_path)
            print(f"    - {file} ({format_size(file_size)})")
    else:
        print("    No files available")
    
    print("\nPress Ctrl+C to stop the server")
    
    # Create and start the server
    try:
        server = tftpy.TftpServer(directory)
        server.listen(ip, port)
    except KeyboardInterrupt:
        print("\nShutting down TFTP server")
    except PermissionError:
        print(f"\nError: Permission denied. You may need to run as root/sudo to use port {port}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

def format_size(size_bytes):
    """Format a file size in a human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def ssh_connect_with_shell(ip, username, password, timeout=10):
    """Connect to device via SSH and return client and channel"""
    print(f"Connecting to {ip} via SSH...")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(ip, username=username, password=password, timeout=timeout)
        print(f"Successfully connected to {ip}")
        
        channel = client.invoke_shell()
        channel.settimeout(timeout)
        
        time.sleep(2)
        initial_output = b""
        while channel.recv_ready():
            chunk = channel.recv(4096)
            initial_output += chunk
        
        initial_str = initial_output.decode('utf-8', errors='ignore')
        print("\n----- Initial SSH Connection Output -----")
        print(initial_str)
        print("-----------------------------------------\n")
        
        return client, channel
    except Exception as e:
        print(f"Error connecting to {ip}: {e}")
        return None, None

def execute_ssh_command(channel, command, wait_time=5, max_output_wait=30):
    """Execute command and get full output"""
    if not channel:
        return None
    
    while channel.recv_ready():
        channel.recv(4096)
    
    print(f"\n>>> Executing command: {command}")
    channel.send(command + "\n")
    
    output = b""
    start_time = time.time()
    last_receive_time = start_time
    
    time.sleep(1)
    
    while (time.time() - last_receive_time < wait_time and 
           time.time() - start_time < max_output_wait):
        if channel.recv_ready():
            chunk = channel.recv(4096)
            output += chunk
            print(chunk.decode('utf-8', errors='ignore'), end='')
            sys.stdout.flush()
            last_receive_time = time.time()
        else:
            time.sleep(0.1)
    
    output_str = output.decode('utf-8', errors='ignore')
    
    duration = time.time() - start_time
    print(f"\n\n>>> Command completed in {duration:.2f} seconds")
    
    return output_str

def main():
    print("\n===== COMTREND FIRMWARE UPGRADE UTILITY =====")

    # Connection mode: Auto Detect or Manual
    mode_options = ["Auto Detect (recommended)", "Manual"]
    mode_menu = TerminalMenu(mode_options, title="Connection mode:")
    mode_index = mode_menu.show()
    drain_tty_input()
    if mode_index is None:
        print("Cancelled.")
        return
    auto_detect_mode = mode_index == 0

    # Step 1: Power on and connect device
    print("\n===== STEP 1: CONNECT DEVICE =====")
    print("Please follow these instructions:")
    print("1. Power on the COMTREND device")
    print("2. Connect the device to this computer over ethernet")
    print("3. Wait for the device to fully boot")

    computer_ip = None
    selected_iface = None
    if auto_detect_mode:
        print("\nDetecting Ethernet connection (you can press Enter to switch to manual selection)...")
        detected = wait_for_ethernet_connection(timeout=300, interval=3)
        if detected:
            selected_iface, computer_ip = detected
            print(f"Ethernet detected: {selected_iface} -> {computer_ip}")
    if not auto_detect_mode or computer_ip is None:
        if not auto_detect_mode:
            input("Press Enter when the device is ready to continue...\n")

    # Step 2: Get firmware file
    print("\n===== STEP 2: SELECT FIRMWARE =====")
    
    # Offer two options for firmware selection
    selection_options = ["Select from firmware_images directory", "Enter custom file path"]
    selection_menu = TerminalMenu(selection_options, title="Choose firmware source:")
    selection_index = selection_menu.show()
    drain_tty_input()
    if selection_index is None:
        print("Firmware selection cancelled.")
        return
    
    firmware_path = None
    
    if selection_index == 0:
        # Select from firmware_images directory
        firmware_images_dir = "firmware_images"
        
        if not os.path.exists(firmware_images_dir):
            print(f"Error: {firmware_images_dir} directory not found")
            return
        
        # Get list of firmware files
        firmware_files = [f for f in os.listdir(firmware_images_dir) 
                         if os.path.isfile(os.path.join(firmware_images_dir, f))]
        
        if not firmware_files:
            print(f"Error: No firmware files found in {firmware_images_dir} directory")
            return
        
        # Display menu for firmware selection
        print(f"\nSelect a firmware file from {firmware_images_dir}:")
        firmware_menu = TerminalMenu(firmware_files, title="")
        firmware_index = firmware_menu.show()
        drain_tty_input()
        if firmware_index is None:
            print("Firmware selection cancelled.")
            return
        
        firmware_filename = firmware_files[firmware_index]
        firmware_path = os.path.join(firmware_images_dir, firmware_filename)
    else:
        # Enter custom file path
        firmware_path = input("\nEnter the path to the firmware image file: ")
        if not firmware_path:
            print("No file path entered.")
            return
    
    if not os.path.exists(firmware_path):
        print(f"Error: File {firmware_path} not found")
        return
    
    firmware_dir = os.path.dirname(os.path.abspath(firmware_path))
    if not firmware_dir:
        firmware_dir = os.getcwd()
    
    firmware_filename = os.path.basename(firmware_path)
    
    # Step 3: Start TFTP server
    print("\n===== STEP 3: STARTING TFTP SERVER =====")
    print(f"Starting TFTP server in: {firmware_dir}")
    print(f"Serving firmware file: {firmware_filename}")
    
    # Start TFTP server in a separate thread
    tftp_thread = threading.Thread(
        target=setup_tftp_server,
        args=(firmware_dir,),
        daemon=True
    )
    tftp_thread.start()
    
    # Step 4: Get network information (when not already set by auto-detect)
    if computer_ip is None:
        print("\n===== STEP 4: CONFIRM NETWORK CONNECTION =====")
        interfaces = get_network_interfaces()
        interface_options = [f"{iface}: {ip}" for (iface, ip) in interfaces]
        interface_menu = TerminalMenu(interface_options, title="Select the interface connected to the device")
        idx = interface_menu.show()
        drain_tty_input()
        if idx is None:
            print("Cancelled.")
            return
        selected_iface = interfaces[idx][0]
        computer_ip = interfaces[idx][1]
    print(f"Using computer IP: {computer_ip}")

    # Default device/gateway IP: detect from interface when possible
    default_device_ip = "192.168.1.1"
    gateway = get_gateway_for_connection(selected_iface, computer_ip)
    if gateway:
        default_device_ip = gateway
        print(f"Detected gateway address: {default_device_ip}")

    # Step 5: Connect to device
    print("\n===== STEP 5: CONNECT TO DEVICE =====")
    if auto_detect_mode and gateway:
        device_ip = default_device_ip
        print(f"Using device IP: {device_ip}")
    else:
        device_ip = input(f"Enter the device IP address (default: {default_device_ip}): ") or default_device_ip
    
    if not wait_for_ping(device_ip):
        print(f"Unable to reach device at {device_ip}. Please check the connection and try again.")
        return
    
    # Step 6: SSH and upgrade firmware
    print("\n===== STEP 6: UPGRADING FIRMWARE =====")
    print(f"Connecting to device at {device_ip}...")
    
    initial_username = os.getenv('COMTREND_INITIAL_USERNAME', 'admin')
    initial_password = os.getenv('COMTREND_INITIAL_PASSWORD', 'admin')
    
    ssh_client, channel = ssh_connect_with_shell(device_ip, initial_username, initial_password)
    if not ssh_client or not channel:
        print("Failed to connect to device. Please check the connection and try again.")
        return
    
    # Execute TFTP upgrade command
    upgrade_cmd = f"tftp -g -t i -f {firmware_filename} {computer_ip}"
    print(f"\nExecuting upgrade command: {upgrade_cmd}")
    output = execute_ssh_command(channel, upgrade_cmd)
    
    # Wait for upgrade to complete
    print("\nWaiting for firmware upgrade to complete...")
    time.sleep(60)  # Adjust this time based on your device's upgrade duration
    
    # Step 7: Restore defaults
    print("\n===== STEP 7: RESTORING DEFAULTS =====")
    output = execute_ssh_command(channel, "restoredefault")
    
    # Close SSH connection as device will reboot
    ssh_client.close()
    
    # Step 8: Wait for reboot and reconnect
    print("\n===== STEP 8: WAITING FOR REBOOT =====")
    print("Device is rebooting. This may take a few minutes...")
    time.sleep(120)  # Wait for device to reboot
    
    if not wait_for_ping(device_ip):
        print(f"Unable to reach device at {device_ip} after reboot.")
        return
    
    # Step 9: Connect with new credentials
    print("\n===== STEP 9: CONNECTING WITH NEW CREDENTIALS =====")
    upgraded_username = os.getenv('COMTREND_UPGRADED_USERNAME', 'admin')
    upgraded_password = os.getenv('COMTREND_UPGRADED_PASSWORD', 'admin')
    
    ssh_client, channel = ssh_connect_with_shell(device_ip, upgraded_username, upgraded_password)
    if not ssh_client or not channel:
        print("Failed to connect with new credentials. Please check the connection and try again.")
        return
    
    print("\n===== UPGRADE COMPLETE =====")
    print("The device has been successfully upgraded and restored to factory defaults.")
    print("You can now configure the device as needed.")
    
    ssh_client.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting program...")
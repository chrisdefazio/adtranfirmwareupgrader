#!/usr/bin/env python3
import os
import sys
import argparse
import tftpy
import logging
import time
import paramiko
import getpass
import platform
import subprocess
from dotenv import load_dotenv

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

def get_network_interfaces():
    """Get network interfaces and their IP addresses"""
    if platform.system() == "Windows":
        output = subprocess.run("ipconfig", shell=True, capture_output=True, text=True).stdout
        interfaces = []
        current_if = None
        for line in output.split('\n'):
            if ':' in line and not 'IPv' in line:
                current_if = line.split(':')[0].strip()
            if 'IPv4 Address' in line and current_if:
                ip = line.split(':')[1].strip()
                interfaces.append((current_if, ip))
        return interfaces
    else:
        output = subprocess.run("ifconfig | grep 'inet ' | grep -v 127.0.0.1", shell=True, capture_output=True, text=True).stdout
        interfaces = []
        for line in output.split('\n'):
            if line.strip():
                parts = line.strip().split()
                ip = parts[1]
                iface = line.split(':')[0] if ':' in line else "unknown"
                interfaces.append((iface, ip))
        return interfaces

def wait_for_ping(ip, timeout=300, interval=5):
    """Wait for device to respond to ping"""
    print(f"Waiting for device {ip} to respond to ping...")
    start_time = time.time()
    
    ping_cmd = "ping -n 1 " if platform.system().lower() == "windows" else "ping -c 1 "
    
    while time.time() - start_time < timeout:
        response = os.system(ping_cmd + ip + " > nul" if platform.system().lower() == "windows" else " > /dev/null")
        if response == 0:
            print(f"Device {ip} is responding to ping!")
            return True
            
        time.sleep(interval)
        print(f"Still waiting for device {ip}... ({int(time.time() - start_time)}s elapsed)")
    
    print(f"Timeout waiting for device {ip} to respond to ping")
    return False

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
    
    # Step 1: Power on and connect device
    print("\n===== STEP 1: CONNECT DEVICE =====")
    print("Please follow these instructions:")
    print("1. Power on the COMTREND device")
    print("2. Connect the device to this computer over ethernet")
    print("3. Wait for the device to fully boot")
    input("Press Enter when the device is ready to continue...\n")
    
    # Step 2: Get firmware file
    print("\n===== STEP 2: SELECT FIRMWARE =====")
    firmware_path = input("Enter the path to the firmware image file: ")
    
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
    import threading
    tftp_thread = threading.Thread(
        target=setup_tftp_server,
        args=(firmware_dir,),
        daemon=True
    )
    tftp_thread.start()
    
    # Step 4: Get network information
    print("\n===== STEP 4: CONFIRM NETWORK CONNECTION =====")
    print("Available network interfaces:")
    interfaces = get_network_interfaces()
    for i, (iface, ip) in enumerate(interfaces):
        print(f"{i+1}. {iface}: {ip}")
    
    idx = -1
    while idx < 0 or idx >= len(interfaces):
        try:
            idx = int(input(f"Select the interface connected to the device (1-{len(interfaces)}): ")) - 1
        except ValueError:
            print("Please enter a valid number")
    
    computer_ip = interfaces[idx][1]
    print(f"Using computer IP: {computer_ip}")
    
    # Step 5: Connect to device
    print("\n===== STEP 5: CONNECT TO DEVICE =====")
    device_ip = input("Enter the device IP address (default: 192.168.1.1): ") or "192.168.1.1"
    
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
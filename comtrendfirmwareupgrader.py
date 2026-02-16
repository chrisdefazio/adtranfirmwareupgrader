#!/usr/bin/env python3
import os
import sys
import argparse
import tftpy
import logging
import time
import threading
import paramiko
import getpass
import platform
import subprocess
from dotenv import load_dotenv
from simple_term_menu import TerminalMenu

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

def get_os_type():
    """Return the current OS for platform-specific logic: Darwin, Linux, or Windows."""
    return platform.system()

def _get_wired_interface_ip_darwin():
    """Detect a wired (Ethernet/USB LAN) interface with IPv4 on macOS. Returns (iface_name, ip) or None."""
    try:
        output = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        if output.returncode != 0:
            return None
        lines = output.stdout.splitlines()
        i = 0
        devices_to_try = []
        while i < len(lines):
            line = lines[i]
            if "Hardware Port:" in line:
                port_name = line.split("Hardware Port:")[-1].strip()
                if any(x in port_name for x in ("Ethernet", "LAN", "Thunderbolt")) and "Wi-Fi" not in port_name and "Bluetooth" not in port_name:
                    i += 1
                    while i < len(lines) and lines[i].strip().startswith("Device:"):
                        dev_line = lines[i]
                        dev = dev_line.split("Device:")[-1].strip()
                        if dev:
                            devices_to_try.append((port_name, dev))
                        i += 1
                    continue
            i += 1
        for port_name, dev in devices_to_try:
            ip_out = subprocess.run(
                ["ipconfig", "getifaddr", dev],
                capture_output=True, text=True, timeout=2
            )
            if ip_out.returncode == 0 and ip_out.stdout.strip():
                ip = ip_out.stdout.strip()
                if ip and not ip.startswith("127."):
                    return (port_name, ip)
        out = subprocess.run(
            "ifconfig | grep -A 2 '^en' | grep 'inet '",
            shell=True, capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            for line in out.stdout.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == "inet":
                    ip = parts[1]
                    if not ip.startswith("127."):
                        return ("enX", ip)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None

def _get_wired_interface_ip_linux():
    """Detect a wired interface with IPv4 on Linux. Returns (iface_name, ip) or None."""
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode != 0:
            return None
        for line in out.stdout.splitlines():
            if "lo" in line.split()[1]:
                continue
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "inet":
                iface = parts[1].rstrip(":")
                ip = parts[3].split("/")[0]
                if not ip.startswith("127."):
                    return (iface, ip)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    try:
        out = subprocess.run(
            "ifconfig | grep -E '^[a-z]' | grep -v lo",
            shell=True, capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            blocks = out.stdout.strip().split("\n\n")
            for block in blocks:
                lines = block.split("\n")
                iface = lines[0].split(":")[0].strip()
                for line in lines[1:]:
                    if "inet " in line and "127." not in line:
                        parts = line.strip().split()
                        for i, p in enumerate(parts):
                            if p == "inet" and i + 1 < len(parts):
                                ip = parts[i + 1].split("/")[0] if "/" in parts[i + 1] else parts[i + 1]
                                return (iface, ip)
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None

def _get_wired_interface_ip_windows():
    """Detect a wired Ethernet adapter with IPv4 on Windows. Returns (adapter_name, ip) or None."""
    try:
        output = subprocess.run(
            "ipconfig",
            shell=True, capture_output=True, text=True, timeout=10
        )
        if output.returncode != 0:
            return None
        lines = output.stdout.splitlines()
        current_adapter = None
        for line in lines:
            if line.strip() and ":" in line and not line.strip().startswith(" "):
                current_adapter = line.split(":")[0].strip()
            if current_adapter and "IPv4 Address" in line:
                if any(x in current_adapter for x in ("Virtual", "VPN", "Bluetooth", "Loopback")):
                    continue
                if any(x in current_adapter for x in ("Ethernet", "LAN", "Local Area")):
                    ip = line.split(":")[-1].strip()
                    if ip and not ip.startswith("127."):
                        return (current_adapter, ip)
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None

def get_wired_interface_ip():
    """Return (iface_name, ip) for a wired interface with IPv4 on current OS, or None."""
    os_type = get_os_type()
    if os_type == "Darwin":
        return _get_wired_interface_ip_darwin()
    if os_type == "Linux":
        return _get_wired_interface_ip_linux()
    if os_type == "Windows":
        return _get_wired_interface_ip_windows()
    return None

def wait_for_ethernet_connection(timeout=300, interval=3):
    """Poll for a wired Ethernet interface with IPv4. Allows switching to manual mode during wait.
    Returns (iface_name, ip) when detected, or None on timeout or if user switches to manual."""
    manual_requested = [False]

    def wait_for_manual_key():
        try:
            input("\nPress Enter to switch to manual interface selection... ")
            manual_requested[0] = True
        except (EOFError, KeyboardInterrupt):
            manual_requested[0] = True

    t = threading.Thread(target=wait_for_manual_key, daemon=True)
    t.start()
    start_time = time.time()
    last_status = 0
    try:
        while time.time() - start_time < timeout:
            if manual_requested[0]:
                return None
            result = get_wired_interface_ip()
            if result:
                return result
            elapsed = int(time.time() - start_time)
            if elapsed >= last_status + interval or last_status == 0:
                print(f"Waiting for Ethernet connection... ({elapsed}s)")
                last_status = elapsed
            time.sleep(interval)
    finally:
        manual_requested[0] = True
    return None

def get_gateway_for_connection(iface_name=None, computer_ip=None):
    """Get the default gateway (router) for the given interface or computer IP.
    Returns gateway IP string or None. Used to suggest the device/gateway address."""
    os_type = get_os_type()
    if os_type == "Darwin":
        if iface_name:
            if " " in iface_name or "LAN" in iface_name or "Ethernet" in iface_name:
                try:
                    out = subprocess.run(
                        ["networksetup", "-getinfo", iface_name],
                        capture_output=True, text=True, timeout=5
                    )
                    if out.returncode == 0:
                        for line in out.stdout.splitlines():
                            if line.strip().startswith("Router:"):
                                gw = line.split("Router:")[-1].strip()
                                if gw and gw != "(none)":
                                    return gw
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
            try:
                out = subprocess.run(
                    "netstat -nr -f inet",
                    shell=True, capture_output=True, text=True, timeout=5
                )
                if out.returncode == 0:
                    for line in out.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] == "default" and len(parts) >= 6 and parts[-1] == iface_name:
                            return parts[1]
            except (subprocess.TimeoutExpired, OSError):
                pass
        if computer_ip:
            try:
                out = subprocess.run(
                    "netstat -nr -f inet",
                    shell=True, capture_output=True, text=True, timeout=5
                )
                if out.returncode == 0:
                    for line in out.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] == "default":
                            return parts[1]
            except (subprocess.TimeoutExpired, OSError):
                pass
    if os_type == "Linux":
        if iface_name:
            try:
                out = subprocess.run(
                    ["ip", "route", "show", "dev", iface_name],
                    capture_output=True, text=True, timeout=5
                )
                if out.returncode == 0:
                    for line in out.stdout.splitlines():
                        if "default" in line and "via" in line:
                            tokens = line.split()
                            for i, p in enumerate(tokens):
                                if p == "via" and i + 1 < len(tokens):
                                    return tokens[i + 1]
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        if computer_ip:
            try:
                out = subprocess.run(
                    ["ip", "route", "show", "default"],
                    capture_output=True, text=True, timeout=5
                )
                if out.returncode == 0 and out.stdout.strip():
                    parts = out.stdout.strip().split()
                    if "via" in parts:
                        idx = parts.index("via")
                        if idx + 1 < len(parts):
                            return parts[idx + 1]
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
    if os_type == "Windows":
        try:
            out = subprocess.run(
                "ipconfig",
                shell=True, capture_output=True, text=True, timeout=10
            )
            if out.returncode != 0:
                return None
            lines = out.stdout.splitlines()
            current_ip = None
            for line in lines:
                if line.strip() and not line.startswith(" ") and ":" in line:
                    current_ip = None
                if "IPv4 Address" in line and ":" in line:
                    current_ip = line.split(":")[-1].strip()
                if current_ip and "Default Gateway" in line and ":" in line:
                    gw = line.split(":")[-1].strip()
                    if gw and (computer_ip is None or current_ip == computer_ip):
                        return gw
        except (subprocess.TimeoutExpired, OSError):
            pass
    return None

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

    # Connection mode: Auto Detect or Manual
    mode_options = ["Auto Detect (recommended)", "Manual"]
    mode_menu = TerminalMenu(mode_options, title="Connection mode:")
    mode_index = mode_menu.show()
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
    import threading
    tftp_thread = threading.Thread(
        target=setup_tftp_server,
        args=(firmware_dir,),
        daemon=True
    )
    tftp_thread.start()
    
    # Step 4: Get network information (when not already set by auto-detect)
    if computer_ip is None:
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
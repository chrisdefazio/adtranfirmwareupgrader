import os
import subprocess
import http.server
import socketserver
import threading
import time
import platform
import socket
import paramiko
import getpass
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from dotenv import load_dotenv
import csv
from datetime import datetime
from simple_term_menu import TerminalMenu

# Load environment variables from .env file
load_dotenv()

# Configure HTTP server for firmware hosting
class SimpleHTTPServerThread(threading.Thread):
    def __init__(self, port=8000, directory=None):
        threading.Thread.__init__(self)
        self.port = port
        self.directory = directory
        self.daemon = True  # Daemon thread will close when the main program exits
        
    def run(self):
        if self.directory:
            os.chdir(self.directory)
            
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", self.port), handler) as httpd:
            print(f"HTTP server running at port {self.port}")
            httpd.serve_forever()

def run_command(command):
    """Run a shell command and return the output"""
    try:
        result = subprocess.run(command, shell=True, check=True, 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                               text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return None

def clear_ssh_key(ip):
    """Clear SSH known hosts for the IP"""
    if platform.system() == "Windows":
        print(f"On Windows, manually remove the key for {ip} from ~/.ssh/known_hosts if needed")
    else:
        run_command(f"ssh-keygen -R {ip}")
        print(f"Cleared SSH key for {ip}")

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
        # Parse "Hardware Port: ..." and "Device: enX" for Ethernet-like ports
        lines = output.stdout.splitlines()
        i = 0
        devices_to_try = []
        while i < len(lines):
            line = lines[i]
            if "Hardware Port:" in line:
                port_name = line.split("Hardware Port:")[-1].strip()
                # Consider Ethernet, USB LAN, etc. (exclude Wi-Fi, Bluetooth)
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
        # Fallback: ifconfig for inet on en* interfaces
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
                        iface = "enX"  # generic
                        return (iface, ip)
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
            # Skip loopback
            if "lo" in line.split()[1]:
                continue
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "inet":
                # interface name has colon: eth0:2 -> eth0
                iface = parts[1].rstrip(":")
                ip_cidr = parts[3]
                ip = ip_cidr.split("/")[0]
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
                                ip = parts[i + 1]
                                if "/" in ip:
                                    ip = ip.split("/")[0]
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
                # Adapter name line (e.g. "Ethernet adapter Ethernet:")
                current_adapter = line.split(":")[0].strip()
            if current_adapter and "IPv4 Address" in line:
                # Exclude virtual/vpn/bluetooth
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
    manual_requested = [False]  # list so closure can mutate

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
        manual_requested[0] = True  # allow input thread to exit if still waiting
    return None

def get_gateway_for_connection(iface_name=None, computer_ip=None):
    """Get the default gateway (router) for the given interface or computer IP.
    Returns gateway IP string or None. Used to suggest the device/gateway address."""
    os_type = get_os_type()
    if os_type == "Darwin":
        if iface_name:
            # Port name (e.g. "USB 10/100/1000 LAN") -> networksetup -getinfo
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
            # Device name (e.g. en5) -> netstat and match interface
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
                            for i, p in enumerate(line.split()):
                                if p == "via" and i + 1 < len(line.split()):
                                    return line.split()[i + 1]
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
                # New adapter section (no leading space)
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

def get_network_interfaces():
    """Get network interfaces and their IP addresses"""
    if platform.system() == "Windows":
        output = run_command("ipconfig")
        # Simple parsing for Windows ipconfig output
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
        # For Unix-like systems
        output = run_command("ifconfig | grep 'inet ' | grep -v 127.0.0.1")
        interfaces = []
        for line in output.split('\n'):
            if line.strip():
                # Extract interface and IP address
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

def get_ssh_credentials(ip):
    """Determine which SSH credentials to use based on IP address"""
    if ip.startswith("172.16.192."):
        print("Using upgraded firmware credentials (172.16.192.x IP range)")
        return os.getenv('UPGRADED_USERNAME'), os.getenv('UPGRADED_PASSWORD')
    else:
        print("Using initial firmware credentials")
        return os.getenv('INITIAL_USERNAME'), os.getenv('INITIAL_PASSWORD')

def ssh_connect_with_shell(ip, username=None, password=None, timeout=10, prompt_on_fail=False):
    """Connect to device via SSH and return client and channel
    
    Args:
        ip: Device IP address
        username: SSH username (if None, will be determined from IP)
        password: SSH password (if None, will be determined from IP)
        timeout: Connection timeout in seconds
        prompt_on_fail: If True, prompt user for manual credentials on auth failure
    """
    print(f"Connecting to {ip} via SSH...")
    
    # If credentials not provided, determine them based on IP
    if username is None or password is None:
        username, password = get_ssh_credentials(ip)
    
    print(f"Using username: '{username}'")
    print(f"Using password: '{password[:2]}{'*' * (len(password) - 2) if password and len(password) > 2 else ''}'")
    
    # Create SSH client
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # Handler for keyboard-interactive authentication
    def kbd_interactive_handler(title, instructions, prompt_list):
        """Handle keyboard-interactive authentication prompts"""
        responses = []
        for prompt, echo in prompt_list:
            if 'password' in prompt.lower():
                responses.append(password)
            else:
                responses.append(password)  # Default to password for unknown prompts
        return responses
    
    def attempt_connection(user, pwd):
        """Attempt SSH connection with given credentials"""
        nonlocal client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Update handler to use current password
        def handler(title, instructions, prompt_list):
            responses = []
            for prompt, echo in prompt_list:
                responses.append(pwd)
            return responses
        
        try:
            # First try standard password authentication
            client.connect(ip, username=user, password=pwd, timeout=timeout,
                          allow_agent=False, look_for_keys=False)
            print(f"Successfully connected to {ip} (password auth)")
            
            # Create an interactive shell
            channel = client.invoke_shell()
            channel.settimeout(timeout)
            
            # Wait for initial prompt
            time.sleep(2)
            initial_output = b""
            while channel.recv_ready():
                chunk = channel.recv(4096)
                initial_output += chunk
            
            initial_str = initial_output.decode('utf-8', errors='ignore')
            print("\n----- Initial SSH Connection Output -----")
            print(initial_str)
            print("-----------------------------------------\n")
            
            return client, channel, None  # Success, no error
        except paramiko.AuthenticationException as auth_err:
            print(f"Password authentication failed: {auth_err}")
            print("Attempting keyboard-interactive authentication...")
            
            # Close the failed connection and try keyboard-interactive
            try:
                client.close()
            except:
                pass
            
            try:
                # Get transport for keyboard-interactive auth
                transport = paramiko.Transport((ip, 22))
                transport.connect()
                transport.auth_interactive(user, handler)
                
                # Create client from transport
                client = paramiko.SSHClient()
                client._transport = transport
                print(f"Successfully connected to {ip} (keyboard-interactive auth)")
                
                # Create an interactive shell
                channel = transport.open_session()
                channel.get_pty()
                channel.invoke_shell()
                channel.settimeout(timeout)
                
                # Wait for initial prompt
                time.sleep(2)
                initial_output = b""
                while channel.recv_ready():
                    chunk = channel.recv(4096)
                    initial_output += chunk
                
                initial_str = initial_output.decode('utf-8', errors='ignore')
                print("\n----- Initial SSH Connection Output -----")
                print(initial_str)
                print("-----------------------------------------\n")
                
                return client, channel, None  # Success
            except Exception as kbd_err:
                print(f"Keyboard-interactive authentication also failed: {kbd_err}")
                return None, None, "auth_failed"
        except paramiko.SSHException as ssh_err:
            print(f"SSH error connecting to {ip}: {ssh_err}")
            return None, None, "ssh_error"
        except socket.timeout:
            print(f"Connection to {ip} timed out after {timeout} seconds")
            return None, None, "timeout"
        except socket.error as sock_err:
            print(f"Socket error connecting to {ip}: {sock_err}")
            return None, None, "socket_error"
        except Exception as e:
            print(f"Unexpected error connecting to {ip}: {type(e).__name__}: {e}")
            return None, None, "unknown_error"
    
    # First attempt with provided/default credentials
    client, channel, error = attempt_connection(username, password)
    
    if client and channel:
        return client, channel
    
    # If auth failed and prompt_on_fail is enabled, ask for manual credentials
    if error == "auth_failed" and prompt_on_fail:
        print("\n" + "="*50)
        print("AUTHENTICATION FAILED - Enter credentials manually")
        print("="*50)
        print(f"(Press Enter to keep current value)")
        
        new_username = input(f"Username [{username}]: ").strip()
        if new_username:
            username = new_username
        
        new_password = getpass.getpass(f"Password: ")
        if new_password:
            password = new_password
        
        print(f"\nRetrying with username: '{username}'")
        client, channel, error = attempt_connection(username, password)
        
        if client and channel:
            return client, channel
    
    return None, None

def retry_ssh_connect(ip, username=None, password=None, max_attempts=10, retry_delay=10, prompt_on_auth_fail=True):
    """Attempt to connect via SSH with multiple retries
    
    Args:
        ip: Device IP address
        username: SSH username (if None, will be determined from IP)
        password: SSH password (if None, will be determined from IP)
        max_attempts: Maximum number of connection attempts
        retry_delay: Delay between retries in seconds
        prompt_on_auth_fail: If True, prompt for manual credentials on first auth failure
    """
    print(f"Attempting to connect to {ip} via SSH (max {max_attempts} attempts)...")
    
    # If credentials not provided, determine them based on IP
    if username is None or password is None:
        username, password = get_ssh_credentials(ip)
    
    prompted_for_creds = False
    
    for attempt in range(1, max_attempts + 1):
        print(f"\nAttempt {attempt}/{max_attempts}...")
        
        # On first attempt, allow prompting for credentials if auth fails
        # After manual entry, use those credentials for subsequent retries
        should_prompt = prompt_on_auth_fail and not prompted_for_creds
        
        ssh_client, channel = ssh_connect_with_shell(ip, username, password, prompt_on_fail=should_prompt)
        
        if ssh_client and channel:
            print(f"✓ Successfully connected to {ip} on attempt {attempt}")
            return ssh_client, channel
        
        # Mark that we've given the user a chance to enter credentials
        if should_prompt:
            prompted_for_creds = True
        
        if attempt < max_attempts:
            print(f"Connection failed. Waiting {retry_delay} seconds before retrying...")
            time.sleep(retry_delay)
    
    print(f"✗ Failed to connect to {ip} after {max_attempts} attempts")
    return None, None

def execute_ssh_command(channel, command, wait_time=5, max_output_wait=30):
    """Execute command and get full output"""
    if not channel:
        return None
    
    # Clear any pending output
    while channel.recv_ready():
        channel.recv(4096)
    
    # Send command
    print(f"\n>>> Executing command: {command}")
    channel.send(command + "\n")
    
    # Collect output with timeout
    output = b""
    start_time = time.time()
    last_receive_time = start_time
    
    # First short wait
    time.sleep(1)
    
    while (time.time() - last_receive_time < wait_time and 
           time.time() - start_time < max_output_wait):
        if channel.recv_ready():
            chunk = channel.recv(4096)
            output += chunk
            print(chunk.decode('utf-8', errors='ignore'), end='')
            sys.stdout.flush()  # Force output to display immediately
            last_receive_time = time.time()
        else:
            time.sleep(0.1)
    
    # Convert to string
    output_str = output.decode('utf-8', errors='ignore')
    
    # Print summary
    duration = time.time() - start_time
    print(f"\n\n>>> Command completed in {duration:.2f} seconds")
    
    return output_str

def safe_close_ssh_connection(ssh_client, channel):
    """Safely close SSH connection and channel"""
    if channel:
        try:
            channel.close()
        except:
            pass
    
    if ssh_client:
        try:
            ssh_client.close()
        except:
            pass
    
    # Give time for connection to fully terminate
    time.sleep(2)

def monitor_upgrade_progress(channel, timeout=300):
    """Monitor the upgrade process until completion or timeout"""
    print("\n----- Monitoring Upgrade Progress -----")
    
    start_time = time.time()
    last_output = ""
    download_started = False
    upgrade_complete = False
    
    while time.time() - start_time < timeout:
        if channel.recv_ready():
            output = channel.recv(4096).decode('utf-8', errors='ignore')
            print(output, end='')
            sys.stdout.flush()
            last_output += output
            
            # Check for progress indicators
            if "download" in output.lower() or "transfer" in output.lower() or "%" in output:
                download_started = True
            
            if "success" in output.lower() or "complete" in output.lower():
                upgrade_complete = True
                print("\n\n>>> Upgrade completed successfully!")
                break
                
            if "error" in output.lower() or "fail" in output.lower():
                print("\n\n>>> Upgrade failed!")
                break
        else:
            # If no data available, wait briefly
            time.sleep(0.5)
    
    print("\n----- End of Monitoring -----\n")
    
    if time.time() - start_time >= timeout:
        print("\n>>> Monitoring timed out!")
    
    return download_started, upgrade_complete, last_output

def check_firmware_received(server_log):
    """Check if the firmware file was received by the HTTP server"""
    for line in server_log.getvalue().split("\n"):
        if "GET" in line and "200" in line:
            return True
    return False

def main():
    # Check for paramiko library
    try:
        import paramiko
    except ImportError:
        print("The paramiko library is required. Please install it using:")
        print("pip install paramiko")
        return
    
    # Ask user what they want to do
    print("\n===== ADTRAN DEVICE UTILITY =====")
    print("1. Upgrade firmware and extract device information")
    print("2. Extract device information only (no upgrade)")
    choice = input("\nSelect an option (1 or 2): ")
    
    if choice not in ["1", "2"]:
        print("Invalid choice. Please select 1 or 2.")
        return

    # Connection mode: Auto Detect or Manual (select at start; can switch to manual during auto-detect)
    mode_options = ["Auto Detect (recommended)", "Manual"]
    mode_menu = TerminalMenu(mode_options, title="Connection mode:")
    mode_index = mode_menu.show()
    if mode_index is None:
        print("Cancelled.")
        return
    auto_detect_mode = mode_index == 0

    if choice == "1":
        # Offer two options for firmware selection
        print("\n===== FIRMWARE FILE SELECTION =====")
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
        
        # Start HTTP server for firmware hosting
        # We'll serve from the directory containing the firmware file
        firmware_dir = os.path.dirname(os.path.abspath(firmware_path))
        if not firmware_dir:  # If the file is in the current directory
            firmware_dir = os.getcwd()
        
        firmware_filename = os.path.basename(firmware_path)
        
        print(f"\nStarting HTTP server in: {firmware_dir}")
        print(f"Serving firmware file: {firmware_filename}")
        
        server_thread = SimpleHTTPServerThread(port=8000, directory=firmware_dir)
        server_thread.start()
    
    # Display instructions for connecting the gateway
    print("\n===== STEP 1: CONNECT DEVICE =====")
    print("Please follow these instructions:")
    print("1. Plug in the 834_v6 gateway to power")
    print("2. Connect the gateway to this computer over ethernet")
    print("3. Wait for the status light to blink blue/green indicating it's fully booted")

    computer_ip = None
    selected_iface = None
    if auto_detect_mode:
        print("\nDetecting Ethernet connection (you can press Enter to switch to manual selection)...")
        detected = wait_for_ethernet_connection(timeout=300, interval=3)
        if detected:
            iface_name, computer_ip = detected
            selected_iface = iface_name
            print(f"Ethernet detected: {iface_name} -> {computer_ip}")
    if not auto_detect_mode or computer_ip is None:
        if not auto_detect_mode:
            input("Press Enter when the device is ready to continue...\n")
        # Display network interfaces and prompt for computer IP (manual or fallback)
        print("\n===== STEP 2: CONFIRM NETWORK CONNECTION =====")
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
    # Prompt for device IP
    device_ip = input(f"\nEnter the device IP address (default: {default_device_ip}): ") or default_device_ip
    
    # Clear SSH key for device IP
    clear_ssh_key(device_ip)
    
    if choice == "1":
        # Connect to device via SSH and perform upgrade
        print("\n===== STEP 3: UPGRADING FIRMWARE =====")
        print(f"Connecting to device at {device_ip}...")
        
        # SSH connection with interactive shell and automatic credential selection
        ssh_client, channel = ssh_connect_with_shell(device_ip, prompt_on_fail=True)
        if not ssh_client or not channel:
            print("Failed to connect to device. Please check the connection and try again.")
            return
        
        # Execute system restore nvram command to clear RAM before upgrade
        print("\nExecuting system restore nvram command to clear RAM...")
        output = execute_ssh_command(channel, "system restore nvram")
        
        # Monitor for confirmation prompt
        if "confirm" in output.lower() or "proceed" in output.lower() or "y/n" in output.lower():
            print("Confirmation prompt detected. Sending 'y'...")
            output = execute_ssh_command(channel, "y")
        
        # Execute upgrade command
        upgrade_url = f"http://{computer_ip}:8000/{firmware_filename}"
        output = execute_ssh_command(channel, f"upgrade {upgrade_url}")
        
        # Monitor for confirmation prompt
        if "confirm" in output.lower() or "proceed" in output.lower() or "y/n" in output.lower():
            print("Second confirmation prompt detected. Sending 'y'...")
            output = execute_ssh_command(channel, "y")
        
        # Monitor the upgrade progress
        print("\nStarting to monitor upgrade progress...")
        download_started, upgrade_complete, last_output = monitor_upgrade_progress(channel)
        
        if download_started:
            print("✓ Firmware download was initiated")
        else:
            print("✗ Firmware download may not have started")
        
        if upgrade_complete:
            print("✓ Upgrade process completed successfully")
        else:
            print("⚠ Upgrade completion confirmation not received")
            print("The upgrade may still be in progress or may have failed.")
        
        # Execute system restore default command
        print("\nExecuting system restore default command...")
        output = execute_ssh_command(channel, "system restore default")
        
        # Monitor for confirmation prompt
        if "confirm" in output.lower() or "proceed" in output.lower() or "y/n" in output.lower():
            print("Confirmation prompt detected. Sending 'y'...")
            output = execute_ssh_command(channel, "y")
        
        # Safely close SSH connection before device reboots
        print("\nSafely closing SSH connection...")
        safe_close_ssh_connection(ssh_client, channel)
        
        # Instructions for waiting for reboot
        print("\n===== STEP 4: WAITING FOR DEVICE REBOOT =====")
        print("The device is now performing a system restore and will reboot automatically.")
        print("Please wait while the device completes this process...")
        
        # Prompt for new device IP
        print("\n===== STEP 5: CONNECT TO UPGRADED DEVICE =====")
        print("The device IP has changed. The new IP should be in the 172.16.192.x range.")
        new_device_ip = input("Enter the new device IP address (default: 172.16.192.1): ") or "172.16.192.1"
        
        # Wait for device to respond
        if wait_for_ping(new_device_ip):
            # Give services time to start
            print(f"\nDevice is responding to ping. Waiting 30 seconds for all services to start...")
            time.sleep(30)
            
            # Clear SSH key for new device IP
            clear_ssh_key(new_device_ip)
            
            # Connect to upgraded device with retries
            print(f"\nConnecting to upgraded device at {new_device_ip}...")
            ssh_client, channel = retry_ssh_connect(new_device_ip)
            
            if ssh_client and channel:
                extract_device_info(ssh_client, channel, new_device_ip, operation_type="Upgrade")
                ssh_client.close()
            
            # Final instructions for web configuration
            print("\n===== STEP 6: COMPLETE SETUP VIA WEB GUI =====")
            print(f"Open a web browser and navigate to: http://{new_device_ip}")
            print("Set Intellifi mode to 'Mesh Controller'")
            print("Login and confirm the router is working as expected")
        else:
            print(f"Unable to reach device at {new_device_ip}. Please check the connection and try again.")
    else:
        # Just extract device information
        print("\n===== EXTRACTING DEVICE INFORMATION =====")
        print(f"Connecting to device at {device_ip}...")
        
        # Connect to device with retries and automatic credential selection
        ssh_client, channel = retry_ssh_connect(device_ip, max_attempts=5, retry_delay=15)
        
        if ssh_client and channel:
            extract_device_info(ssh_client, channel, device_ip, operation_type="Info Only")
            ssh_client.close()
        else:
            print("Failed to connect to device. Please check the connection and try again.")
    
    print("\n===== OPERATION COMPLETE =====")
    if choice == "1":
        print("The device has been successfully upgraded and configured.")
    else:
        print("Device information has been successfully extracted.")
    
    if choice == "1":
        print("\nThe HTTP server is still running. Press Ctrl+C to exit the program when you're finished.")

def extract_device_info(ssh_client, channel, device_ip, operation_type="Info Only"):
    """Extract and save device information"""
    # Get WiFi configuration
    print("\nRetrieving WiFi configuration...")
    wifi_output = execute_ssh_command(channel, "show wifi config")
    
    # Extract WiFi SSID and password
    ssid = ""
    wifi_key = ""
    if wifi_output:
        for line in wifi_output.split('\n'):
            if "wireless.i5g.ssid" in line:
                ssid = line.split("=")[1].strip().strip("'")
            if "wireless.i5g.key" in line:
                wifi_key = line.split("=")[1].strip().strip("'")
    
    if ssid and wifi_key:
        print("\n===== WIFI CONFIGURATION =====")
        print(f"SSID: {ssid}")
        print(f"Password: {wifi_key}")
    
    # Get device info
    print("\nRetrieving device information...")
    mfg_output = execute_ssh_command(channel, "show mfg")
    
    # Extract serial and MAC
    serial = ""
    mac = ""
    if mfg_output:
        for line in mfg_output.split('\n'):
            if "MFG_SERIAL" in line:
                serial = line.split("=")[1].strip()
            if "MFG_MAC" in line:
                mac = line.split("=")[1].strip()
    
    if serial and mac:
        print("\n===== DEVICE INFORMATION =====")
        print(f"Serial Number: {serial}")
        print(f"MAC Address: {mac}")
    
    # Get firmware build information
    print("\nRetrieving firmware build information...")
    build_output = execute_ssh_command(channel, "show buildinfo")
    
    # Extract firmware description
    firmware_version = ""
    if build_output:
        for line in build_output.split('\n'):
            if "DISTRIB_DESCRIPTION" in line:
                firmware_version = line.split("=")[1].strip().strip("'")
                print(f"Firmware Version: {firmware_version}")
    
    # Save the information to a CSV file
    csv_file = "device_upgrades.csv"
    file_exists = os.path.isfile(csv_file)
    
    try:
        with open(csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            # Write header if file is new
            if not file_exists:
                writer.writerow(['Timestamp', 'Device IP', 'WiFi SSID', 'WiFi Password', 'Serial Number', 'MAC Address', 'Firmware Version', 'Operation Type'])
            
            # Write device information
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([timestamp, device_ip, ssid, wifi_key, serial, mac, firmware_version, operation_type])
            
        print(f"\nDevice information appended to {csv_file}")
    except Exception as e:
        print(f"Error saving device information: {e}")

if __name__ == "__main__":
    try:
        main()
        # Keep the main thread running so the HTTP server stays alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting program...")
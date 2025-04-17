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

def ssh_connect_with_shell(ip, username, password, timeout=10):
    """Connect to device via SSH and return client and channel"""
    print(f"Connecting to {ip} via SSH...")
    
    # Create SSH client
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connect to the device
        client.connect(ip, username=username, password=password, timeout=timeout)
        print(f"Successfully connected to {ip}")
        
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
        
        return client, channel
    except Exception as e:
        print(f"Error connecting to {ip}: {e}")
        return None, None

def retry_ssh_connect(ip, username, password, max_attempts=5, retry_delay=10):
    """Attempt to connect via SSH with multiple retries"""
    print(f"Attempting to connect to {ip} via SSH (max {max_attempts} attempts)...")
    
    for attempt in range(1, max_attempts + 1):
        print(f"\nAttempt {attempt}/{max_attempts}...")
        ssh_client, channel = ssh_connect_with_shell(ip, username, password)
        
        if ssh_client and channel:
            print(f"✓ Successfully connected to {ip} on attempt {attempt}")
            return ssh_client, channel
        
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
    
    # Get firmware file path
    firmware_path = input("Enter the path to the firmware image file: ")
    
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
    input("Press Enter when the device is ready to continue...\n")
    
    # Display network interfaces and prompt for computer IP
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
    
    computer_ip = interfaces[idx][1]
    print(f"Using computer IP: {computer_ip}")
    
    # Prompt for device IP
    device_ip = input("\nEnter the device IP address (default: 192.168.1.1): ") or "192.168.1.1"
    
    # Clear SSH key for device IP
    clear_ssh_key(device_ip)
    
    # Connect to device via SSH and perform upgrade
    print("\n===== STEP 3: UPGRADING FIRMWARE =====")
    print(f"Connecting to device at {device_ip}...")
    
    # SSH connection with interactive shell
    ssh_client, channel = ssh_connect_with_shell(device_ip, os.getenv('INITIAL_USERNAME'), os.getenv('INITIAL_PASSWORD'))
    if not ssh_client or not channel:
        print("Failed to connect to device. Please check the connection and try again.")
        return
    
    # Execute upgrade command
    upgrade_url = f"http://{computer_ip}:8000/{firmware_filename}"
    output = execute_ssh_command(channel, f"upgrade {upgrade_url}")
    
    # Monitor for confirmation prompt
    if "confirm" in output.lower() or "proceed" in output.lower() or "y/n" in output.lower():
        print("Confirmation prompt detected. Sending 'y'...")
        output = execute_ssh_command(channel, "y")
        
        # Check for second confirmation
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
    
    # Close SSH connection as device will reboot
    ssh_client.close()
    
    # Instructions for reset and reboot
    print("\n===== STEP 4: WAIT FOR UPGRADE AND RESET =====")
    print("The device should now be flashing the firmware and will reboot when done.")
    print("Please monitor the device's indicator lights:")
    print("1. Wait for the status light to blink blue/green (indicating it's ready)")
    print("2. Then press and hold the RESET button until the blue indicator light blinks")
    print("3. Wait for the indicator light to flash green again")
    input("Press Enter when this process is complete...\n")
    
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
        ssh_client, channel = retry_ssh_connect(new_device_ip, os.getenv('UPGRADED_USERNAME'), os.getenv('UPGRADED_PASSWORD'), max_attempts=5, retry_delay=15)

        if ssh_client and channel:
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
            
            # Save the information to a file
            device_info_file = f"device_info_{new_device_ip.replace('.', '_')}.txt"
            try:
                with open(device_info_file, 'w') as f:
                    f.write(f"Device IP: {new_device_ip}\n")
                    f.write(f"WiFi SSID: {ssid}\n")
                    f.write(f"WiFi Password: {wifi_key}\n")
                    f.write(f"Serial Number: {serial}\n")
                    f.write(f"MAC Address: {mac}\n")
                print(f"\nDevice information saved to {device_info_file}")
            except Exception as e:
                print(f"Error saving device information: {e}")
            
            # Close SSH connection
            ssh_client.close()
        
        # Final instructions for web configuration
        print("\n===== STEP 6: COMPLETE SETUP VIA WEB GUI =====")
        print(f"Open a web browser and navigate to: http://{new_device_ip}")
        print("Set Intellifi mode to 'Mesh Controller'")
        print("Login and confirm the router is working as expected")
    else:
        print(f"Unable to reach device at {new_device_ip}. Please check the connection and try again.")
    
    print("\n===== SETUP COMPLETE =====")
    print("The device has been successfully upgraded and configured.")
    print("\nThe HTTP server is still running. Press Ctrl+C to exit the program when you're finished.")

if __name__ == "__main__":
    try:
        main()
        # Keep the main thread running so the HTTP server stays alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting program...")
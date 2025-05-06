"""
Utility functions for firmware upgrade operations.
"""

import os
import sys
import time
import paramiko
import platform
import subprocess

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

def clear_ssh_key(ip):
    """Clear SSH known hosts for the IP"""
    if platform.system() == "Windows":
        print(f"On Windows, manually remove the key for {ip} from ~/.ssh/known_hosts if needed")
    else:
        subprocess.run(f"ssh-keygen -R {ip}", shell=True)
        print(f"Cleared SSH key for {ip}")

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

def extract_device_info(ssh_client, channel, device_ip):
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
    
    # Save the information to a file
    device_info_file = f"device_info_{device_ip.replace('.', '_')}.txt"
    try:
        with open(device_info_file, 'w') as f:
            f.write(f"Device IP: {device_ip}\n")
            f.write(f"WiFi SSID: {ssid}\n")
            f.write(f"WiFi Password: {wifi_key}\n")
            f.write(f"Serial Number: {serial}\n")
            f.write(f"MAC Address: {mac}\n")
        print(f"\nDevice information saved to {device_info_file}")
    except Exception as e:
        print(f"Error saving device information: {e}") 
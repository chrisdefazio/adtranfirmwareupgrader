# Unified Firmware Upgrader

A Python-based tool for upgrading firmware on network devices. Currently supports ADTRAN and Comtrend devices, with a modular design that makes it easy to add support for additional device types.

## Features

- Support for multiple device types (ADTRAN, Comtrend)
- Guided upgrade process with clear instructions
- Automatic device information gathering
- Configuration backup and restore
- Progress monitoring during upgrade
- Cross-platform support (Windows, macOS, Linux)

## Requirements

- Python 3.6 or higher
- Required Python packages (see requirements.txt)
- Network connection to the device
- Firmware image file for the target device

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/firmwareupgrader.git
cd firmwareupgrader
```

2. Create and activate a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the firmware upgrader:
```bash
python firmwareupgrader.py
```

2. Follow the on-screen prompts to:
   - Select device type
   - Enter device IP address
   - Provide device credentials
   - Select firmware file
   - Confirm upgrade

## Device Support

### ADTRAN Devices
- Supports ADTRAN 834v6 and similar models
- Uses SSH for device communication
- Backs up and restores device configuration

### Comtrend Devices
- Supports Comtrend VR-3071 and VR-3071v2
- Uses SSH for device communication
- Backs up and restores device configuration

## Adding Support for New Devices

To add support for a new device type:

1. Create a new class in the `devices` directory that inherits from `DeviceUpgrader`
2. Implement all required methods from the base class
3. Add the new device class to the `DEVICE_TYPES` dictionary in `firmwareupgrader.py`

Example:
```python
from devices.base import DeviceUpgrader

class NewDeviceUpgrader(DeviceUpgrader):
    def __init__(self, device_ip: str, username: str = "admin", password: str = "admin"):
        super().__init__(device_ip, username, password)
    
    # Implement required methods...
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is provided as-is, without any warranty. Always backup your device configuration before performing firmware upgrades. The authors are not responsible for any damage that may occur during the upgrade process. 

# ADTRAN Firmware Upgrader

A Python utility for upgrading firmware on ADTRAN devices via SSH.

## Features

- Automated firmware upgrade process
- SSH-based device communication
- Progress monitoring
- Automatic IP detection and connection
- WiFi configuration retrieval

## Prerequisites

- Python 3.9 or higher
- pip (Python package installer)
- SSH access to the ADTRAN device

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/adtranfirmwareupgrader.git
cd adtranfirmwareupgrader
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root with your device credentials:
```bash
# SSH Credentials for ADTRAN Device
INITIAL_USERNAME=admin
INITIAL_PASSWORD=admin
UPGRADED_USERNAME=support
UPGRADED_PASSWORD=your_password
```

## Usage

1. Place your firmware image file in the project directory
2. Run the script:
```bash
python adtranfirmwareupgrader.py
```
3. Follow the on-screen instructions to complete the upgrade process

## Security Notes

- The `.env` file contains sensitive credentials and should never be committed to version control
- Make sure to use strong passwords for your device
- Keep your firmware files secure and verify their integrity before use

## License

[Your chosen license]

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 
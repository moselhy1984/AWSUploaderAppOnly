# AWS File Uploader Application

A secure, device-bound file upload application for AWS S3 with MySQL database integration.

## Features

- Secure file uploads to AWS S3
- Device-specific encryption and binding
- MySQL database integration
- Cross-platform support (Windows, macOS, Linux)
- Modern PyQt5-based GUI
- Task management with device-specific filtering

## Prerequisites

- Python 3.8 or higher
- MySQL Server
- AWS Account with S3 access
- Virtual environment (recommended)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd AWSUploaderAppOnly
```

2. Create and activate a virtual environment:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Device-Specific Setup

1. Run the configuration tool:
```bash
python Create_ConfigKey.py
```

2. Enter your AWS credentials and MySQL database details
3. The tool will generate device-specific encryption files
4. DO NOT share these files between devices

## Database Setup

1. Create the required tables:
```sql
CREATE TABLE devices (
    DeviceID INT AUTO_INCREMENT PRIMARY KEY,
    MAC_Address VARCHAR(17) UNIQUE,
    DeviceName VARCHAR(100),
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE upload_tasks (
    TaskID INT AUTO_INCREMENT PRIMARY KEY,
    FileName VARCHAR(255),
    FilePath VARCHAR(512),
    Status ENUM('pending', 'completed', 'failed'),
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CompletedTimestamp TIMESTAMP NULL,
    DeviceID INT,
    FOREIGN KEY (DeviceID) REFERENCES devices(DeviceID)
);
```

## Running the Application

1. Ensure your virtual environment is activated
2. Run the main application:
```bash
python main.py
```

## Building Executable

To create a single executable file:

```bash
pyinstaller --onefile --hidden-import=getmac --icon=icon.ico main.py
```

The executable will be created in the `dist` directory.

## Security Notes

- Each device must generate its own encryption files
- Never share encryption files between devices
- Keep your AWS credentials secure
- Regularly backup your database

## Troubleshooting

1. If you get a "MAC address mismatch" error:
   - Ensure you're running the application on the same device where you generated the config
   - Generate new config files if needed

2. If the application fails to start:
   - Check if all dependencies are installed
   - Verify database connection
   - Ensure AWS credentials are correct

## Support

For issues and support, please contact the development team.

## License

[Your License Here] 
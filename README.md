# Local File Sharing Server

A simple Flask-based file sharing server for local network use.

## Setup

1. Install Python 3.x if you haven't already
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

1. Start the server:
   ```bash
   python app.py
   ```
2. Access the web interface:
   - Local access: http://localhost:5000
   - Network access: http://[your-local-ip]:5000

## Features

- File upload through web interface
- File download through web interface
- Bootstrap-styled UI
- 50GB file size limit
- Files stored in `uploads` directory

## Security Notes

- This server is intended for local network use only
- No authentication is implemented by default
- Use with trusted networks only 
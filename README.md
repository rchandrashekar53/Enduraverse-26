# MagicalEye AI Inspection System

An advanced AI-powered visual inspection system for manufacturing quality control, built with Flask, YOLO, and Supabase.

## Features

- **Real-time Defect Detection**: Uses YOLO AI model for automated defect identification
- **ESP32-CAM Integration**: Live video streaming from industrial cameras
- **Cloud Database**: Supabase integration for data persistence and analytics
- **QR Code Traceability**: Generate QR codes for each inspected part
- **Trend Analysis**: Monitor defect rates and predict maintenance needs
- **Alert System**: Automatic notifications for quality issues
- **Web Dashboard**: Responsive interface with analytics and monitoring

## Tech Stack

- **Backend**: Python Flask
- **AI Model**: YOLO (Ultralytics)
- **Database**: SQLite (local) + Supabase (cloud)
- **Frontend**: HTML/CSS/JavaScript with Bootstrap
- **Hardware**: ESP32-CAM for video streaming

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd testing-finale
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   - Copy model files to `magicaleye/` directory
   - Update ESP32 IP address in `app.py`
   - Add Supabase credentials (see Security section)

5. **Run the application**
   ```bash
   python magicaleye/app.py
   ```

## Project Structure

```
testing-finale/
├── magicaleye/              # Main Flask application
│   ├── app.py              # Main application file
│   ├── templates/          # HTML templates
│   ├── static/             # CSS, JS, images
│   ├── best.tflite         # TensorFlow Lite model (gitignored)
│   └── inspections.db      # Local database (gitignored)
├── inference.py            # Standalone YOLO inference script
├── best.pt                 # YOLO model weights (gitignored)
├── static/                 # Additional static files
└── .gitignore             # Security-focused ignore file
```

## Security

**Important**: This project contains sensitive information that is automatically gitignored:

- API keys and credentials
- Database files
- Model weights
- Log files
- Personal configuration

Never commit these files to version control. The `.gitignore` file is configured to automatically exclude them.

## Usage

1. **Start the Flask server**
2. **Access the dashboard** at `http://localhost:5000`
3. **Configure ESP32-CAM** with the correct IP address
4. **Upload model files** to the appropriate directories
5. **Monitor inspections** through the web interface

## API Endpoints

- `GET /` - Main dashboard
- `GET /monitor` - Live monitoring
- `GET /analytics` - Analytics dashboard
- `GET /alerts` - Alert management
- `GET /log` - System logs
- `GET /api/stats` - JSON API for statistics

## Development

- **Environment**: Python 3.8+
- **Dependencies**: See `requirements.txt`
- **Database**: SQLite for local development, Supabase for production
- **Models**: YOLOv8 for object detection

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

Proprietary - Endurance Complete Solutions

## Contact

For support or questions, contact the development team.
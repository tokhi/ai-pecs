# SLI Telemetry Extraction Service

This directory contains the Python service that asynchronously processes raw telemetry traces from the Langfuse database and extracts platform-level SLIs.

## Local Setup

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate 
   ```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Run the parser against the sample JSON file:**
```bash
python service.py
```

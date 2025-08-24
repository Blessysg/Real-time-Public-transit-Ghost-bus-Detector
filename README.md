# Real-time-Public-transit-Ghost-bus-Detector
Problem Statement: To develop a real-time analytics system that identifies "ghost buses" in a public transit network—vehicles that appear on tracking apps but are not in service, are non-responsive, or are severely off-route—to provide riders with a more accurate and reliable view of the transit system.

# Open a terminal in the correct folder
In VS Code: Terminal → New Terminal.
Check the blue terminal path says ...\ghost-bus-detector\ (root of the project).
If not, type (copy-paste is okay):
  cd .\ghost-bus-detector\
  
Then go into backend:
  cd .\backend\

Create a virtual environment
  python -m venv .venv

Activate it (PowerShell)
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1

Install the packages
  python -m pip install -r requirements.txt

Run the API locally
  python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# How to test it
Open your browser and go to: http://localhost:8000/health → you should see:
  {"status":"ok"}

Also check the automatic API docs at: http://localhost:8000/docs


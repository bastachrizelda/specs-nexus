import sys
import os

# Get the directory where this script is located (specs-nexus-main)
script_dir = os.path.dirname(os.path.abspath(__file__))

# Add the script directory to Python path so 'app' module can be found
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Change to the script directory to ensure relative imports work
os.chdir(script_dir)

# Now import uvicorn and the app
import uvicorn

if __name__ == "__main__":
    # Use string format for app to work with reload
    # This tells uvicorn to import app.main:app from the current directory
    uvicorn.run(
        "app.main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        reload_dirs=[script_dir],
        reload_includes=["*.py"]
    )

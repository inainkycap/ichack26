# ichack26

## Venv instructions
### 1. Go to the backend folder
cd backend

### 2. Create a virtual environment
python -m venv venv

### 3. Activate the virtual environment
### macOS / Linux
source venv/bin/activate
### Windows (PowerShell)
venv\Scripts\Activate.ps1

### 4. Install dependencies
pip install -r requirements.txt

### 5. Run the backend server
uvicorn main:app --reload
# run.py
import uvicorn
import os

if __name__ == "__main__":
    # Создаем директории если их нет
    os.makedirs("data/input", exist_ok=True)
    os.makedirs("data/output", exist_ok=True)
    
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

# run.py
if __name__ == "__main__":
    import uvicorn
    # Было: host="0.0.0.0"
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
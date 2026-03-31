if __name__ == "__main__":
    import uvicorn
    # Передаём строку импорта как рекомендует uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
    # reload=True удобно при разработке, но необязательно здесь
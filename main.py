from fastapi import FastAPI

app = FastAPI(title="CRM")

@app.get("/health")
def health():
    return {"status": "ok"}
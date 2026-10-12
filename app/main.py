from fastapi import FastAPI

app = FastAPI(title="Pitchr AI")


@app.get("/health")
def health():
    return {"status": "ok"}

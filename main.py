import os

import uvicorn


def run():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    uvicorn.run("fastapi_backend:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()

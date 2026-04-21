import uvicorn
from gateway.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "gateway.server:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )

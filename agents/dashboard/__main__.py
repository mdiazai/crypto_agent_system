import uvicorn
from shared.utils import configure_logging

configure_logging()

if __name__ == "__main__":
    uvicorn.run(
        "agents.dashboard.dashboard_agent:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info",
        access_log=True,
    )

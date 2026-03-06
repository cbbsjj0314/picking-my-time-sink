"""FastAPI application entrypoint."""

from fastapi import FastAPI

from api.routers.games import router as games_router

app = FastAPI(title="Steam CCU API", version="0.1.0")
app.include_router(games_router)

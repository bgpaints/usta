"""Точка входа сервера Usta.  Запуск:  uvicorn app.main:app --reload"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  — регистрирует таблицы
from .api import admin, auth, master
from .config import settings
from .db import Base, engine

logging.basicConfig(level=logging.INFO)


def create_app(create_tables: bool = True) -> FastAPI:
    if not settings.debug and (settings.jwt_secret == "dev-only-change-me" or len(settings.jwt_secret) < 32):
        raise RuntimeError("На сервере задайте JWT_SECRET длиной от 32 символов")
    app = FastAPI(title="Usta by Bekmetov — API", version="0.1.0")
    # Адреса mini-app и админки добавим, когда будут домены
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(auth.router)
    app.include_router(master.router)
    app.include_router(admin.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    if create_tables:
        Base.metadata.create_all(engine)
    return app


app = create_app()

"""FastAPI application for the distilled command parser."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from service.runtime import ModelRuntime, Settings
from service.schema import InvalidModelOutput, validated_output


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


def create_app(
    runtime: ModelRuntime | None = None,
    settings: Settings | None = None,
    start_loader: bool = True,
) -> FastAPI:
    application = FastAPI(title="Command Parser", docs_url=None, redoc_url=None)
    model_runtime = runtime or ModelRuntime()
    configured_settings = settings

    async def load_model() -> None:
        nonlocal configured_settings
        try:
            configured_settings = configured_settings or Settings.from_environment()
            await asyncio.to_thread(model_runtime.load, configured_settings)
        except Exception as error:
            model_runtime.load_error = str(error)

    if start_loader:
        @application.on_event("startup")
        async def schedule_model_load() -> None:
            asyncio.create_task(load_model())

    @application.get("/healthz")
    async def healthz():
        return JSONResponse(status_code=200, content={"status": "alive"})

    @application.get("/readyz")
    async def readyz():
        if model_runtime.ready:
            return JSONResponse(status_code=200, content={"status": "ready"})
        return JSONResponse(status_code=503, content={"status": "not_ready"})

    @application.post("/parse")
    async def parse(request: ParseRequest):
        if not model_runtime.ready or configured_settings is None:
            return JSONResponse(status_code=503, content={"error": "model_not_ready"})
        raw = await asyncio.to_thread(
            model_runtime.generate,
            request.text,
            configured_settings.max_new_tokens,
        )
        if configured_settings.fault_inject:
            raw = "not json"
        try:
            output = validated_output(raw)
        except InvalidModelOutput:
            return JSONResponse(
                status_code=500, content={"error": "invalid_model_output"}
            )
        return JSONResponse(
            status_code=200,
            content=output,
            headers={
                "X-Model-Version": configured_settings.model_version,
                "X-Served-By": os.environ.get("HOSTNAME", "unknown"),
            },
        )

    return application


app = create_app()


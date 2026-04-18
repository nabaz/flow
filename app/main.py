from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as routes_router
from app.api.alerts import router as alerts_router
from app.api.system import router as system_router

app = FastAPI(title="Alert Routing Engine")


@app.get("/")
async def root():
    return {"status": "ok", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(routes_router)
app.include_router(alerts_router)
app.include_router(system_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = first.get("loc", ())
    field = ".".join(str(p) for p in loc if p != "body")
    msg = first.get("msg", "invalid request")
    error_msg = f"{field}: {msg}" if field else msg
    return JSONResponse(status_code=400, content={"error": error_msg})

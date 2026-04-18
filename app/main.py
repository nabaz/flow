from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as routes_router
from app.api.alerts import router as alerts_router
from app.api.system import router as system_router

app = FastAPI()

app.include_router(routes_router)
app.include_router(alerts_router)
app.include_router(system_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    msg = first.get("msg", "invalid request")
    return JSONResponse(status_code=400, content={"error": msg})

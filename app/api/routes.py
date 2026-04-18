from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import RouteInput
from app.store import store

router = APIRouter()


@router.post("/routes", status_code=201)
async def create_route(route: RouteInput):
    created = route.id not in store.routes
    store.routes[route.id] = route
    return {"id": route.id, "created": created}


@router.get("/routes")
async def list_routes():
    return {"routes": [r.model_dump(exclude_none=True) for r in store.routes.values()]}


@router.get("/routes/{route_id}")
async def get_route(route_id: str):
    if route_id not in store.routes:
        return JSONResponse(status_code=404, content={"error": "route not found"})
    return store.routes[route_id].model_dump(exclude_none=True)


@router.delete("/routes/{route_id}")
async def delete_route(route_id: str):
    if route_id not in store.routes:
        return JSONResponse(status_code=404, content={"error": "route not found"})
    del store.routes[route_id]
    return {"id": route_id, "deleted": True}

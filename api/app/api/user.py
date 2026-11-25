from typing import Annotated, Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from .. import appdb

router = APIRouter(prefix="/api")
DeviceId = Annotated[str, Header(alias="X-Device-Id", min_length=8, max_length=64)]
DEFAULT_AVISOS = {"retraso": True, "cancelacion": True, "anden": True, "salida": True}


class FavoriteIn(BaseModel):
    tipo: Literal["tren", "estacion"]
    ref: str = Field(min_length=1, max_length=32)
    avisos: dict[str, bool] = {}


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10)
    keys: dict[str, str]


@router.get("/favorites")
def list_favorites(request: Request, device_id: DeviceId):
    favs = appdb.list_favorites(request.app.state.st.app_db, device_id)
    return [{"tipo": f["tipo"], "ref": f["ref"], "avisos": f["avisos"]} for f in favs]


@router.put("/favorites")
def put_favorite(fav: FavoriteIn, request: Request, device_id: DeviceId):
    avisos = {**DEFAULT_AVISOS, **{k: v for k, v in fav.avisos.items() if k in DEFAULT_AVISOS}}
    appdb.put_favorite(request.app.state.st.app_db, device_id, fav.tipo, fav.ref, avisos)
    return {"ok": True}


@router.delete("/favorites")
def delete_favorite(tipo: Literal["tren", "estacion"], ref: str, request: Request, device_id: DeviceId):
    appdb.delete_favorite(request.app.state.st.app_db, device_id, tipo, ref)
    return {"ok": True}


@router.get("/push/vapid-public-key")
def vapid_public_key(request: Request):
    return {"key": request.app.state.st.settings.vapid_public_key}


@router.post("/push/subscription")
def subscribe(sub: SubscriptionIn, request: Request, device_id: DeviceId):
    appdb.put_subscription(request.app.state.st.app_db, device_id, sub.model_dump())
    return {"ok": True}


@router.delete("/push/subscription")
def unsubscribe(request: Request, device_id: DeviceId):
    appdb.delete_subscription(request.app.state.st.app_db, device_id)
    return {"ok": True}

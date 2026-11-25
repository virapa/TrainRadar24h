import os
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    st = request.app.state.st
    return {"version": os.environ.get("APP_VERSION", "dev"), "trenes": len(st.snapshot.trains), "feeds": st.snapshot.feeds,
            "generado": st.snapshot.generated_at, "gtfs_cargado": st.repo.loaded_at()}


@router.get("/trains")
def trains(request: Request, response: Response):
    snap = request.app.state.st.snapshot
    etag = f'"{snap.etag}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return {"trenes": [t.light() for t in snap.trains.values()], "feeds": snap.feeds,
            "generado": snap.generated_at}


@router.get("/trains/{train_id}")
def train_detail(train_id: str, request: Request):
    st = request.app.state.st
    train = st.snapshot.trains.get(train_id)
    if not train:
        raise HTTPException(404, "Tren no encontrado")
    shape = st.repo.shape(train.shape_id) if train.shape_id else []
    if not shape:
        shape = [[p["lon"], p["lat"]] for p in train.paradas if p["lat"] is not None]
    return {**asdict(train), "shape": shape}


@router.get("/search")
def search(q: str, request: Request):
    st = request.app.state.st
    q = q.strip()
    if len(q) < 2:
        return {"trenes": [], "estaciones": []}
    if q.isdigit():
        hits = [t.light() for t in st.snapshot.trains.values() if q in t.numero]
        return {"trenes": hits[:20], "estaciones": []}
    return {"trenes": [], "estaciones": st.repo.search_stops(q)}


# app_main.py - Minimal FastAPI backend that talks to Supabase
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os, datetime as dt
from typing import Optional, List

app = FastAPI()

# CORS for your frontends (adjust origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.get("/health")
def health():
    return {"ok": True}

# -------- FICHAJES --------
@app.post("/fichajes")
def crear_fichaje(
    user_id: str = Form(...),
    empleado: Optional[str] = Form(None),
    tipo: str = Form(...),                     # 'Entrada' | 'Salida'
    observaciones: str = Form(""),
    fuente: str = Form("movil")
):
    now = dt.datetime.now()
    now_utc = dt.datetime.utcnow()
    data = {
        "user_id": user_id,
        "empleado": empleado,
        "fecha_local": now.strftime("%Y-%m-%d %H:%M:%S"),
        "fecha_utc":   now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "tipo": tipo,
        "observaciones": observaciones,
        "fuente": fuente,
    }
    res = supabase.table("fichajes").insert(data).execute()
    if res.data is None:
        raise HTTPException(400, str(res.error) if res.error else "Insert error")
    return res.data[0]

@app.get("/fichajes")
def listar_fichajes(user_id: str, limit: int = 200):
    res = (
        supabase.table("fichajes")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at_utc", desc=True)
        .limit(limit)
        .execute()
    )
    if res.data is None:
        raise HTTPException(400, str(res.error) if res.error else "Query error")
    return res.data

# Endpoint to insert manual pair (Entrada + Salida)
@app.post("/fichajes/manual-par")
def fichaje_manual_par(
    user_id: str = Form(...),
    entrada: str = Form(...),  # 'YYYY-MM-DD HH:MM'
    salida: str  = Form(...),  # 'YYYY-MM-DD HH:MM'
    observaciones: str = Form(""),
):
    try:
        e_local = dt.datetime.strptime(entrada, "%Y-%m-%d %H:%M")
        s_local = dt.datetime.strptime(salida,  "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(400, "Formato de fecha inválido. Usa 'YYYY-MM-DD HH:MM'.")

    rows = [
        {
            "user_id": user_id,
            "empleado": None,
            "fecha_local": e_local.strftime("%Y-%m-%d %H:%M:%S"),
            "fecha_utc":   (e_local - (dt.datetime.now() - dt.datetime.utcnow())).strftime("%Y-%m-%d %H:%M:%S"),
            "tipo": "Entrada",
            "observaciones": observaciones,
            "fuente": "ajuste_movil",
        },
        {
            "user_id": user_id,
            "empleado": None,
            "fecha_local": s_local.strftime("%Y-%m-%d %H:%M:%S"),
            "fecha_utc":   (s_local - (dt.datetime.now() - dt.datetime.utcnow())).strftime("%Y-%m-%d %H:%M:%S"),
            "tipo": "Salida",
            "observaciones": observaciones,
            "fuente": "ajuste_movil",
        },
    ]
    res = supabase.table("fichajes").insert(rows).execute()
    if res.data is None:
        raise HTTPException(400, str(res.error) if res.error else "Insert error")
    return {"ok": True, "inserted": len(res.data)}

# -------- VACACIONES --------
@app.post("/vacaciones")
def crear_vacaciones(
    user_id: str = Form(...),
    fecha_inicio: str = Form(...),   # YYYY-MM-DD
    fecha_fin: str = Form(...),      # YYYY-MM-DD
    dias: int = Form(...),
    comentario: str = Form("")
):
    data = {
        "user_id": user_id,
        "usuario": None,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "dias": dias,
        "comentario": comentario,
        "estado": "Pendiente",
    }
    res = supabase.table("vacaciones").insert(data).execute()
    if res.data is None:
        raise HTTPException(400, str(res.error) if res.error else "Insert error")
    return res.data[0]

@app.get("/vacaciones")
def listar_vacaciones(user_id: str, limit: int = 100):
    res = (
        supabase.table("vacaciones")
        .select("*")
        .eq("user_id", user_id)
        .order("fecha_inicio", desc=True)
        .limit(limit)
        .execute()
    )
    if res.data is None:
        raise HTTPException(400, str(res.error) if res.error else "Query error")
    return res.data

# -------- BAJAS --------
@app.post("/bajas")
async def crear_baja(
    user_id: str = Form(...),
    tipo: str = Form(...),
    fecha_inicio: str = Form(...),    # YYYY-MM-DD
    fecha_fin: Optional[str] = Form(None),
    descripcion: str = Form(""),
    files: List[UploadFile] | None = None
):
    urls = []
    if files:
        bucket = "adjuntos"
        for f in files:
            content = await f.read()
            path = f"bajas/{user_id}/{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{f.filename}"
            up = supabase.storage.from_(bucket).upload(path, content, file_options={"content-type": f.content_type})
            if isinstance(up, dict) and up.get("error"):
                raise HTTPException(400, up["error"]["message"])
            # get public URL (adjust if you keep bucket private and sign URLs instead)
            public_url = supabase.storage.from_(bucket).get_public_url(path)
            urls.append(public_url)

    data = {
        "user_id": user_id,
        "usuario": None,
        "tipo": tipo,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "descripcion": descripcion,
        "archivos": ";".join(urls),
        "estado": "Notificada",
    }
    res = supabase.table("bajas").insert(data).execute()
    if res.data is None:
        raise HTTPException(400, str(res.error) if res.error else "Insert error")
    return res.data[0]

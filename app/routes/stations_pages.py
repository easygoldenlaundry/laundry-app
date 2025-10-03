# app/routes/stations_pages.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import station_access_dependency

router = APIRouter() # Remove the global dependency
templates = Jinja2Templates(directory="app/templates")

@router.get("/hub_intake", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("hub_intake"))])
async def get_hub_intake(request: Request):
    """Serves the hub intake scanning page."""
    return templates.TemplateResponse("hub_intake.html", {"request": request})

@router.get("/imaging", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("imaging"))])
async def get_imaging_station(request: Request):
    """Serves the imaging station page."""
    return templates.TemplateResponse("station_imaging.html", {"request": request})

@router.get("/pretreat", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("pretreat"))])
async def get_pretreat_station(request: Request):
    """Serves the pretreat station page."""
    return templates.TemplateResponse("station_pretreat.html", {"request": request})

@router.get("/washing", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("washing"))])
async def get_washing_station(request: Request):
    """Serves the washing station page."""
    return templates.TemplateResponse("station_wash.html", {"request": request})

@router.get("/drying", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("drying"))])
async def get_drying_station(request: Request):
    """Serves the drying station page."""
    return templates.TemplateResponse("station_dry.html", {"request": request})

@router.get("/folding", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("folding"))])
async def get_folding_station(request: Request):
    """Serves the folding station page."""
    return templates.TemplateResponse("station_fold.html", {"request": request})

@router.get("/qa_station", response_class=HTMLResponse, dependencies=[Depends(station_access_dependency("qa_station"))])
async def get_qa_station(request: Request):
    """Serves the QA station page."""
    return templates.TemplateResponse("station_qa.html", {"request": request})
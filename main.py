from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from auth import verify_password, create_access_token
from models import Base, Ticket, User
import requests
import shutil
from datetime import datetime, timedelta
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uuid
from parking_api import park_in_request, park_out_request
from fastapi.responses import FileResponse
Base.metadata.create_all(bind=engine)
app = FastAPI()
cors_env = os.environ.get("CORS_ORIGINS")
if cors_env:
    origins = [o.strip() for o in cors_env.split(",")]
else:
    origins = [
        "http://localhost:5173",
       
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173"] for tighter control
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOAD_FOLDER ="exit_videos/"
# Pydantic schema
class TicketCreate(BaseModel):
    token: str
    access_point_id: Optional[int]
    number: Optional[str]
    code: Optional[str]
    city: Optional[str]
    status: Optional[str]
    spot_number: Optional[int]
    trip_p_id: Optional[int]
    ticket_key_id: Optional[int]
    entry_time: Optional[datetime]
    exit_time: Optional[datetime]
    entry_pic_base64: Optional[str]
    car_pic_base64: str
    exit_video_path: Optional[str]

class TicketOut(BaseModel):
    id: int
    token: str
    access_point_id: Optional[int] = None
    number: Optional[str] = None
    code: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None
    spot_number: Optional[int] = None
    trip_p_id: Optional[int] = None
    ticket_key_id: Optional[int] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    entry_pic_base64: Optional[str] = None
    car_pic: Optional[str] = None
    exit_video_path: Optional[str] = None

    class Config:
        orm_mode = True

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def download_file(url: str, folder: str) -> str:
    os.makedirs(folder, exist_ok=True)
    local_filename = os.path.join(folder, url.split("/")[-1])
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
    return local_filename


@app.get("/tickets/", response_model=List[TicketOut])
def get_tickets(db: Session = Depends(get_db)):
    tickets = db.query(Ticket).all()
    return tickets
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=60))
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/ticket")
def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db)):
    

    db_ticket = Ticket(
        token=ticket.token,
        access_point_id=ticket.access_point_id,
        number=ticket.number,
        code=ticket.code,
        city=ticket.city,
        status=ticket.status,
        spot_number=ticket.spot_number,
        ticket_key_id=ticket.ticket_key_id,
        entry_time=ticket.entry_time or datetime.utcnow(),
        exit_time=ticket.exit_time,
        entry_pic_base64=ticket.entry_pic_base64,
        car_pic=ticket.car_pic_base64,
        exit_video_path=ticket.exit_video_path,
    )


    
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return {"id": db_ticket.id, "message": "Ticket created successfully"}

@app.get("/ticket/{id}", response_model=TicketOut)
def view_ticket(id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    return JSONResponse(content={
        "message": "Video uploaded successfully",
        "file_name": unique_filename
    })


@app.post("/submit/{ticket_id}")
def submit_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Submit a ticket by calling park-in then park-out APIs."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    parkin_resp = park_in_request(
        token=ticket.token,
        parkin_time=(ticket.entry_time or datetime.utcnow()).isoformat(),
        plate_code=ticket.code or "",
        plate_number=ticket.number or "",
        emirates=ticket.city or "",
        conf=str(ticket.ticket_key_id or ""),
        spot_number=ticket.spot_number or 0,
        pole_id=ticket.access_point_id or 0,
        images=[ticket.car_pic,ticket.entry_pic_base64] if ticket.entry_pic_base64 else [ticket.car_pic],
    )

    trip_id = None
    if isinstance(parkin_resp, dict):
        trip_id = parkin_resp.get("trip_id") or parkin_resp.get("data", {}).get("trip_id")
    if not trip_id:
        raise HTTPException(status_code=400, detail="Failed to obtain trip id")

    ticket.trip_p_id = trip_id
    ticket.status = "submitted"
    db.commit()
    db.refresh(ticket)

    parkout_resp = park_out_request(
        token=ticket.token,
        parkout_time=(ticket.exit_time or datetime.utcnow()).isoformat(),
        spot_number=ticket.spot_number or 0,
        pole_id=ticket.access_point_id or 0,
        trip_id=trip_id,
    )

    return {"park_in": parkin_resp, "park_out": parkout_resp, "ticket_id": ticket.id}

@app.get("/videos/{video_name}")
def get_exit_video(video_name: str):
    # 1. Look up the ticket in the database
    
    exit_video_path = os.path.join(UPLOAD_FOLDER,video_name)
    # print(os.path.isfile(exit_video_path))
    if os.path.isfile(exit_video_path):
        # 2. Return the file on disk
        return FileResponse(
            path=exit_video_path,
            media_type="video/mp4",            # adjust if your videos are a different format
            filename=video_name  # suggested download name
        )
    else:
        raise HTTPException(status_code=404, detail="Video not found")
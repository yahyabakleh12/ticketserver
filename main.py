from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, HttpUrl
from typing import Optional
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from auth import verify_password, create_access_token
from models import Base, Ticket,User
import requests
import shutil
from datetime import timedelta
import os
from fastapi.middleware.cors import CORSMiddleware
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
# Pydantic schema
class TicketCreate(BaseModel):
    token: str
    access_point_id: Optional[int]
    number: Optional[str]
    code: Optional[str]
    city: Optional[str]
    status: Optional[str]
    entry_time: Optional[str]
    exit_time: Optional[str]
    entry_pic_url: Optional[HttpUrl]
    car_pic_base64: str
    exit_video_url: Optional[HttpUrl]

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
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=60))
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/tickets/")
def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db)):
    entry_pic_path = None
    exit_video_path = None

    # Download entry image
    if ticket.entry_pic_url:
        try:
            entry_pic_path = download_file(ticket.entry_pic_url, "entry_images")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error downloading entry_pic: {e}")

    # Download exit video
    if ticket.exit_video_url:
        try:
            exit_video_path = download_file(ticket.exit_video_url, "exit_videos")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error downloading exit_video: {e}")

    db_ticket = Ticket(
        token=ticket.token,
        access_point_id=ticket.access_point_id,
        number=ticket.number,
        code=ticket.code,
        city=ticket.city,
        status=ticket.status,
        entry_time=ticket.entry_time,
        exit_time=ticket.exit_time,
        entry_pic_path=entry_pic_path,
        car_pic=ticket.car_pic_base64,
        exit_video_path=exit_video_path
    )


    
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return {"id": db_ticket.id, "message": "Ticket created successfully"}

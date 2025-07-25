from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, engine
from auth import verify_password, create_access_token
from models import Base, Ticket, SubmittedTicket, CancelledTicket, User
import requests
import shutil
from datetime import datetime, timedelta
import os
import base64
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uuid
from parking_api import park_in_request, park_out_request
from fastapi.responses import FileResponse
import shutil
Base.metadata.create_all(bind=engine)
app = FastAPI()
cors_env = os.environ.get("CORS_ORIGINS")
ENTRY_IMAGE_DIR = "D:/entry_images/"
CAR_IMAGE_DIR = "D:/car_images/"
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
UPLOAD_FOLDER ="D:/exit_video/"
# Pydantic schema
class TicketCreate(BaseModel):
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
    car_pic_base64: str = None
    exit_video_path: Optional[str] = None

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

def save_base64_jpg(b64_string: str, output_path: str):
    """
    Decode a base64‐encoded JPEG and save it to disk.

    :param b64_string: The JPEG data as a base64 string.
                        It may include a data URI prefix like "data:image/jpeg;base64,..."
    :param output_path: Path to write the decoded JPG, e.g. "snapshot.jpg"
    """
    # If the string has a data URI prefix, strip it out:
    if b64_string.startswith("data:image"):
        b64_string = b64_string.split(",", 1)[1]

    # Decode and write to a file
    img_data = base64.b64decode(b64_string)
    with open(output_path, "wb") as f:
        f.write(img_data)
    return output_path 

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
@app.get("/tickets/next-id")
def get_next_ticket_id(db: Session = Depends(get_db)):
    """Return the next available ticket id."""
    max_id = db.query(func.max(Ticket.id)).scalar()
    next_id = (max_id or 0) + 1
    return {"next_id": next_id}
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=60))
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/ticket")
def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db)):
    filename_in = f"{uuid.uuid4()}.jpg"
    filename_car = f"{uuid.uuid4()}.jpg"
    full_path_in = os.path.join(ENTRY_IMAGE_DIR, filename_in)
    full_path_car = os.path.join(CAR_IMAGE_DIR, filename_car)
    in_image= save_base64_jpg(ticket.entry_pic_base64,full_path_in)
    car_im = save_base64_jpg(ticket.car_pic_base64,full_path_car)
    db_ticket = Ticket(
        token=ticket.token,
        access_point_id=ticket.access_point_id,
        number=ticket.number,
        code=ticket.code,
        city=ticket.city,
        status=ticket.status,
        spot_number=ticket.spot_number,
        ticket_key_id=ticket.ticket_key_id,
        entry_time=ticket.entry_time,
        exit_time=ticket.exit_time,
        entry_pic_base64=in_image,
        car_pic=car_im,
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

@app.get("/ticket/{id}/next", response_model=TicketOut)
def get_next_ticket(id: int, db: Session = Depends(get_db)):
    """Return the next ticket with an id greater than the provided id."""
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id > id)
        .order_by(Ticket.id)
        .first()
    )
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
def submit_t(ticket_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Schedule ticket submission in the background."""
    background_tasks.add_task(submit_ticket, ticket_id, db)
    return {"status": "submission scheduled"}

def submit_ticket(ticket_id: int, db: Session):
    """Submit a ticket by calling park-in then park-out APIs."""
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        car_bs64 = ""
        in_bs64 = ""
        with open(ticket.car_pic, "rb") as f:
            car_bytes = f.read()
        car_bs64 = base64.b64encode(car_bytes).decode("utf-8")
        with open(ticket.entry_pic_base64, "rb") as d:
            in_bytes = d.read()
        in_bs64 = base64.b64encode(in_bytes).decode("utf-8")
        print(ticket.token)

        parkin_resp = park_in_request(
            token=ticket.token,
            parkin_time=(ticket.entry_time or datetime.utcnow()).isoformat(),
            plate_code=ticket.code or "",
            plate_number=ticket.number or "",
            emirates=ticket.city or "",
            conf=str(ticket.ticket_key_id or ""),
            spot_number=ticket.spot_number or 0,
            pole_id=ticket.access_point_id or 0,
            images=[car_bs64, in_bs64],
        )
        print(parkin_resp)

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

        submitted = SubmittedTicket(
            token=ticket.token,
            access_point_id=ticket.access_point_id,
            number=ticket.number,
            code=ticket.code,
            city=ticket.city,
            status="submitted",
            entry_time=ticket.entry_time,
            exit_time=ticket.exit_time,
            entry_pic_base64=ticket.entry_pic_base64,
            car_pic=ticket.car_pic,
            exit_video_path=ticket.exit_video_path,
            spot_number=ticket.spot_number,
            trip_p_id=ticket.trip_p_id,
            ticket_key_id=ticket.ticket_key_id,
        )
        db.add(submitted)
        db.delete(ticket)
        db.commit()
        db.refresh(submitted)

        return {"park_in": parkin_resp, "park_out": parkout_resp, "ticket_id": submitted.id}
    finally:
        db.close()
# @app.get("/fix")
# def fix_db(db: Session = Depends(get_db)):
#     tickets = db.query(Ticket).filter(Ticket.token == 'buOs11IDXwseQCb3bLvAxNv0Gx4HLC21Um').all()
#     for ticket in tickets:
#         filename_in = f"{uuid.uuid4()}.jpg"
#         filename_car = f"{uuid.uuid4()}.jpg"
#         full_path_in = os.path.join(ENTRY_IMAGE_DIR, filename_in)
#         full_path_car = os.path.join(CAR_IMAGE_DIR, filename_car)
#         ticket_d = db.query(Ticket).filter(Ticket.id == ticket.id).first()
#         if not ticket:
#             continue
#         src_car = ticket.car_pic
#         src_in = ticket.entry_pic_base64

#         # destination path (including filename)
#         dst_car = full_path_car
#         dst_in = full_path_in
#         # this will move (and rename if needed) the file
#         shutil.move(src_car, dst_in)
#         shutil.move(src_in, dst_car)
#         ticket_d.entry_pic_base64 = full_path_in
#         ticket_d.car_pic = full_path_car
#         db.commit()
#         db.refresh(ticket)
#         print("Done")
#     print("all images are cleare")

@app.post("/ticket/{id}/cancel", response_model=TicketOut)
def cancel_ticket(id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    cancelled = CancelledTicket(
        token=ticket.token,
        access_point_id=ticket.access_point_id,
        number=ticket.number,
        code=ticket.code,
        city=ticket.city,
        status="cancelled",
        entry_time=ticket.entry_time,
        exit_time=ticket.exit_time,
        entry_pic_base64=ticket.entry_pic_base64,
        car_pic=ticket.car_pic,
        exit_video_path=ticket.exit_video_path,
        spot_number=ticket.spot_number,
        trip_p_id=ticket.trip_p_id,
        ticket_key_id=ticket.ticket_key_id,
    )
    db.add(cancelled)
    db.delete(ticket)
    db.commit()
    db.refresh(cancelled)
    return cancelled

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

@app.get("/image-car/{id}")
def get_image(id: str,db: Session = Depends(get_db)):
    # 1. Look up the ticket in the database
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if os.path.isfile(ticket.car_pic):
        # 2. Return the file on disk
        return FileResponse(
            path=ticket.car_pic,
            media_type="image/jpg",            # adjust if your videos are a different format
            filename=ticket.car_pic  # suggested download name
        )
    else:
    
        raise HTTPException(status_code=404, detail="Video not found")
@app.get("/image-in/{id}")
def get_image(id: str,db: Session = Depends(get_db)):
    # 1. Look up the ticket in the database
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if os.path.isfile(ticket.entry_pic_base64):
        # 2. Return the file on disk
        return FileResponse(
            path=ticket.entry_pic_base64,
            media_type="image/jpg",            # adjust if your videos are a different format
            filename=ticket.entry_pic_base64  # suggested download name
        )
    else:
    
        raise HTTPException(status_code=404, detail="Video not found")
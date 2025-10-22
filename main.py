from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, engine
from auth import verify_password, create_access_token
from models import Base, Ticket, SubmittedTicket, CancelledTicket, User
import requests
import shutil
from datetime import datetime, timedelta
import os
import re
import base64
import json
import aiofiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
import uuid
from parking_api import park_in_request, park_out_request
from fastapi.responses import FileResponse
from convert_video import make_browser_friendly


WINDOWS_ABS_PATH_PATTERN = re.compile(r"^[A-Za-z]:[/\\]")


def _normalize_directory(path: str) -> str:
    """Return a normalized directory path for consistent joins."""

    expanded = os.path.expanduser(path)
    return os.path.normpath(expanded)


def _resolve_relative_path(path: Optional[str], base_dir: str) -> Optional[str]:
    """Resolve *path* against *base_dir* when it is not absolute."""

    if not path:
        return path
    if os.path.isabs(path) or WINDOWS_ABS_PATH_PATTERN.match(path):
        return os.path.normpath(path)

    normalized = path.replace("\\", "/").lstrip("/")
    base_name = os.path.basename(os.path.normpath(base_dir))
    if base_name:
        lowered = normalized.lower()
        prefix = f"{base_name.lower()}/"
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix) :]

    if not normalized:
        return os.path.normpath(base_dir)

    return os.path.normpath(os.path.join(base_dir, normalized))


ENTRY_IMAGE_DIR = _normalize_directory(os.environ.get("ENTRY_IMAGE_DIR", "D:/entry_images"))
CAR_IMAGE_DIR = _normalize_directory(os.environ.get("CAR_IMAGE_DIR", "D:/car_images"))
UPLOAD_FOLDER = _normalize_directory(os.environ.get("EXIT_VIDEO_DIR", "D:/exit_video"))
CONFIG_PATH = os.environ.get("TICKETSERVER_CONFIG_PATH")

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


def success_response(message: str, identifier, **extra) -> JSONResponse:
    """Return a unified success response with status code 200."""
    payload = {"message": message, "id": identifier}
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))

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

    model_config = ConfigDict(from_attributes=True)

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
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
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

async def load_runtime_config() -> None:
    """Load optional directory configuration from a JSON file."""

    global ENTRY_IMAGE_DIR, CAR_IMAGE_DIR, UPLOAD_FOLDER

    if not CONFIG_PATH:
        return

    try:
        async with aiofiles.open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            raw_config = await config_file.read()
    except FileNotFoundError:
        print(f"Config file {CONFIG_PATH} not found; using default directories.")
        return
    except OSError as exc:
        print(f"Failed to open config file {CONFIG_PATH}: {exc}")
        return

    try:
        data = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in config file {CONFIG_PATH}: {exc}")
        return

    entry_dir = data.get("entry_image_dir")
    car_dir = data.get("car_image_dir")
    exit_dir = data.get("exit_video_dir")

    if entry_dir:
        ENTRY_IMAGE_DIR = _normalize_directory(entry_dir)
    if car_dir:
        CAR_IMAGE_DIR = _normalize_directory(car_dir)
    if exit_dir:
        UPLOAD_FOLDER = _normalize_directory(exit_dir)


def normalize_path_car(path: str) -> str:
    normalized = _resolve_relative_path(path, CAR_IMAGE_DIR)
    return normalized if normalized is not None else path


def normalize_video_path(path: str) -> str:
    normalized = _resolve_relative_path(path, UPLOAD_FOLDER)
    return normalized if normalized is not None else path


def is_video_file(path: str) -> bool:
    """Return True if the given path has a video file extension."""
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    return os.path.splitext(path)[1].lower() in video_exts


def submit_previous_day_tickets() -> None:
    """Submit all tickets from the previous day with duration under one hour."""
    start_prev = datetime.combine(datetime.now().date() - timedelta(days=1), datetime.min.time())
    end_prev = start_prev + timedelta(days=1)
    db = SessionLocal()
    try:
        tickets = (
            db.query(Ticket)
            .filter(
                Ticket.entry_time >= start_prev,
                Ticket.entry_time < end_prev,
                Ticket.exit_time != None,
            )
            .all()
        )
    finally:
        db.close()

    ids_to_submit = [
        t.id
        for t in tickets
        if t.entry_time and t.exit_time and t.exit_time - t.entry_time < timedelta(hours=1)
    ]

    for tid in ids_to_submit:
        submit_ticket(tid, SessionLocal())


async def schedule_midnight_submission() -> None:
    """Run submission task every midnight."""
    while True:
        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_midnight - now).total_seconds())
        submit_previous_day_tickets()


@app.on_event("startup")
async def start_scheduler() -> None:
    await load_runtime_config()
    asyncio.create_task(schedule_midnight_submission())

@app.get("/tickets/", response_model=List[TicketOut])
def get_tickets(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    offset = (page - 1) * page_size
    tickets = (
        db.query(Ticket)
        .filter(Ticket.entry_time>"2025-07-28 23:59:59")
        .order_by(Ticket.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return tickets
@app.get("/tickets/next-id")
def get_next_ticket_id(db: Session = Depends(get_db)):
    """Return the next available ticket id."""
    max_id = db.query(func.max(Ticket.id)).scalar()
    next_id = (max_id or 0) + 1
    return {"next_id": next_id}

@app.get("/submittedtickets/", response_model=List[TicketOut])
def get_submitted_tickets(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    offset = (page - 1) * page_size
    tickets = (
        db.query(SubmittedTicket)
        .order_by(SubmittedTicket.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return tickets

@app.get("/cancelledtickets/", response_model=List[TicketOut])
def get_cancelled_tickets(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    offset = (page - 1) * page_size
    tickets = (
        db.query(CancelledTicket)
        .order_by(CancelledTicket.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return tickets
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=60))
    return {"access_token": access_token, "token_type": "bearer"}


def clean_plate(p: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (p or "").upper())

def plate_similarity_strict(p1: str, p2: str) -> float:
    p1, p2 = clean_plate(p1), clean_plate(p2)
    n = min(len(p1), len(p2))
    if n == 0:
        return 0.0
    matches = sum(1 for i in range(n) if p1[i] == p2[i])
    return matches / max(len(p1), len(p2))


@app.post("/ticket")
def create_ticket(ticket: TicketCreate, db: Session = Depends(get_db)):
    ref_time = ticket.entry_time or ticket.exit_time or datetime.now()
    day_start = ref_time.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    # time_threshold = max(ref_time - timedelta(hours=2), day_start)

    existing = (
        db.query(Ticket)
        .filter(
            Ticket.spot_number == ticket.spot_number,
            Ticket.access_point_id == ticket.access_point_id,
            Ticket.number == ticket.number,
            # Ticket.code == ticket.code,
            # Ticket.entry_time >= time_threshold,
            Ticket.entry_time < day_end,
        )
        .order_by(Ticket.entry_time.desc())
        .first()
    )

    # if existing and existing.exit_time and ticket.entry_time:
    #     time_diff = ticket.entry_time - existing.exit_time
    #     if time_diff > timedelta(hours=2):
    #         existing = None

    if existing:
        latest = (
            db.query(Ticket)
            .filter(
                Ticket.spot_number == ticket.spot_number,
                Ticket.access_point_id == ticket.access_point_id,
                # Ticket.entry_time >= time_threshold,
                Ticket.entry_time < day_end,
            )
            .order_by(Ticket.entry_time.desc())
            .first()
        )
        if latest and latest.id == existing.id:
            if ticket.exit_time:
                existing.exit_time = ticket.exit_time
            if ticket.exit_video_path:
                normalized_video = normalize_video_path(ticket.exit_video_path)
                if is_video_file(normalized_video) and "_bf" not in os.path.splitext(normalized_video)[0]:
                    try:
                        converted = make_browser_friendly(normalized_video)
                        existing.exit_video_path = os.path.basename(converted)
                    except Exception as exc:
                        print(f"Failed to convert {ticket.exit_video_path}: {exc}")
                else:
                    existing.exit_video_path = os.path.basename(normalized_video)
            db.commit()
            db.refresh(existing)
            print("Ticket exit time updated")
            return success_response("Ticket exit time updated", existing.id)

    
    # // ADD BY MHD
    last_car = (
        db.query(Ticket)
        .filter(
            Ticket.spot_number == ticket.spot_number,
            Ticket.access_point_id == ticket.access_point_id,
        )
        .order_by(Ticket.id.desc())
        .first()
    )

    print("New car detected:")
    print(f"  Spot: {ticket.spot_number}, Access Point: {ticket.access_point_id}")
    print(f"  Plate: {ticket.code} {ticket.number}")

    if last_car:
        print(f"  Last car in this spot: {last_car.code} {last_car.number}")

        new_plate_full = f"{ticket.code}-{ticket.number}".upper()
        old_plate_full = f"{last_car.code}-{last_car.number}".upper()

        similarity = plate_similarity_strict(new_plate_full, old_plate_full)
        print(f"[PLATE CHECK] new={new_plate_full}, last={old_plate_full}, similarity={similarity:.2f}")

        # ✅ If similar → update last ticket instead of creating new one
        if similarity >= 0.6:
            print(f"[DUPLICATE] Similar plate detected ({similarity:.2f}) → updating last ticket #{last_car.id}")

            # Update exit time if provided
            if ticket.exit_time:
                last_car.exit_time = ticket.exit_time

            # Update exit video if provided
            if ticket.exit_video_path:
                normalized_video = normalize_video_path(ticket.exit_video_path)
                if is_video_file(normalized_video) and "_bf" not in os.path.splitext(normalized_video)[0]:
                    try:
                        converted = make_browser_friendly(normalized_video)
                        last_car.exit_video_path = os.path.basename(converted)
                        print(f"Exit video converted and updated for ticket #{last_car.id}")
                    except Exception as exc:
                        print(f"Failed to convert {ticket.exit_video_path}: {exc}")
                else:
                    last_car.exit_video_path = os.path.basename(normalized_video)
                    print(f"Exit video updated for ticket #{last_car.id}")

            # Commit database changes
            db.commit()
            db.refresh(last_car)
            print(f"Ticket #{last_car.id} updated successfully (exit time/video).")
            return success_response("Similar plate detected → Ticket updated", last_car.id)

        else:
            print(f"[INFO] Different plate detected ({similarity:.2f}) → new car, creating new ticket.")
    else:
        print("No previous car found for this spot.")

    #!//////////////

    filename_in = f"{uuid.uuid4()}.jpg"
    filename_car = f"{uuid.uuid4()}.jpg"
    full_path_in = os.path.join(ENTRY_IMAGE_DIR, filename_in)
    full_path_car = os.path.join(CAR_IMAGE_DIR, filename_car)
    in_image = save_base64_jpg(ticket.entry_pic_base64, full_path_in)
    car_im = save_base64_jpg(ticket.car_pic_base64, full_path_car)

    exit_video_filename = ticket.exit_video_path
    if ticket.exit_video_path:
        normalized_video = normalize_video_path(ticket.exit_video_path)
        if is_video_file(normalized_video) and "_bf" not in os.path.splitext(normalized_video)[0]:
            try:
                converted = make_browser_friendly(normalized_video)
                exit_video_filename = os.path.basename(converted)
            except Exception as exc:
                print(f"Failed to convert {ticket.exit_video_path}: {exc}")
        else:
            exit_video_filename = os.path.basename(normalized_video)

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
        exit_video_path=exit_video_filename,
    )

    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    print('Ticket created successfully')
    return success_response("Ticket created successfully", db_ticket.id)

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
        .filter(Ticket.entry_time>"2025-07-28 23:59:59")
        .filter(Ticket.id > id)
        .order_by(Ticket.id)
        .first()
    )
    if not ticket:
         ticket = (
        db.query(Ticket)
        .filter(Ticket.entry_time>"2025-07-28 23:59:59")
        .order_by(Ticket.id)
        .first()
    )
    return ticket
@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    response_name = unique_filename
    if is_video_file(file_path) and "_bf" not in os.path.splitext(file_path)[0]:
        try:
            converted = make_browser_friendly(file_path)
            response_name = os.path.basename(converted)
        except Exception as exc:
            print(f"Failed to convert {file_path}: {exc}")

    return success_response("File uploaded successfully", response_name, file_name=response_name)


@app.post("/submit/{ticket_id}")
def submit_t(ticket_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Schedule ticket submission in the background."""
    background_tasks.add_task(submit_ticket, ticket_id, db)
    return success_response("Submission scheduled", ticket_id)


@app.post("/submit-under-hour")
def submit_short_tickets(db: Session = Depends(get_db)):
    """Submit all tickets with duration under one hour."""
    tickets = db.query(Ticket).filter(Ticket.exit_time != None).all()
    ids_to_submit = []

    for t in tickets:
        if not t.entry_time or not t.exit_time:
            continue

        duration = t.exit_time - t.entry_time
        print(f"Ticket {t.id} duration: {duration}")

        if timedelta(0) <= duration < timedelta(hours=1):
            ids_to_submit.append(t.id)

    for tid in ids_to_submit:
        submit_ticket(tid, SessionLocal())

    return success_response(
        "Submitted tickets under one hour",
        ids_to_submit,
        submitted=len(ids_to_submit),
    )

def submit_ticket(ticket_id: int, db: Session):
    """Submit a ticket by calling park-in then park-out APIs."""
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        car_bs64 = ""
        in_bs64 = ""
        normalized_path_car=normalize_path_car(ticket.car_pic)
        with open(normalized_path_car, "rb") as f:
            car_bytes = f.read()
        car_bs64 = base64.b64encode(car_bytes).decode("utf-8")
        normalized_path=normalize_path(ticket.entry_pic_base64)
        with open(normalized_path, "rb") as d:
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
            entry_pic_base64=normalized_path,
            car_pic=normalized_path_car,
            exit_video_path=ticket.exit_video_path,
            spot_number=ticket.spot_number,
            trip_p_id=ticket.trip_p_id,
            ticket_key_id=ticket.ticket_key_id,
        )
        db.add(submitted)
        db.delete(ticket)
        db.commit()
        db.refresh(submitted)

        return success_response(
            "Ticket submitted successfully",
            submitted.id,
            park_in=parkin_resp,
            park_out=parkout_resp,
        )
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
    ticket_payload = TicketOut.from_orm(cancelled).dict()
    return success_response("Ticket cancelled successfully", cancelled.id, ticket=ticket_payload)


def merge_duplicate_tickets(db: Session) -> dict:
    """Merge tickets with identical plate and location info on the same day.

    For each set of tickets sharing plate number, code, city, spot number and
    access point within the same calendar day, keep the earliest entry record.
    The earliest ticket's ``exit_time`` is updated to the latest ``exit_time``
    seen in the set. All other tickets are moved to ``CancelledTicket`` and
    removed from ``Ticket``.

    :param db: Active database session.
    :return: Summary with number of merged groups.
    """

    tickets = db.query(Ticket).order_by(Ticket.entry_time).all()
    groups: dict[tuple, list[Ticket]] = {}
    for t in tickets:
        if not t.entry_time:
            continue
        key = (
            t.number,
            t.code,
            t.city,
            t.spot_number,
            t.access_point_id,
            t.entry_time.date(),
        )
        groups.setdefault(key, []).append(t)

    merged_groups = 0
    for key, group in groups.items():
        if len(group) <= 1:
            continue

        group.sort(key=lambda x: x.entry_time)
        first = group[0]
        exit_times = [g.exit_time for g in group if g.exit_time]
        if exit_times:
            first.exit_time = max(exit_times)

        for duplicate in group[1:]:
            cancelled = CancelledTicket(
                token=duplicate.token,
                access_point_id=duplicate.access_point_id,
                number=duplicate.number,
                code=duplicate.code,
                city=duplicate.city,
                status="cancelled",
                entry_time=duplicate.entry_time,
                exit_time=duplicate.exit_time,
                entry_pic_base64=duplicate.entry_pic_base64,
                car_pic=duplicate.car_pic,
                exit_video_path=duplicate.exit_video_path,
                spot_number=duplicate.spot_number,
                trip_p_id=duplicate.trip_p_id,
                ticket_key_id=duplicate.ticket_key_id,
            )
            db.add(cancelled)
            db.delete(duplicate)

        merged_groups += 1

    db.commit()
    return success_response("Merged duplicate tickets", merged_groups)


@app.post("/tickets/merge-duplicates")
def merge_duplicates(db: Session = Depends(get_db)):
    """API endpoint to merge duplicate tickets."""
    return merge_duplicate_tickets(db)

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
    normalized_path_car =normalize_path_car(ticket.car_pic)
    if os.path.isfile(normalized_path_car):
        # 2. Return the file on disk
        return FileResponse(
            path=normalized_path_car,
            media_type="image/jpg",            # adjust if your videos are a different format
            filename=ticket.car_pic  # suggested download name
        )
    else:
    
        raise HTTPException(status_code=404, detail="Video not found")
def normalize_path(path: str) -> str:
    normalized = _resolve_relative_path(path, ENTRY_IMAGE_DIR)
    return normalized if normalized is not None else path

@app.get("/image-in/{id}")
def get_image(id: str,db: Session = Depends(get_db)):
    # 1. Look up the ticket in the database
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    normalized_path = normalize_path(ticket.entry_pic_base64)
    if os.path.isfile(normalized_path):
        # 2. Return the file on disk
        return FileResponse(
            path=normalized_path,
            media_type="image/jpg",            # adjust if your videos are a different format
            filename=ticket.entry_pic_base64  # suggested download name
        )
    else:
    
        raise HTTPException(status_code=404, detail="Video not found")


@app.get("/convert-video/{token}", response_model=List[TicketOut])
def convert_video(token: str, db: Session = Depends(get_db)):
    tickets = (
        db.query(Ticket)
        .filter(Ticket.token == token)
        .order_by(Ticket.id.desc())
        .all()
    )

    for ticket in tickets:
        if not ticket.exit_video_path:
            continue
        normalized = normalize_video_path(ticket.exit_video_path)
        if not is_video_file(normalized) or "_bf" in os.path.splitext(normalized)[0]:
            continue
        try:
            new_path = make_browser_friendly(normalized)
            ticket.exit_video_path = os.path.basename(new_path)
        except Exception as exc:
            print(f"Failed to convert {ticket.exit_video_path}: {exc}")

    db.commit()
    return tickets

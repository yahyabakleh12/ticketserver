from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from database import Base

class Ticket(Base):
    __tablename__ = "Ticket"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), index=True)
    access_point_id = Column(Integer)
    number = Column(String(50))
    code = Column(String(50))
    city = Column(String(100))
    status = Column(String(50))
    entry_time= Column(DateTime,   nullable=False)
    exit_time= Column(DateTime,   nullable=True)
    entry_pic_base64 = Column(String(255))
    car_pic = Column(Text)  # base64
    exit_video_path = Column(String(255))
    spot_number = Column(Integer)
    trip_p_id = Column(Integer)
    ticket_key_id = Column(Integer)


class SubmittedTicket(Base):
    __tablename__ = "SubmittedTicket"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), index=True)
    access_point_id = Column(Integer)
    number = Column(String(50))
    code = Column(String(50))
    city = Column(String(100))
    status = Column(String(50))
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=True)
    entry_pic_base64 = Column(String(255))
    car_pic = Column(Text)
    exit_video_path = Column(String(255))
    spot_number = Column(Integer)
    trip_p_id = Column(Integer)
    ticket_key_id = Column(Integer)


class CancelledTicket(Base):
    __tablename__ = "CancelledTicket"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), index=True)
    access_point_id = Column(Integer)
    number = Column(String(50))
    code = Column(String(50))
    city = Column(String(100))
    status = Column(String(50))
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=True)
    entry_pic_base64 = Column(String(255))
    car_pic = Column(Text)
    exit_video_path = Column(String(255))
    spot_number = Column(Integer)
    trip_p_id = Column(Integer)
    ticket_key_id = Column(Integer)
class User(Base):
    __tablename__ = "User"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True)
    password = Column(String(255))

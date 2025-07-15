from sqlalchemy import Column, Integer, String, DateTime, Text
from database import Base

class Ticket(Base):
    __tablename__ = "Ticket"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), unique=True, index=True)
    access_point_id = Column(Integer)
    number = Column(String(50))
    code = Column(String(50))
    city = Column(String(100))
    status = Column(String(50))
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    entry_pic_path = Column(String(255))
    car_pic = Column(Text)  # base64
    exit_video_path = Column(String(255))
class User(Base):
    __tablename__ = "User"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True)
    password = Column(String(255))
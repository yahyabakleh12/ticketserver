from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import User, Base
from auth import get_password_hash

def seed_admin():
    db: Session = SessionLocal()
    Base.metadata.create_all(bind=engine)  # make sure tables exist

    existing = db.query(User).filter(User.username == "admin").first()
    if existing:
        print("Admin user already exists.")
    else:
        hashed_pw = get_password_hash("123456789")
        admin_user = User(username="admin", password=hashed_pw)
        db.add(admin_user)
        db.commit()
        print("Admin user created with username=admin and password=123456789")

    db.close()

if __name__ == "__main__":
    seed_admin()

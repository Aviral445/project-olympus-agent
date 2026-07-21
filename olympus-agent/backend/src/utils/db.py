import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Database URL defaults to local SQLite file 'olympus.db'
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./olympus.db")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PatchLog(Base):
    __tablename__ = "patch_logs"

    id = Column(Integer, primary_key=True, index=True)
    target_file = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # PASS or FAIL
    git_diff = Column(Text, nullable=True)
    error_logs = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Initializes tables in database."""
    Base.metadata.create_all(bind=engine)
    print("🗄️ [Database]: Engine initialized and tables created successfully.")

def log_patch_run(target_file: str, attempt: int, status: str, git_diff: str = "", error_logs: str = ""):
    """Saves execution history to DB."""
    db = SessionLocal()
    try:
        log_entry = PatchLog(
            target_file=target_file,
            attempt_number=attempt,
            status=status,
            git_diff=git_diff,
            error_logs=error_logs
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        print(f"💾 [Database]: Stored log entry ID #{log_entry.id} ({status})")
        return log_entry
    finally:
        db.close()
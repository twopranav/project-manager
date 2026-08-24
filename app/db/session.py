from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings

# Load the application's database configuration from the environment.
settings = get_settings()

# Create the SQLAlchemy engine that manages connections to the configured database.
engine = create_engine(settings.DATABASE_URL)

# Create a reusable factory for database sessions that uses the engine and disables automatic commit/flush behavior.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Provide a database session to API endpoints and ensure it is closed after the request finishes.
def get_db():
    # Create a new database session for the current request.
    db = SessionLocal()
    try:
        # Yield the session to the endpoint while keeping it open for the duration of the request.
        yield db
    finally:
        # Close the session when the endpoint finishes, even if an exception occurs.
        db.close()
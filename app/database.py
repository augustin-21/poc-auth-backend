from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# SQLite async URL
DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Use async_sessionmaker (SQLAlchemy 2.x style)
AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,  # Not strictly needed in 2.x, but safe to include
)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, database_url: str) -> None:
        connect_args = (
            {"check_same_thread": False}
            if database_url.startswith("sqlite")
            else {}
        )
        self.engine: Engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        db_session = self.session_factory()
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    def dispose(self) -> None:
        self.engine.dispose()


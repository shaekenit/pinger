import argparse
import asyncio
import time
import secrets
from typing import Dict, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import Column, Integer, String, Float, Boolean, create_engine, select, update
from sqlalchemy.orm import declarative_base, sessionmaker, Session


class ServerConfig:

    DATABASE_URL = "sqlite:///./ping_db.sqlite3"
    TOKEN_EXPIRY_SECONDS = 60 * 60
    RATE_LIMIT_PER_MINUTE = 120
    CLEANUP_INTERVAL_SECONDS = 60
    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 8000


Base = declarative_base()
database_engine = create_engine(
    ServerConfig.DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True
)
DatabaseSession = sessionmaker(
    bind=database_engine,
    autoflush=False,
    autocommit=False,
    future=True
)


class SessionToken(Base):

    __tablename__ = "session_tokens"

    token = Column(String, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    expiry = Column(Float, nullable=False)


class PendingPing(Base):

    __tablename__ = "pending_pings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    to_username = Column(String, index=True, nullable=False)
    from_username = Column(String, nullable=False)
    ts = Column(Float, nullable=False)
    delivered = Column(Boolean, default=False, nullable=False)


Base.metadata.create_all(bind=database_engine)


class ConnectionManager:

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def send_connected_clients(self):
        usernames = list(self.active_connections.keys())
        for username, websocket in self.active_connections.items():
            try:
                await websocket.send_json({
                "type": "clientlist",
                "clients":usernames
                })
            except RuntimeError:
                self.disconnect(username)

    async def connect(self, websocket: WebSocket, username: str) -> None:
        await websocket.accept()
        self.active_connections[username] = websocket
        await self.send_connected_clients()


    def disconnect(self, username: str) -> None:
        self.active_connections.pop(username, None)

    def is_connected(self, username: str) -> bool:
        return username in self.active_connections

    async def send_personal_message(self, message: dict, username: str) -> bool:
        if websocket := self.active_connections.get(username):
            try:
                await websocket.send_json(message)
                return True
            except Exception:
                self.disconnect(username)
        return False


class RateLimiter:

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.user_counters: Dict[str, Dict[str, float]] = {}

    def check_rate_limit(self, username: str) -> bool:
        current_time = time.time()
        user_counter = self.user_counters.setdefault(
            username,
            {"count": 0, "window_start": current_time}
        )

        if current_time - user_counter["window_start"] > 60:
            user_counter["count"] = 1
            user_counter["window_start"] = current_time
            return True

        user_counter["count"] += 1
        return user_counter["count"] <= self.requests_per_minute

    def cleanup_old_counters(self) -> None:
        current_time = time.time()
        stale_users = [
            username for username, counter in self.user_counters.items()
            if current_time - counter.get("window_start", 0) > 3600
        ]
        for username in stale_users:
            self.user_counters.pop(username, None)


class AuthenticationService:

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def get_current_time() -> float:
        return time.time()

    @staticmethod
    def validate_token(token: str) -> Optional[str]:
        with DatabaseSession() as db_session:
            token_record = db_session.execute(
                select(SessionToken).where(SessionToken.token == token)
            ).scalars().first()

            current_time = AuthenticationService.get_current_time()

            if not token_record or token_record.expiry < current_time:
                # Clean up expired token
                if token_record:
                    db_session.query(SessionToken).filter(
                        SessionToken.token == token
                    ).delete()
                    db_session.commit()
                return None

            return token_record.username


class PingService:

    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager

    async def send_ping(self, from_username: str, to_username: str) -> dict:
        current_time = time.time()
        ping_message = {
            "type": "ping",
            "from": from_username,
            "to": to_username,
            "ts": current_time
        }

        delivered = await self.connection_manager.send_personal_message(
            ping_message, to_username
        )

        self._store_ping_record(from_username, to_username, current_time, delivered)

        if delivered:
            return {"result": "delivered", "target_online": True}
        return {"result": "queued", "target_online": False}

    def _store_ping_record(self, from_username: str, to_username: str,
                          timestamp: float, delivered: bool) -> None:
        with DatabaseSession() as db_session:
            db_session.add(PendingPing(
                to_username=to_username,
                from_username=from_username,
                ts=timestamp,
                delivered=delivered
            ))
            db_session.commit()

    async def deliver_queued_pings(self, username: str) -> None:
        with DatabaseSession() as db_session:
            pending_pings = db_session.execute(
                select(PendingPing).where(
                    PendingPing.to_username == username,
                    PendingPing.delivered == False
                ).order_by(PendingPing.id)
            ).scalars().all()

            for ping in pending_pings:
                try:
                    queued_message = {
                        "type": "queued_ping",
                        "from": ping.from_username,
                        "to": ping.to_username,
                        "ts": ping.ts,
                        "id": ping.id
                    }

                    if await self.connection_manager.send_personal_message(
                        queued_message, username
                    ):
                        db_session.execute(
                            update(PendingPing).where(
                                PendingPing.id == ping.id
                            ).values(delivered=True)
                        )
                except Exception:
                    pass

            db_session.commit()


connection_manager = ConnectionManager()
rate_limiter = RateLimiter(ServerConfig.RATE_LIMIT_PER_MINUTE)
ping_service = PingService(connection_manager)

app = FastAPI(title="Ping Middleman Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_current_user(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = auth_header.split(None, 1)[1].strip()
    username = AuthenticationService.validate_token(token)

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return username


async def perform_cleanup() -> None:
    while True:
        current_time = AuthenticationService.get_current_time()

        try:
            with DatabaseSession() as db_session:
                db_session.query(SessionToken).filter(
                    SessionToken.expiry < current_time
                ).delete(synchronize_session=False)
                db_session.commit()
        except Exception:
            pass

        rate_limiter.cleanup_old_counters()

        await asyncio.sleep(ServerConfig.CLEANUP_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(perform_cleanup())


@app.post("/login")
async def login_user(credentials: dict):
    username = credentials.get("username")
    if not username or not isinstance(username, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid username required"
        )

    token = AuthenticationService.generate_token()
    expiry_time = AuthenticationService.get_current_time() + ServerConfig.TOKEN_EXPIRY_SECONDS

    with DatabaseSession() as db_session:
        db_session.add(SessionToken(
            token=token,
            username=username,
            expiry=expiry_time
        ))
        db_session.commit()

    return {"token": token, "expires_in": ServerConfig.TOKEN_EXPIRY_SECONDS}


@app.post("/ping")
async def send_user_ping(
    ping_request: dict,
    sender_username: str = Depends(get_current_user)
):
    target_username = ping_request.get("to")
    if not target_username or not isinstance(target_username, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target username required"
        )

    if not rate_limiter.check_rate_limit(sender_username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )

    result = await ping_service.send_ping(sender_username, target_username)

    if result["result"] == "delivered":
        return result
    return JSONResponse(result, status_code=status.HTTP_202_ACCEPTED)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    username = AuthenticationService.validate_token(token)
    if not username:
        await websocket.close(code=1008)
        return

    await connection_manager.connect(websocket, username)

    try:
        await ping_service.deliver_queued_pings(username)

        while True:
            try:
                message = await websocket.receive_text()
                if message.strip().lower() == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    finally:
        connection_manager.disconnect(username)


@app.get("/clients")
async def root():
    usernames = list(connection_manager.active_connections.keys())
    return usernames

@app.get("/health")
async def health_check():
    with DatabaseSession() as db_session:
        queued_count = db_session.query(PendingPing).filter(
            PendingPing.delivered == False
        ).count()
        session_count = db_session.query(SessionToken).count()

    return {
        "status": "healthy",
        "connected_users": len(connection_manager.active_connections),
        "queued_pings": queued_count,
        "active_sessions": session_count,
    }

app.mount("/", StaticFiles(directory="static", html=True), name="static")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Middleman Server")
    parser.add_argument("--dev", action="store_true", help="Run in development mode")
    parser.add_argument("--host", default=ServerConfig.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=ServerConfig.DEFAULT_PORT)
    return parser.parse_args()


#if __name__ == "__main__":
    #args = parse_arguments()
    #import uvicorn
    #uvicorn.run(
    #    "server:app",
    #    host=args.host,
    #    port=args.port,
    #    reload=args.dev
    #)
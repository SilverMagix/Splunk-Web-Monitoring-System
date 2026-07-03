import asyncio
import os
import random
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Web App")

MONITORING_SERVICE_URL = os.getenv(
    "MONITORING_SERVICE_URL", "http://localhost:8002"
)

FAKE_PRODUCTS = [
    {"id": 1, "name": "Wireless Mouse", "price": 29.99},
    {"id": 2, "name": "Mechanical Keyboard", "price": 89.99},
    {"id": 3, "name": "USB-C Hub", "price": 49.99},
    {"id": 4, "name": "Monitor Stand", "price": 39.99},
    {"id": 5, "name": "Webcam HD", "price": 59.99},
    {"id": 6, "name": "Laptop Sleeve", "price": 24.99},
    {"id": 7, "name": "Noise Cancelling Headphones", "price": 199.99},
    {"id": 8, "name": "Portable SSD 1TB", "price": 119.99},
    {"id": 9, "name": "Desk Lamp", "price": 34.99},
    {"id": 10, "name": "Ergonomic Chair", "price": 349.99},
]


class LoginRequest(BaseModel):
    username: str
    password: str


class CheckoutRequest(BaseModel):
    cart_id: str
    items: int = 1


def random_ip() -> str:
    choice = random.randint(0, 2)
    if choice == 0:
        return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    if choice == 1:
        return f"192.168.{random.randint(0, 255)}.{random.randint(1, 254)}"
    return f"203.0.113.{random.randint(1, 254)}"


async def forward_log(log_event: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{MONITORING_SERVICE_URL}/ingest", json=log_event)
    except Exception:
        pass


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    user_id = None

    response = await call_next(request)

    if hasattr(request.state, "user_id"):
        user_id = request.state.user_id

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    log_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "web-app",
        "endpoint": request.url.path,
        "method": request.method,
        "status_code": response.status_code,
        "response_time_ms": elapsed_ms,
        "ip": random_ip(),
    }
    if user_id:
        log_event["user_id"] = user_id

    asyncio.create_task(forward_log(log_event))
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products")
async def products():
    await asyncio.sleep(random.uniform(0.02, 0.1))
    count = random.randint(5, 10)
    return {"products": random.sample(FAKE_PRODUCTS, count)}


@app.post("/login")
async def login(body: LoginRequest, request: Request):
    await asyncio.sleep(random.uniform(0.05, 0.15))
    if random.random() < 0.7:
        user_id = f"user_{random.randint(1000, 9999)}"
        request.state.user_id = user_id
        return {"status": "success", "user_id": user_id}
    return JSONResponse(
        status_code=401,
        content={"status": "failed", "message": "Invalid credentials"},
    )


@app.post("/checkout")
async def checkout(body: CheckoutRequest, request: Request):
    await asyncio.sleep(random.uniform(0.2, 1.5))
    user_id = f"user_{random.randint(1000, 9999)}"
    request.state.user_id = user_id
    if random.random() < 0.15:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Payment processing failed"},
        )
    return {
        "status": "success",
        "order_id": f"ORD-{random.randint(100000, 999999)}",
        "total": round(random.uniform(20.0, 500.0), 2),
    }

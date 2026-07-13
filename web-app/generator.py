"""Traffic simulator for the web app: baseline load plus bursts, brute-force, and checkout spikes."""

import asyncio
import os
import random
import time

import httpx

WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:8001")

# (method, path, JSON body or None, selection weight)
ENDPOINTS = [
    ("GET", "/products", None, 0.40),
    ("POST", "/login", {"username": "user", "password": "pass"}, 0.30),
    ("POST", "/checkout", {"cart_id": "cart-1", "items": 3}, 0.20),
    ("GET", "/health", None, 0.10),
]

stats = {"sent": 0, "errors": 0}


def pick_endpoint():
    """Weighted random choice among demo endpoints."""
    roll = random.random()
    cumulative = 0.0
    for method, path, body, weight in ENDPOINTS:
        cumulative += weight
        if roll <= cumulative:
            return method, path, body
    return ENDPOINTS[0][0], ENDPOINTS[0][1], ENDPOINTS[0][2]


async def send_request(client: httpx.AsyncClient, method: str, path: str, body: dict | None):
    """Send one request and update success/error counters."""
    url = f"{WEB_APP_URL}{path}"
    try:
        if method == "GET":
            response = await client.get(url)
        else:
            response = await client.post(url, json=body)
        stats["sent"] += 1
        if response.status_code >= 400:
            stats["errors"] += 1
    except Exception:
        stats["errors"] += 1


async def burst_traffic(client: httpx.AsyncClient):
    """Every ~10s: fire 10–20 concurrent mixed requests."""
    count = random.randint(10, 20)
    tasks = []
    for _ in range(count):
        method, path, body = pick_endpoint()
        tasks.append(send_request(client, method, path, body))
    await asyncio.gather(*tasks)


async def brute_force_logins(client: httpx.AsyncClient):
    """Every ~30s: rapid failed login attempts (bad credentials)."""
    count = random.randint(5, 10)
    for _ in range(count):
        username = f"attacker_{random.randint(1, 9999)}"
        await send_request(
            client,
            "POST",
            "/login",
            {"username": username, "password": "wrong"},
        )
        await asyncio.sleep(0.05)


async def checkout_spike(client: httpx.AsyncClient):
    """Every ~45s: several concurrent checkout requests."""
    count = random.randint(3, 5)
    tasks = [
        send_request(
            client,
            "POST",
            "/checkout",
            {"cart_id": f"cart-{random.randint(1, 100)}", "items": random.randint(1, 5)},
        )
        for _ in range(count)
    ]
    await asyncio.gather(*tasks)


async def main():
    """Run continuous baseline traffic with periodic anomaly patterns."""
    print(f"Load generator targeting {WEB_APP_URL}", flush=True)
    print("Press Ctrl+C to stop\n", flush=True)

    start = time.time()
    last_burst = start
    last_brute = start
    last_checkout = start
    last_summary = start

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            now = time.time()

            if now - last_burst >= 10:
                await burst_traffic(client)
                last_burst = now

            if now - last_brute >= 30:
                await brute_force_logins(client)
                last_brute = now

            if now - last_checkout >= 45:
                await checkout_spike(client)
                last_checkout = now

            # Steady baseline: one request every 200–500 ms.
            method, path, body = pick_endpoint()
            await send_request(client, method, path, body)

            if now - last_summary >= 10:
                elapsed = int(now - start)
                print(
                    f"[{elapsed}s] sent={stats['sent']} errors={stats['errors']}",
                    flush=True,
                )
                last_summary = now

            await asyncio.sleep(random.uniform(0.2, 0.5))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\nStopped. Total sent={stats['sent']} errors={stats['errors']}", flush=True)

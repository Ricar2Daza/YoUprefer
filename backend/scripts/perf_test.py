
import asyncio
import time
import random
import httpx
from statistics import mean, median

BASE_URL = "http://localhost:8000/api/v1"
# Adjust these credentials to match a valid user in your local DB or create one
USERNAME = "perf_user@example.com"
PASSWORD = "password123"

async def get_token(client):
    try:
        response = await client.post(f"{BASE_URL}/auth/login/access-token", data={
            "username": USERNAME,
            "password": PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        print(f"Login failed: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Login error: {e}")
    return None

async def measure_endpoint(client, token, endpoint, iterations=20):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    times = []
    success_count = 0
    
    print(f"Testing {endpoint} with {iterations} iterations...")
    
    for i in range(iterations):
        start = time.time()
        try:
            response = await client.get(f"{BASE_URL}{endpoint}", headers=headers)
            elapsed = (time.time() - start) * 1000 # ms
            times.append(elapsed)
            if response.status_code == 200:
                success_count += 1
            # else:
            #     print(f"Request failed: {response.status_code}")
        except Exception as e:
            print(f"Request error: {e}")
            
    if not times:
        return 0, 0, 0
        
    return mean(times), median(times), success_count

async def main():
    async with httpx.AsyncClient() as client:
        # 1. Setup / Login
        # Create user if not exists? Ideally we assume one exists or we rely on previous tests
        # For now, let's try to register one to be sure
        try:
            await client.post(f"{BASE_URL}/auth/register", json={
                "email": USERNAME,
                "password": PASSWORD,
                "full_name": "Perf User"
            })
        except:
            pass
            
        token = await get_token(client)
        if not token:
            print("Skipping authenticated tests due to login failure")
            return

        # 2. Test get_random_pair
        avg, med, success = await measure_endpoint(client, token, "/profiles/pair", 50)
        print(f"GET /profiles/pair: Avg={avg:.2f}ms, Median={med:.2f}ms, Success={success}/50")

        # 3. Test get_ranking
        avg, med, success = await measure_endpoint(client, token, "/profiles/ranking", 50)
        print(f"GET /profiles/ranking: Avg={avg:.2f}ms, Median={med:.2f}ms, Success={success}/50")

if __name__ == "__main__":
    asyncio.run(main())

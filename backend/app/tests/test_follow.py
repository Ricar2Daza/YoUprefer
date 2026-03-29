import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_follow_and_unfollow_flow(client: AsyncClient):
    response_a = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "follower@example.com",
            "password": "password123",
            "full_name": "Follower User",
        },
    )
    assert response_a.status_code == 200
    user_a = response_a.json()

    response_b = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "following@example.com",
            "password": "password123",
            "full_name": "Following User",
        },
    )
    assert response_b.status_code == 200
    user_b = response_b.json()

    login_a = await client.post(
        "/api/v1/auth/login/access-token",
        data={"username": "follower@example.com", "password": "password123"},
    )
    assert login_a.status_code == 200
    token_a = login_a.json()["access_token"]

    follow_response = await client.post(
        f"/api/v1/users/{user_b['id']}/follow",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert follow_response.status_code == 201
    follow_data = follow_response.json()
    assert follow_data["follower_id"] == user_a["id"]
    assert follow_data["following_id"] == user_b["id"]

    me_a = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert me_a.status_code == 200
    me_a_data = me_a.json()
    assert me_a_data["following_count"] == 1
    assert me_a_data["follower_count"] == 0

    login_b = await client.post(
        "/api/v1/auth/login/access-token",
        data={"username": "following@example.com", "password": "password123"},
    )
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]

    me_b = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert me_b.status_code == 200
    me_b_data = me_b.json()
    assert me_b_data["follower_count"] == 1
    assert me_b_data["following_count"] == 0

    followers_response = await client.get(
        f"/api/v1/users/{user_b['id']}/followers",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert followers_response.status_code == 200
    followers = followers_response.json()
    assert len(followers) == 1
    assert followers[0]["id"] == user_a["id"]

    unfollow_response = await client.delete(
        f"/api/v1/users/{user_b['id']}/follow",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert unfollow_response.status_code == 200

    me_a_after = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert me_a_after.status_code == 200
    me_a_after_data = me_a_after.json()
    assert me_a_after_data["following_count"] == 0
    assert me_a_after_data["follower_count"] == 0

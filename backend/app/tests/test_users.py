import pytest
from httpx import AsyncClient
from app import schemas
from app.core import security

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    # Crear un usuario
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test_user_create@example.com",
            "password": "password123",
            "full_name": "Test User Create"
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test_user_create@example.com"
    assert "id" in data
    assert "hashed_password" not in data

@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: AsyncClient):
    # Crear el primer usuario
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "password123",
            "full_name": "Original User"
        },
    )
    
    # Intentar crear el mismo usuario
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "password456",
            "full_name": "Duplicate User"
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "El usuario con este correo ya existe en el sistema."

@pytest.mark.asyncio
async def test_read_user_me(client: AsyncClient):
    # 1. Registrar usuario
    email = "me@example.com"
    password = "password123"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Me User"},
    )
    
    # 2. Login para obtener token
    login_response = await client.post(
        "/api/v1/auth/login/access-token",
        data={"username": email, "password": password},
    )
    token = login_response.json()["access_token"]
    
    # 3. Leer perfil propio con token
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert data["votes_cast_count"] == 0

@pytest.mark.asyncio
async def test_update_user_me(client: AsyncClient):
    # 1. Registrar usuario
    email = "update_me@example.com"
    password = "password123"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Update Me"},
    )
    
    # 2. Login
    login_response = await client.post(
        "/api/v1/auth/login/access-token",
        data={"username": email, "password": password},
    )
    token = login_response.json()["access_token"]
    
    # 3. Actualizar
    new_name = "Updated Name"
    response = await client.put(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": new_name}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == new_name

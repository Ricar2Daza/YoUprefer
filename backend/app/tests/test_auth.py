def test_register_user(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test_reg@example.com", "password": "password123", "full_name": "Test User"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test_reg@example.com"
    assert "id" in data

def test_login(client):
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "password123", "full_name": "Login User"},
    )
    
    # Login
    response = client.post(
        "/api/v1/auth/login/access-token",
        data={"username": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

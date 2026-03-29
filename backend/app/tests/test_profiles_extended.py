import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.profile import ProfileType, Gender


@pytest.mark.asyncio
async def test_profile_pair_endpoint(client: AsyncClient, db: AsyncSession):
    """Test getting a random pair of profiles"""
    from app.models.user import User
    from app.models.profile import Profile
    from app.models.category import Category
    
    # Create test data
    user = User(email="pairuser@example.com", hashed_password="x", full_name="Pair User", is_active=True)
    category = Category(name="Pair Category", slug="pair-category", is_active=True)
    db.add_all([user, category])
    await db.commit()
    await db.refresh(user)
    await db.refresh(category)
    
    # Create multiple profiles
    for i in range(3):
        profile = Profile(
            user_id=user.id,
            category_id=category.id,
            type=ProfileType.REAL,
            gender=Gender.FEMALE,
            elo_score=1000 + i * 100,
            is_approved=True,
            is_active=True,
            image_url=f"http://test.com/pair{i}.jpg"
        )
        db.add(profile)
    await db.commit()
    
    # Test getting a pair
    r = await client.get(f"{settings.API_V1_STR}/profiles/pair")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2  # Should return exactly 2 profiles
    assert all(p["gender"] == "female" for p in data)  # Should be female profiles
    assert all(p["is_approved"] == True for p in data)
    assert all(p["is_active"] == True for p in data)


@pytest.mark.asyncio
async def test_profile_pair_with_category_filter(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.profile import Profile
    from app.models.category import Category
    
    user = User(
        email="paircatuser@example.com",
        hashed_password="x",
        full_name="Pair Cat User",
        is_active=True,
    )
    category1 = Category(name="Category 1", slug="category-1", is_active=True)
    category2 = Category(name="Category 2", slug="category-2", is_active=True)
    db.add_all([user, category1, category2])
    await db.commit()
    await db.refresh(user)
    await db.refresh(category1)
    await db.refresh(category2)
    
    profile1 = Profile(
        user_id=user.id,
        category_id=category1.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        elo_score=1000,
        is_approved=True,
        is_active=True,
        image_url="http://test.com/cat1.jpg",
    )
    profile2 = Profile(
        user_id=user.id,
        category_id=category1.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        elo_score=1100,
        is_approved=True,
        is_active=True,
        image_url="http://test.com/cat1b.jpg",
    )
    profile_other_category = Profile(
        user_id=user.id,
        category_id=category2.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        elo_score=900,
        is_approved=True,
        is_active=True,
        image_url="http://test.com/cat2.jpg",
    )
    db.add_all([profile1, profile2, profile_other_category])
    await db.commit()
    
    # Test category filter
    r = await client.get(f"{settings.API_V1_STR}/profiles/pair?category_id={category1.id}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(p["category_id"] == category1.id for p in data)


@pytest.mark.asyncio
async def test_profile_ranking_endpoint(client: AsyncClient, db: AsyncSession):
    """Test profile ranking endpoint"""
    from app.models.user import User
    from app.models.profile import Profile
    from app.models.category import Category
    
    # Create test data
    user = User(email="rankinguser@example.com", hashed_password="x", full_name="Ranking User", is_active=True)
    category = Category(name="Ranking Category", slug="ranking-category", is_active=True)
    db.add_all([user, category])
    await db.commit()
    await db.refresh(user)
    await db.refresh(category)
    
    # Create profiles with different scores
    for i in range(3):
        profile = Profile(
            user_id=user.id,
            category_id=category.id,
            type=ProfileType.REAL,
            gender=Gender.MALE,
            elo_score=1500 - i * 100,  # Descending scores
            is_approved=True,
            is_active=True,
            image_url=f"http://test.com/ranking{i}.jpg"
        )
        db.add(profile)
    await db.commit()
    
    # Test ranking endpoint
    r = await client.get(f"{settings.API_V1_STR}/profiles/ranking")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 3
    # Check that profiles are ordered by score (highest first)
    for i in range(len(data) - 1):
        assert data[i]["elo_score"] >= data[i + 1]["elo_score"]


@pytest.mark.asyncio
async def test_profile_me_endpoint_requires_auth(client: AsyncClient):
    """Test that /profiles/me requires authentication"""
    r = await client.get(f"{settings.API_V1_STR}/profiles/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_upload_requires_auth(client: AsyncClient):
    """Test that profile upload requires authentication"""
    r = await client.post(f"{settings.API_V1_STR}/profiles/", json={
        "category_id": 1,
        "type": "real",
        "gender": "male",
        "legal_consent": True
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_upload_direct_requires_auth(client: AsyncClient):
    """Test that profile upload direct requires authentication"""
    r = await client.post(f"{settings.API_V1_STR}/profiles/upload-direct", json={
        "category_id": 1,
        "type": "real",
        "gender": "male",
        "legal_consent": True
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_leave_requires_auth(client: AsyncClient):
    """Test that profile leave requires authentication"""
    r = await client.post(f"{settings.API_V1_STR}/profiles/1/leave")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_delete_requires_auth(client: AsyncClient):
    """Test that profile deletion requires authentication"""
    r = await client.delete(f"{settings.API_V1_STR}/profiles/1")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_participation_status_requires_auth(client: AsyncClient):
    """Test that participation status requires authentication"""
    r = await client.get(f"{settings.API_V1_STR}/profiles/me/participation-status")
    assert r.status_code == 401

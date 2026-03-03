import uuid
import aiosqlite
import config
from database import queries


async def test_register_login_me(client):
    email = f"user-{uuid.uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "password"})
    res = await client.post("/auth/login", json={"email": email, "password": "password"})
    token = res.json()["access_token"]

    me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


async def test_admin_forbidden(client, user_token):
    res = await client.get("/admin/users", headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 403


async def test_admin_access(client, temp_db, admin_token):
    res = await client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200

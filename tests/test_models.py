async def test_models_endpoint(client, user_token):
    res = await client.get("/models", headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 200
    data = res.json()
    assert "openai" in data or "gemini" in data or "claude" in data

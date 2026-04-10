async def test_models_endpoint(client, user_token):
    res = await client.get("/models", headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 200
    data = res.json()
    assert "openai" in data
    assert data["gemini"] == ["gemini-2.5-flash-lite"]
    assert data["claude"] == ["claude-haiku-4-5"]

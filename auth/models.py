from pydantic import BaseModel, EmailStr
from typing import Literal, Optional

Tier = Literal["free", "basic", "pro"]
Role = Literal["user", "admin"]

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    role: Role
    tier: Tier

class UpdateTierRequest(BaseModel):
    tier: Tier

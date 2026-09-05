from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class Msg(BaseModel):
    msg: str

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

class VerifyEmail(BaseModel):
    token: str = Field(..., min_length=1)

class ResendVerification(BaseModel):
    email: EmailStr

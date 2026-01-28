from typing import Optional
from pydantic import BaseModel, EmailStr

class Msg(BaseModel):
    msg: str

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

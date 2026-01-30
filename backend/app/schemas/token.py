from typing import Optional
from pydantic import BaseModel

# Token schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[int] = None
    type: Optional[str] = None

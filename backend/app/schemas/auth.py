from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated: bool


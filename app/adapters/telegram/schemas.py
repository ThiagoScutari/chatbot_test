from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    id: int
    first_name: str
    username: str | None = None


class TelegramChat(BaseModel):
    id: int
    type: str  # private, group, supergroup, channel


class TelegramMessage(BaseModel):
    message_id: int
    from_user: TelegramUser | None = Field(None, alias="from")
    chat: TelegramChat
    text: str | None = None
    date: int  # unix timestamp

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None

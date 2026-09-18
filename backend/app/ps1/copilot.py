"""Backward-compatibility module. Use app.ps1.assistant instead."""
from app.ps1.assistant import Draft, chat

__all__ = ["Draft", "chat"]

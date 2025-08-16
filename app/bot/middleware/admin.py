"""Middleware and filters to restrict access to administrators."""

from __future__ import annotations

from typing import Iterable, List

from aiogram import types
from aiogram.filters import BaseFilter


class AdminFilter(BaseFilter):
    """Allow only administrators based on user ID."""

    def __init__(self, admin_ids: Iterable[int]):
        self.admin_ids: List[int] = list(admin_ids)

    async def __call__(self, message: types.Message) -> bool:
        return bool(message.from_user and message.from_user.id in self.admin_ids)


__all__ = ["AdminFilter"]

"""Finite state machine definitions for bot flows."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterLogin(StatesGroup):
    phone = State()
    code = State()
    password = State()


class SourceManage(StatesGroup):
    waiting_action = State()
    editing_source = State()


class PromptEdit(StatesGroup):
    waiting_text = State()


class ModelKey(StatesGroup):
    waiting_model = State()
    waiting_key = State()


class PipelineControl(StatesGroup):
    confirm = State()


class ScheduleEdit(StatesGroup):
    waiting_cron = State()


class Moderation(StatesGroup):
    reviewing = State()


__all__ = [
    "MasterLogin",
    "SourceManage",
    "PromptEdit",
    "ModelKey",
    "PipelineControl",
    "ScheduleEdit",
    "Moderation",
]

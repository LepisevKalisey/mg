"""Telegram command handlers for admin bot."""

from __future__ import annotations

from typing import Iterable

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from .middleware.admin import AdminFilter
from .states import (
    MasterLogin,
    ModelKey,
    Moderation,
    PipelineControl,
    PromptEdit,
    ScheduleEdit,
    SourceManage,
)


async def _cancel_state(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.")


def setup_router(admin_ids: Iterable[int]) -> Router:
    """Create router with all handlers and admin filter."""
    router = Router()
    router.message.filter(AdminFilter(admin_ids))

    @router.message(CommandStart())
    async def cmd_start(message: types.Message) -> None:
        await message.answer("MG Digest admin bot")

    # Master login flow
    @router.message(Command("login"))
    async def login_start(message: types.Message, state: FSMContext) -> None:
        await state.set_state(MasterLogin.phone)
        await message.answer("Send master phone number:")

    @router.message(MasterLogin.phone, F.text)
    async def login_phone(message: types.Message, state: FSMContext) -> None:
        await state.update_data(phone=message.text)
        await state.set_state(MasterLogin.code)
        await message.answer("Enter login code:")

    @router.message(MasterLogin.code, F.text)
    async def login_code(message: types.Message, state: FSMContext) -> None:
        await state.update_data(code=message.text)
        await state.set_state(MasterLogin.password)
        await message.answer("Enter 2FA password or send - if not set:")

    @router.message(MasterLogin.password, F.text)
    async def login_password(message: types.Message, state: FSMContext) -> None:
        # Stub: here Telethon login would be performed
        await state.clear()
        await message.answer("Master logged in (stub).")

    # Source management
    @router.message(Command("sources"))
    async def sources_menu(message: types.Message, state: FSMContext) -> None:
        await state.set_state(SourceManage.waiting_action)
        await message.answer("Send source name to toggle or /cancel:")

    @router.message(SourceManage.waiting_action, F.text)
    async def sources_toggle(message: types.Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(f"Toggled source {message.text} (stub).")

    # Prompt editor
    @router.message(Command("prompt"))
    async def prompt_edit(message: types.Message, state: FSMContext) -> None:
        await state.set_state(PromptEdit.waiting_text)
        await message.answer("Send new prompt text:")

    @router.message(PromptEdit.waiting_text, F.text)
    async def prompt_save(message: types.Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Prompt updated (stub).")

    # Model/key management
    @router.message(Command("model"))
    async def model_choose(message: types.Message, state: FSMContext) -> None:
        await state.set_state(ModelKey.waiting_model)
        await message.answer("Send model name:")

    @router.message(ModelKey.waiting_model, F.text)
    async def model_set(message: types.Message, state: FSMContext) -> None:
        await state.update_data(model=message.text)
        await state.set_state(ModelKey.waiting_key)
        await message.answer("Send API key:")

    @router.message(ModelKey.waiting_key, F.text)
    async def model_key_save(message: types.Message, state: FSMContext) -> None:
        data = await state.get_data()
        model = data.get("model")
        await state.clear()
        await message.answer(f"Key for {model} saved (stub).")

    # Pipeline control
    @router.message(Command("pipeline"))
    async def pipeline_control(message: types.Message, state: FSMContext) -> None:
        await state.set_state(PipelineControl.confirm)
        await message.answer("Send on/off to control pipeline:")

    @router.message(PipelineControl.confirm, F.text)
    async def pipeline_set(message: types.Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(f"Pipeline set to {message.text} (stub).")

    # Schedule editor
    @router.message(Command("schedule"))
    async def schedule_edit(message: types.Message, state: FSMContext) -> None:
        await state.set_state(ScheduleEdit.waiting_cron)
        await message.answer("Send cron expression:")

    @router.message(ScheduleEdit.waiting_cron, F.text)
    async def schedule_save(message: types.Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Schedule updated (stub).")

    # Moderation UI
    @router.message(Command("moderate"))
    async def moderation_start(message: types.Message, state: FSMContext) -> None:
        await state.set_state(Moderation.reviewing)
        await message.answer("Nothing to moderate (stub).")

    # Cancel handler
    @router.message(Command("cancel"))
    async def cancel(message: types.Message, state: FSMContext) -> None:
        await _cancel_state(message, state)

    return router


__all__ = ["setup_router"]

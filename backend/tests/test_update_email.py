"""Unit tests for PUT /login/me/email (`update_me_email`).

Rewritten: the old `GdprRepository.update_email` / `Gdpr` model this file
tested no longer exist -- that logic was inlined into the `update_me_email`
route handler directly against `UserRepository` + `UserInfo` (gdpr.user_info).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.user import User
from models.user import UserInfo as UserInfoModel
from router.api.auth import UpdateEmailRequest, update_me_email


def _run(coro):
    return asyncio.run(coro)


def _session_returning_info(info: UserInfoModel | None) -> AsyncMock:
    """A session whose `select(UserInfo)` lookup returns `info`.

    ``Session.add`` is synchronous in real SQLAlchemy; AsyncMock would mock it
    as a coroutine function and leave an unawaited-coroutine warning behind.
    """
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = info
    session.execute.return_value = result
    return session


class TestUpdateMeEmail:
    def test_success_updates_email(self):
        async def _run_test():
            user = User(user_id=uuid4(), role="user")
            info = UserInfoModel(user_id=user.user_id, email="old@example.com", user_name="old")
            session = _session_returning_info(info)
            user_repo = AsyncMock()
            user_repo.get_by_email.return_value = None

            with patch("router.api.auth.UserRepository", return_value=user_repo):
                result = await update_me_email(
                    request=UpdateEmailRequest(email="new@example.com"),
                    user=user,
                    session=session,
                )

            user_repo.get_by_email.assert_awaited_once_with("new@example.com")
            assert info.email == "new@example.com"
            session.add.assert_called_once_with(info)
            session.commit.assert_awaited_once()
            session.refresh.assert_awaited_once_with(info)
            assert result.email == "new@example.com"
            assert result.user_id == user.user_id

        _run(_run_test())

    def test_conflict_raises_for_other_user(self):
        async def _run_test():
            user = User(user_id=uuid4(), role="user")
            other_user = User(user_id=uuid4(), role="user")
            session = AsyncMock()
            user_repo = AsyncMock()
            user_repo.get_by_email.return_value = other_user

            with patch("router.api.auth.UserRepository", return_value=user_repo):
                with pytest.raises(HTTPException) as exc_info:
                    await update_me_email(
                        request=UpdateEmailRequest(email="taken@example.com"),
                        user=user,
                        session=session,
                    )

            assert exc_info.value.status_code == 409
            assert exc_info.value.detail == "email already registered"
            # The conflict check is the first thing the handler does -- it
            # must fail before ever reading or writing gdpr.user_info.
            session.execute.assert_not_called()
            session.commit.assert_not_called()

        _run(_run_test())

    def test_same_user_can_keep_own_email(self):
        async def _run_test():
            user = User(user_id=uuid4(), role="user")
            info = UserInfoModel(user_id=user.user_id, email="same@example.com", user_name="same")
            session = _session_returning_info(info)
            user_repo = AsyncMock()
            user_repo.get_by_email.return_value = user  # same user_id -> not a conflict

            with patch("router.api.auth.UserRepository", return_value=user_repo):
                result = await update_me_email(
                    request=UpdateEmailRequest(email="same@example.com"),
                    user=user,
                    session=session,
                )

            assert result.email == "same@example.com"
            session.commit.assert_awaited_once()

        _run(_run_test())

    def test_missing_profile_raises_403(self):
        async def _run_test():
            user = User(user_id=uuid4(), role="user")
            session = _session_returning_info(None)
            user_repo = AsyncMock()
            user_repo.get_by_email.return_value = None

            with patch("router.api.auth.UserRepository", return_value=user_repo):
                with pytest.raises(HTTPException) as exc_info:
                    await update_me_email(
                        request=UpdateEmailRequest(email="any@example.com"),
                        user=user,
                        session=session,
                    )

            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "User profile not found"
            session.add.assert_not_called()
            session.commit.assert_not_called()

        _run(_run_test())

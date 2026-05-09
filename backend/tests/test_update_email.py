"""Unit tests for GdprRepository.update_email (success and conflict paths)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.user import Gdpr
from repository.user import GdprRepository


def _run(coro):
    return asyncio.run(coro)


class TestUpdateEmail:
    def _make_repo(self) -> GdprRepository:
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return GdprRepository(session)

    def test_success_updates_email(self):
        async def _test():
            repo = self._make_repo()
            user_id = uuid4()
            new_email = "new@example.com"
            gdpr = Gdpr(user_id=user_id, email="old@example.com", legal_name="")

            with (
                patch.object(repo, "get_by_email", new=AsyncMock(return_value=None)),
                patch.object(repo, "get_by_user_id", new=AsyncMock(return_value=gdpr)),
            ):
                result = await repo.update_email(user_id, new_email)

            assert result.email == new_email
            repo.session.add.assert_called_once_with(gdpr)
            repo.session.commit.assert_awaited_once()

        _run(_test())

    def test_conflict_raises_for_other_user(self):
        async def _test():
            repo = self._make_repo()
            user_id = uuid4()
            other_user_id = uuid4()
            taken_email = "taken@example.com"
            other_gdpr = Gdpr(user_id=other_user_id, email=taken_email, legal_name="")

            with patch.object(repo, "get_by_email", new=AsyncMock(return_value=other_gdpr)):
                with pytest.raises(ValueError, match="already registered"):
                    await repo.update_email(user_id, taken_email)

        _run(_test())

    def test_same_user_can_keep_own_email(self):
        async def _test():
            repo = self._make_repo()
            user_id = uuid4()
            email = "same@example.com"
            gdpr = Gdpr(user_id=user_id, email=email, legal_name="")

            with (
                patch.object(repo, "get_by_email", new=AsyncMock(return_value=gdpr)),
                patch.object(repo, "get_by_user_id", new=AsyncMock(return_value=gdpr)),
            ):
                result = await repo.update_email(user_id, email)

            assert result.email == email

        _run(_test())

    def test_user_not_found_raises(self):
        async def _test():
            repo = self._make_repo()
            user_id = uuid4()

            with (
                patch.object(repo, "get_by_email", new=AsyncMock(return_value=None)),
                patch.object(repo, "get_by_user_id", new=AsyncMock(return_value=None)),
            ):
                with pytest.raises(ValueError, match="user not found"):
                    await repo.update_email(user_id, "any@example.com")

        _run(_test())

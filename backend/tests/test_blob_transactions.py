"""Failure-path coverage: denied/failed publication never damages live bytes."""

import asyncio
from contextlib import ExitStack
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile

from router.api import rows as api


def run_probe(*, denied=False, upload_failure=False, copy_failure=False, commit_failure=False):
    async def probe():
        events = []
        table = SimpleNamespace(workspace_id=uuid4(), table_id="test")
        user = SimpleNamespace(user_id=uuid4())
        row = SimpleNamespace(row_id=1, row_data={"doc": {"key": "original"}})
        session = AsyncMock()
        repo = MagicMock()

        async def lock(*_):
            events.append("authorize")
            if denied:
                raise HTTPException(status_code=403)
            return row

        async def stage(*_, **kwargs):
            assert kwargs["commit"] is False
            events.append("db_stage")

        async def put(**_):
            events.append("upload_temp")
            if upload_failure:
                raise ClientError({"Error": {"Code": "InternalError"}}, "PutObject")

        async def copy(**_):
            events.append("promote")
            if copy_failure:
                raise ClientError({"Error": {"Code": "InternalError"}}, "CopyObject")

        async def commit():
            events.append("db_commit")
            if commit_failure:
                raise RuntimeError("commit connection lost")

        repo.lock_for_write = AsyncMock(side_effect=lock)
        repo.update_blob = AsyncMock(side_effect=stage)
        session.commit.side_effect = commit
        s3 = MagicMock()
        s3.put_object = AsyncMock(side_effect=put)
        s3.copy_object = AsyncMock(side_effect=copy)
        s3.delete_object = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=s3)
        context.__aexit__ = AsyncMock(return_value=False)
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, "_get_table_for_member", AsyncMock(return_value=table)))
            stack.enter_context(patch.object(api, "_get_blob_column", AsyncMock()))
            stack.enter_context(patch.object(api, "RowRepository", return_value=repo))
            register = stack.enter_context(patch.object(api, "register_upload", AsyncMock()))
            client = stack.enter_context(patch.object(api, "s3_client", return_value=context))
            if denied or upload_failure or copy_failure or commit_failure:
                with pytest.raises((HTTPException, RuntimeError)):
                    await api.put_blob_cell(
                        "test", 1, "doc", UploadFile(file=BytesIO(b"new"), filename="new.txt"), user, session
                    )
                session.rollback.assert_awaited_once()
            else:
                metadata = await api.put_blob_cell(
                    "test", 1, "doc", UploadFile(file=BytesIO(b"new"), filename="new.txt"), user, session
                )
                assert metadata.key != "original"
                assert s3.copy_object.call_args.kwargs["Key"] == metadata.key
            if denied:
                client.assert_not_called()
                register.assert_not_awaited()
                repo.update_blob.assert_not_awaited()
            elif upload_failure:
                s3.copy_object.assert_not_awaited()
                session.commit.assert_not_awaited()
            elif copy_failure:
                session.commit.assert_not_awaited()
            s3.delete_object.assert_not_awaited()
            assert row.row_data["doc"]["key"] == "original"
        return events

    return asyncio.run(probe())


def test_authorize_stage_upload_promote_then_commit():
    assert run_probe() == ["authorize", "db_stage", "upload_temp", "promote", "db_commit"]


def test_read_only_user_never_touches_storage():
    assert run_probe(denied=True) == ["authorize"]


def test_failed_upload_never_promotes():
    assert run_probe(upload_failure=True) == ["authorize", "db_stage", "upload_temp"]


def test_failed_promotion_preserves_original():
    assert run_probe(copy_failure=True) == ["authorize", "db_stage", "upload_temp", "promote"]


def test_ambiguous_commit_leaves_cleanup_to_db_authority():
    assert run_probe(commit_failure=True)[-1] == "db_commit"


def test_foreign_blob_key_rejected_before_storage_read():
    async def probe():
        table = SimpleNamespace(workspace_id=uuid4(), table_id="test")
        repo = MagicMock()
        repo.get_by_number = AsyncMock(return_value=SimpleNamespace(row_data={"doc": {"key": "foreign"}}))
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one.return_value = False
        session.execute.return_value = result
        with (
            patch.object(api, "_get_table_for_member", AsyncMock(return_value=table)),
            patch.object(api, "_get_blob_column", AsyncMock()),
            patch.object(api, "RowRepository", return_value=repo),
            patch.object(api, "s3_client") as client,
        ):
            with pytest.raises(HTTPException) as exc:
                await api.get_blob_cell("test", 1, "doc", MagicMock(), session)
            assert exc.value.status_code == 404
            client.assert_not_called()

    asyncio.run(probe())

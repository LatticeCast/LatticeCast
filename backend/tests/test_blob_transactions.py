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


def run_probe(*, denied=False, upload_failure=False, deleted_during_upload=False, commit_failure=False):
    async def probe():
        events = []
        table = SimpleNamespace(workspace_id=uuid4(), table_id="test")
        user = SimpleNamespace(user_id=uuid4())
        row = SimpleNamespace(row_id=1, row_data={"doc": {"key": "original"}})
        session = AsyncMock()
        repo = MagicMock()

        async def stage(*_, **kwargs):
            assert kwargs["commit"] is False
            events.append("db_stage")
            if deleted_during_upload:
                # public.update_blob_cell raises when the row went away while
                # the object was in flight; the router must queue the orphan.
                raise RuntimeError("Row disappeared during blob update")

        async def put(**_):
            events.append("upload_final")
            if upload_failure:
                raise ClientError({"Error": {"Code": "InternalError"}}, "PutObject")

        async def commit():
            events.append("db_commit")
            if commit_failure:
                raise RuntimeError("commit connection lost")

        repo.get_by_number = AsyncMock(return_value=row)
        repo.update_blob = AsyncMock(side_effect=stage)
        session.commit.side_effect = commit
        session.execute.return_value = MagicMock()
        session.execute.return_value.scalar_one.return_value = not denied
        session.rollback.side_effect = lambda: events.append("db_rollback")
        s3 = MagicMock()
        s3.put_object = AsyncMock(side_effect=put)
        s3.delete_object = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=s3)
        context.__aexit__ = AsyncMock(return_value=False)
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, "_get_table_for_member", AsyncMock(return_value=table)))
            stack.enter_context(patch.object(api, "_get_blob_column", AsyncMock()))
            stack.enter_context(patch.object(api, "RowRepository", return_value=repo))
            queue = stack.enter_context(patch.object(api, "queue_orphan_upload", AsyncMock()))
            client = stack.enter_context(patch.object(api, "s3_client", return_value=context))
            if denied or upload_failure or deleted_during_upload or commit_failure:
                with pytest.raises((HTTPException, RuntimeError)):
                    await api.put_blob_cell(
                        "test", 1, "doc", UploadFile(file=BytesIO(b"new"), filename="new.txt"), user, session
                    )
            else:
                metadata = await api.put_blob_cell(
                    "test", 1, "doc", UploadFile(file=BytesIO(b"new"), filename="new.txt"), user, session
                )
                assert metadata.key != "original"
                assert s3.put_object.call_args.kwargs["Key"] == metadata.key
            if denied:
                client.assert_not_called()
                repo.update_blob.assert_not_awaited()
            elif upload_failure:
                session.commit.assert_not_awaited()
            elif deleted_during_upload:
                session.commit.assert_not_awaited()
            if upload_failure or deleted_during_upload or commit_failure:
                queue.assert_awaited_once()
            else:
                queue.assert_not_awaited()
            s3.delete_object.assert_not_awaited()
            assert row.row_data["doc"]["key"] == "original"
        return events

    return asyncio.run(probe())


def test_upload_finishes_before_metadata_commit():
    """The row lock lives inside the single UPDATE, never across S3."""
    assert run_probe() == ["db_rollback", "upload_final", "db_stage", "db_commit"]


def test_read_only_user_never_touches_storage():
    assert run_probe(denied=True) == []


def test_failed_upload_never_opens_row_write_transaction():
    assert run_probe(upload_failure=True) == ["db_rollback", "upload_final", "db_rollback"]


def test_deleted_during_upload_queues_orphan():
    assert run_probe(deleted_during_upload=True) == ["db_rollback", "upload_final", "db_stage", "db_rollback"]


def test_ambiguous_commit_leaves_cleanup_to_db_authority():
    assert run_probe(commit_failure=True)[-2:] == ["db_commit", "db_rollback"]


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

"""The row write lock must follow the workspace-delete cascade order."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from models.row import Row
from repository.row import RowRepository


class TestRowLockOrder(IsolatedAsyncioTestCase):
    async def test_parent_table_is_locked_before_row_update(self):
        row = Row(table_id=7, row_id=9, row_data={})
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        session = MagicMock()
        session.execute = AsyncMock(side_effect=[MagicMock(), result])

        self.assertIs(await RowRepository(session).lock_for_write(7, 9), row)

        calls = session.execute.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertIn("FROM public.tables", str(calls[0].args[0]))
        self.assertIn("FOR KEY SHARE", str(calls[0].args[0]))
        self.assertEqual(calls[0].args[1], {"tid": 7})
        self.assertIn("UPDATE public.rows", str(calls[1].args[0]))
        self.assertEqual(calls[1].args[1], {"tid": 7, "rid": 9})

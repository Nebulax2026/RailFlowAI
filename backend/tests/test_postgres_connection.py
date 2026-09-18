from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.storage as storage


class PostgresConnectionTests(unittest.TestCase):
    def test_supabase_pooler_connection_requires_tls_without_ca_verification(self) -> None:
        connection = object()
        database_url = (
            "postgresql://postgres.project%2Dref:p%40ssword%23123@"
            "aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
        )

        with (
            patch.object(storage, "_db_url", database_url),
            patch("pg8000.dbapi.connect", return_value=connection) as connect,
        ):
            self.assertIs(storage._connect(), connection)

        connect.assert_called_once_with(
            user="postgres.project-ref",
            password="p@ssword#123",
            host="aws-0-ap-southeast-1.pooler.supabase.com",
            port=5432,
            database="postgres",
            ssl_context=True,
        )


if __name__ == "__main__":
    unittest.main()

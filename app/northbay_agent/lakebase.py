"""Lakebase (managed Postgres) access with short-lived OAuth credentials.

Inside the Databricks App this authenticates as the app service principal; in a notebook it
authenticates as the current user. Credentials are refreshed before the one-hour expiry.
"""
import os
import threading
import time
import uuid

import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient

from . import config

_TOKEN_TTL_SECONDS = 40 * 60


class Lakebase:
    def __init__(self, instance: str = config.LAKEBASE_INSTANCE, database: str = config.LAKEBASE_DATABASE,
                 w: WorkspaceClient | None = None):
        self.w = w or WorkspaceClient()
        self.instance = instance
        self.database = database
        self._host = None
        self._user = None
        self._token = None
        self._token_at = 0.0
        self._lock = threading.Lock()

    def _credentials(self):
        with self._lock:
            if self._host is None:
                self._host = self.w.database.get_database_instance(name=self.instance).read_write_dns
                # Postgres role: the service principal's application id in Apps, the user name otherwise
                self._user = os.getenv("DATABRICKS_CLIENT_ID") or self.w.current_user.me().user_name
            if self._token is None or time.time() - self._token_at > _TOKEN_TTL_SECONDS:
                cred = self.w.database.generate_database_credential(
                    request_id=str(uuid.uuid4()), instance_names=[self.instance])
                self._token, self._token_at = cred.token, time.time()
            return self._host, self._user, self._token

    def connect(self):
        host, user, token = self._credentials()
        return psycopg.connect(host=host, port=5432, dbname=self.database, user=user, password=token,
                               sslmode="require", row_factory=dict_row, connect_timeout=15)

    def query(self, sql: str, params=None) -> list[dict]:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def execute(self, sql: str, params=None) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()


_default = None


def get_lakebase() -> Lakebase:
    global _default
    if _default is None:
        _default = Lakebase()
    return _default

from __future__ import annotations

from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from .config import settings


@contextmanager
def mysql_server_connection():
    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def mysql_connection():
    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        yield connection
    finally:
        connection.close()


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS cases (
        case_id VARCHAR(64) NOT NULL PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        category VARCHAR(64) NULL,
        source VARCHAR(64) NOT NULL,
        source_session_id VARCHAR(255) NULL,
        source_user_id VARCHAR(255) NULL,
        priority VARCHAR(16) NOT NULL,
        summary TEXT NULL,
        current_owner_agent VARCHAR(32) NOT NULL,
        recommended_next_action VARCHAR(64) NULL,
        labels_json LONGTEXT NULL,
        workdir_path TEXT NOT NULL,
        created_at DATETIME(3) NOT NULL,
        updated_at DATETIME(3) NOT NULL,
        KEY idx_cases_status_updated (status, updated_at),
        KEY idx_cases_owner_updated (current_owner_agent, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id VARCHAR(64) NOT NULL PRIMARY KEY,
        case_id VARCHAR(64) NOT NULL,
        type VARCHAR(64) NOT NULL,
        stage VARCHAR(32) NOT NULL,
        title VARCHAR(255) NOT NULL,
        format VARCHAR(32) NOT NULL,
        storage_mode VARCHAR(32) NOT NULL,
        storage_path TEXT NULL,
        local_path TEXT NULL,
        bucket_name VARCHAR(255) NULL,
        object_key VARCHAR(1024) NULL,
        original_filename VARCHAR(255) NULL,
        size_bytes BIGINT NULL,
        content_type VARCHAR(255) NULL,
        produced_by_agent VARCHAR(64) NOT NULL,
        version INT NOT NULL,
        metadata_json LONGTEXT NULL,
        created_at DATETIME(3) NOT NULL,
        KEY idx_artifacts_case_created (case_id, created_at),
        KEY idx_artifacts_case_type (case_id, type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id VARCHAR(64) NOT NULL PRIMARY KEY,
        case_id VARCHAR(64) NOT NULL,
        kind VARCHAR(64) NOT NULL,
        actor_type VARCHAR(32) NOT NULL,
        actor_id VARCHAR(64) NOT NULL,
        payload_json LONGTEXT NULL,
        created_at DATETIME(3) NOT NULL,
        KEY idx_events_case_created (case_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS session_logs (
        log_id VARCHAR(64) NOT NULL PRIMARY KEY,
        session_type VARCHAR(64) NOT NULL,
        session_id VARCHAR(255) NOT NULL,
        log_date DATE NOT NULL,
        filename VARCHAR(255) NOT NULL,
        size_bytes BIGINT NOT NULL,
        bucket_name VARCHAR(255) NULL,
        object_key VARCHAR(1024) NULL,
        uploaded_at DATETIME(3) NOT NULL,
        KEY idx_session_logs_date (log_date),
        KEY idx_session_logs_session (session_type, session_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS log_cards (
        card_id VARCHAR(64) NOT NULL PRIMARY KEY,
        log_id VARCHAR(64) NOT NULL,
        agent VARCHAR(64) NOT NULL,
        card_type VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        summary TEXT NULL,
        severity VARCHAR(32) NULL,
        status VARCHAR(32) NOT NULL,
        payload_json LONGTEXT NULL,
        created_at DATETIME(3) NOT NULL,
        updated_at DATETIME(3) NOT NULL,
        KEY idx_log_cards_log_created (log_id, created_at),
        KEY idx_log_cards_agent_type (agent, card_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS log_events (
        event_id VARCHAR(64) NOT NULL PRIMARY KEY,
        log_id VARCHAR(64) NOT NULL,
        agent VARCHAR(64) NOT NULL,
        kind VARCHAR(64) NOT NULL,
        payload_json LONGTEXT NULL,
        created_at DATETIME(3) NOT NULL,
        KEY idx_log_events_log_created (log_id, created_at),
        KEY idx_log_events_agent_kind (agent, kind)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def init_mysql() -> None:
    with mysql_server_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.commit()

    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)
        connection.commit()

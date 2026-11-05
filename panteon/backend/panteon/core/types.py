from sqlalchemy import JSON, Text, String
from sqlalchemy.types import TypeDecorator
import json
import uuid as uuid_lib
from panteon.core.database import is_sqlite


if is_sqlite:
    class JSONB(TypeDecorator):
        impl = Text
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is not None:
                return json.dumps(value)
            return None

        def process_result_value(self, value, dialect):
            if value is not None:
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            return None

    class SQLiteUUID(TypeDecorator):
        impl = String(36)
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, uuid_lib.UUID):
                return str(value)
            return str(uuid_lib.UUID(str(value)))

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, uuid_lib.UUID):
                return value
            try:
                return uuid_lib.UUID(value)
            except (ValueError, AttributeError):
                return value

    def UUID_COL(as_uuid=True):
        return SQLiteUUID()

else:
    from sqlalchemy.dialects.postgresql import UUID, JSONB as PG_JSONB
    JSONB = PG_JSONB

    def UUID_COL(as_uuid=True):
        return UUID(as_uuid=as_uuid)

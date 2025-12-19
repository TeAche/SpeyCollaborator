from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP


metadata = MetaData()


users = Table(
    "users",
    metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column("name", Text),
    Column("created_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
)


categories = Table(
    "categories",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("name", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    UniqueConstraint("user_id", "name", name="uq_categories_user_id_name"),
)


tags = Table(
    "tags",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("name", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    UniqueConstraint("user_id", "name", name="uq_tags_user_id_name"),
)


tasks = Table(
    "tasks",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("title", Text, nullable=False),
    Column("category_id", ForeignKey("categories.id", ondelete="SET NULL")),
    Column("priority", SmallInteger, server_default="1"),
    Column("status", String(length=16), server_default="'active'"),
    Column("comment", Text, server_default="''", nullable=False),
    Column("due_at", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    Column("done_at", TIMESTAMP(timezone=True)),
    Index("ix_tasks_user_status", "user_id", "status"),
)


task_tags = Table(
    "task_tags",
    metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


settings = Table(
    "settings",
    metadata,
    Column("user_id", ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
)

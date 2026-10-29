from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.config import Settings
from app.db.base import Base
from app.models import DocumentChunk, KnowledgeDocument, VectorIndex  # noqa: F401


def test_database_password_is_encoded_and_masked():
    password = "p@ss:/%?#word"
    settings = Settings(_env_file=None, mysql_password=password)
    url = settings.database_url()
    assert url.password == password
    assert password not in str(url)
    assert password not in repr(settings)
    assert url.query["charset"] == "utf8mb4"
    assert settings.database_url(include_database=False).database is None


def test_models_compile_for_mysql_with_chinese_search_and_embedding():
    assert set(Base.metadata.tables) == {
        "knowledge_base", "knowledge_document", "document_chunk", "vector_index", "embedding_task", "retrieval_log", "retrieval_hit", "policy_conversation", "policy_turn"
    }
    dialect = mysql.dialect()
    ddl = str(CreateTable(DocumentChunk.__table__).compile(dialect=dialect))
    assert "MEDIUMBLOB" in ddl
    assert "AUTO_INCREMENT" in ddl
    assert "ON DELETE CASCADE" in ddl
    assert "utf8mb4_0900_ai_ci" in ddl
    fulltext = next(i for i in DocumentChunk.__table__.indexes if i.name == "ft_document_chunk_content")
    index_ddl = str(CreateIndex(fulltext).compile(dialect=dialect))
    assert "FULLTEXT" in index_ddl
    assert "WITH PARSER ngram" in index_ddl

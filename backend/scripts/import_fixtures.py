import asyncio
import tempfile
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
import sys
import os

# Add backend directory to sys.path so we can import modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.archive import extract_backup_async
from services.email_parser import parse_eml
from services.embedding import (
    STORAGE_EMBEDDING_DIMENSION,
    chunk_text,
    fit_embedding_vector,
    generate_embeddings,
)
from services.threading_service import assign_thread_id
from db.session import AsyncSessionLocal
from db.models import Email, TenantConfig
from sqlalchemy import select
from services.tenant_config_scope import tenant_config_owner_filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
IMPORT_USER_ID = os.environ.get("NARUON_IMPORT_USER_ID", "default")
IMPORT_ORGANIZATION_ID = os.environ.get("NARUON_IMPORT_ORGANIZATION_ID", "default")
IMPORT_WORKSPACE_ID = os.environ.get(
    "NARUON_IMPORT_WORKSPACE_ID", f"workspace-{IMPORT_ORGANIZATION_ID}"
)


async def process_zip_file(zip_path: str | Path, session: AsyncSession):
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(f"Extracting {zip_path}...")
        extracted_files = await extract_backup_async(zip_path, temp_dir)

        batch_values = []
        for file_path in extracted_files:
            if not str(file_path).endswith(".eml"):
                continue

            try:
                email_data = parse_eml(file_path)
            except Exception as e:
                logger.error(f"Failed to parse {file_path}: {e}")
                continue

            chunks = chunk_text(email_data["body"])
            embedding = None
            if chunks:
                try:
                    tenant_config = await session.scalar(
                        select(TenantConfig).where(
                            *tenant_config_owner_filters(
                                IMPORT_USER_ID,
                                IMPORT_ORGANIZATION_ID,
                            )
                        )
                    )
                    api_key = (
                        tenant_config.openai_api_key
                        if tenant_config and tenant_config.openai_api_key
                        else os.getenv("OPENAI_API_KEY")
                    ) or ""
                    embeddings = await generate_embeddings([chunks[0]], api_key)
                    if embeddings:
                        embedding = fit_embedding_vector(
                            embeddings[0],
                            STORAGE_EMBEDDING_DIMENSION,
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to generate embedding for {email_data['message_id']}: {e}"
                    )

            # Upsert into database
            thread_id = await assign_thread_id(
                session,
                email_data,
                user_id=IMPORT_USER_ID,
                organization_id=IMPORT_ORGANIZATION_ID,
                workspace_id=IMPORT_WORKSPACE_ID,
            )

            batch_values.append(
                dict(
                    user_id=IMPORT_USER_ID,
                    organization_id=IMPORT_ORGANIZATION_ID,
                    workspace_id=IMPORT_WORKSPACE_ID,
                    message_id=email_data["message_id"],
                    sender=email_data["sender"],
                    reply_to=email_data.get("reply_to"),
                    recipients=email_data["recipients"],
                    subject=email_data["subject"],
                    in_reply_to=email_data.get("in_reply_to"),
                    references=email_data.get("references"),
                    thread_id=thread_id,
                    date=email_data["date"],
                    body=email_data["body"],
                    embedding=embedding,
                )
            )

        if batch_values:
            stmt = insert(Email)
            stmt = stmt.on_conflict_do_update(
                # Alembic 0020_email_workspace_scope replaced the 3-column
                # uq_emails_owner_message_id constraint with the 4-column
                # uq_emails_workspace_message; an ON CONFLICT target that still
                # names only the old 3-column shape matches no constraint on a
                # real PostgreSQL database and the insert is rejected outright.
                index_elements=[
                    "user_id",
                    "organization_id",
                    "workspace_id",
                    "message_id",
                ],
                set_=dict(
                    sender=stmt.excluded.sender,
                    reply_to=stmt.excluded.reply_to,
                    recipients=stmt.excluded.recipients,
                    subject=stmt.excluded.subject,
                    in_reply_to=stmt.excluded.in_reply_to,
                    references=stmt.excluded.references,
                    thread_id=stmt.excluded.thread_id,
                    user_id=stmt.excluded.user_id,
                    organization_id=stmt.excluded.organization_id,
                    workspace_id=stmt.excluded.workspace_id,
                    date=stmt.excluded.date,
                    body=stmt.excluded.body,
                    embedding=stmt.excluded.embedding,
                ),
            )
            await session.execute(stmt, batch_values)
        await session.commit()
        logger.info(f"Finished processing {zip_path}")


async def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    fixtures_dir = root_dir / "secret_fixtures"

    if not fixtures_dir.exists():
        logger.error(f"Fixtures directory {fixtures_dir} does not exist.")
        return

    async with AsyncSessionLocal() as session:
        for zip_file in fixtures_dir.glob("*.zip"):
            await process_zip_file(zip_file, session)


if __name__ == "__main__":
    asyncio.run(main())

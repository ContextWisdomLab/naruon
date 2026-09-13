import asyncio
import sys
import logging
from pathlib import Path

from db.session import AsyncSessionLocal
from db.models import Email, Attachment
from services.email_parser import parse_eml
from services.embedding import (
    STORAGE_EMBEDDING_DIMENSION,
    fit_embedding_vector,
    generate_embeddings,
)
from services.threading_service import assign_thread_id
import os
from sqlalchemy import select

EMBEDDING_DIMENSION = STORAGE_EMBEDDING_DIMENSION
IMPORT_USER_ID = os.environ.get("NARUON_IMPORT_USER_ID", "default")
IMPORT_ORGANIZATION_ID = os.environ.get("NARUON_IMPORT_ORGANIZATION_ID", "default")
IMPORT_WORKSPACE_ID = os.environ.get(
    "NARUON_IMPORT_WORKSPACE_ID", f"workspace-{IMPORT_ORGANIZATION_ID}"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def generate_fixture_embedding(text: str) -> list[float]:
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_api_key:
        return [0.0] * EMBEDDING_DIMENSION

    embeddings = await generate_embeddings([text], openai_api_key=openai_api_key)
    if not embeddings:
        return [0.0] * EMBEDDING_DIMENSION
    return fit_embedding_vector(embeddings[0], EMBEDDING_DIMENSION)


async def import_eml_file(session, eml_file: Path) -> bool:
    try:
        parsed = parse_eml(eml_file)
    except Exception as e:
        logger.error(f"Failed to parse {eml_file}: {e}")
        return False

    existing = await session.execute(
        select(Email).where(
            Email.message_id == parsed["message_id"],
            Email.user_id == IMPORT_USER_ID,
            Email.organization_id == IMPORT_ORGANIZATION_ID,
            Email.workspace_id == IMPORT_WORKSPACE_ID,
        )
    )
    if existing.scalar_one_or_none():
        logger.info(f"Email {parsed['message_id']} already exists, skipping.")
        return False

    body_text = parsed["body"] if parsed["body"].strip() else "Empty body"
    try:
        body_emb = await generate_fixture_embedding(body_text)
    except Exception as e:
        logger.error(f"Failed to generate embedding for {eml_file}: {e}")
        return False

    thread_id = await assign_thread_id(
        session,
        parsed,
        user_id=IMPORT_USER_ID,
        organization_id=IMPORT_ORGANIZATION_ID,
        workspace_id=IMPORT_WORKSPACE_ID,
    )

    email_obj = Email(
        user_id=IMPORT_USER_ID,
        organization_id=IMPORT_ORGANIZATION_ID,
        workspace_id=IMPORT_WORKSPACE_ID,
        message_id=parsed["message_id"],
        sender=parsed["sender"],
        reply_to=parsed.get("reply_to"),
        recipients=parsed["recipients"],
        subject=parsed["subject"],
        in_reply_to=parsed.get("in_reply_to"),
        references=parsed.get("references"),
        date=parsed["date"],
        body=parsed["body"],
        embedding=body_emb,
        thread_id=thread_id,
    )

    for att in parsed.get("attachments", []):
        att_text = att["content"] if att["content"].strip() else "Empty attachment"
        try:
            att_emb = await generate_fixture_embedding(att_text)
            email_obj.attachments.append(
                Attachment(
                    filename=att["filename"],
                    content=att["content"],
                    embedding=att_emb,
                )
            )
        except Exception as e:
            logger.error(
                f"Failed to generate embedding for attachment {att['filename']}: {e}"
            )

    session.add(email_obj)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to commit {eml_file}: {e}")
        return False
    logger.info(
        f"Imported {eml_file.name} with {len(parsed.get('attachments', []))} attachments."
    )
    return True


async def main():
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures"
    if not fixtures_dir.exists():
        logger.error(f"Fixtures directory {fixtures_dir} does not exist.")
        sys.exit(1)

    eml_files = list(fixtures_dir.glob("*.eml"))
    if not eml_files:
        logger.warning(f"No .eml files found in {fixtures_dir}.")
        return

    async with AsyncSessionLocal() as session:
        for eml_file in eml_files:
            await import_eml_file(session, eml_file)


if __name__ == "__main__":
    asyncio.run(main())

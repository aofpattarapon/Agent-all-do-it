"""One-time backfill: encrypt any plaintext rows in the `secrets` table.

The secret store now encrypts values at rest with Fernet (``app/core/secret_crypto.py``).
Rows created before that change hold plaintext. This command re-encrypts every row whose
``value_encrypted`` is not already a ``fernet:`` token. It is idempotent — already-encrypted
rows are skipped — so it is safe to run repeatedly.

Usage:
    uv run pixel_dream_agent cmd encrypt-secrets --dry-run
    uv run pixel_dream_agent cmd encrypt-secrets
"""

import asyncio

import click
from sqlalchemy import select

from app.commands import command, info, success, warning
from app.core.secret_crypto import encrypt_secret, is_encrypted
from app.db.models.secret import Secret
from app.db.session import get_db_context


@command("encrypt-secrets", help="Encrypt plaintext rows in the secrets table (idempotent)")
@click.option("--dry-run", is_flag=True, help="Show what would change without saving")
def encrypt_secrets(dry_run: bool) -> None:
    """Backfill-encrypt any plaintext secret values at rest."""

    async def _run() -> None:
        async with get_db_context() as db:
            rows = list((await db.execute(select(Secret))).scalars().all())
            total = len(rows)
            to_encrypt = [s for s in rows if not is_encrypted(s.value_encrypted)]

            info(f"Scanned {total} secret(s); {len(to_encrypt)} plaintext row(s) to encrypt.")
            if not to_encrypt:
                success("Nothing to do — all secrets are already encrypted.")
                return

            for s in to_encrypt:
                # value_masked already exists; we only re-wrap the stored value.
                if dry_run:
                    warning(f"[dry-run] would encrypt secret {s.id} ({s.provider}/{s.name})")
                    continue
                s.value_encrypted = encrypt_secret(s.value_encrypted)

            if dry_run:
                warning("Dry run — no changes saved.")
                return

            await db.commit()
            success(f"Encrypted {len(to_encrypt)} secret(s) at rest.")

    asyncio.run(_run())

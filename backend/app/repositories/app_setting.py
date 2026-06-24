"""AppSetting repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.app_setting import AppSetting


async def get(db: AsyncSession, key: str) -> AppSetting | None:
    return await db.get(AppSetting, key)


async def get_value(db: AsyncSession, key: str, default: str = "") -> str:
    row = await db.get(AppSetting, key)
    return row.value if row else default


async def list_all(db: AsyncSession) -> list[AppSetting]:
    result = await db.execute(select(AppSetting).order_by(AppSetting.key))
    return list(result.scalars().all())


async def upsert(
    db: AsyncSession, *, key: str, value: str, description: str | None = None
) -> AppSetting:
    row = await db.get(AppSetting, key)
    if row:
        row.value = value
        if description is not None:
            row.description = description
    else:
        row = AppSetting(key=key, value=value, description=description or "")
        db.add(row)
    await db.flush()
    await db.refresh(row)
    return row

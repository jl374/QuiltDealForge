"""sector_enum_to_varchar

Convert sector column from sector_tag enum to free-text varchar so
any sector can be used, not just the 7 hardcoded values.

Revision ID: b2f8d3a1c5e7
Revises: 1cbf645ea107
Create Date: 2026-02-25 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2f8d3a1c5e7'
down_revision: str = '1cbf645ea107'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert enum column to varchar, keeping existing values
    op.alter_column(
        'companies',
        'sector',
        type_=sa.String(),
        existing_type=sa.Enum(
            'IVF', 'SDIRA', 'Accounting', 'HOA', 'RCM', 'Defense', 'Other',
            name='sector_tag',
        ),
        postgresql_using='sector::text',
    )
    # Drop the old enum type
    op.execute("DROP TYPE IF EXISTS sector_tag")


def downgrade() -> None:
    # Recreate the enum type
    op.execute(
        "CREATE TYPE sector_tag AS ENUM "
        "('IVF','SDIRA','Accounting','HOA','RCM','Defense','Other')"
    )
    # Convert back — any non-enum values become 'Other'
    op.execute(
        "UPDATE companies SET sector = 'Other' "
        "WHERE sector NOT IN ('IVF','SDIRA','Accounting','HOA','RCM','Defense','Other')"
    )
    op.alter_column(
        'companies',
        'sector',
        type_=sa.Enum(
            'IVF', 'SDIRA', 'Accounting', 'HOA', 'RCM', 'Defense', 'Other',
            name='sector_tag',
        ),
        postgresql_using='sector::sector_tag',
    )

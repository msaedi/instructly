"""cleanup old booking system and rename availability tables

Revision ID: 15ea6e11292b
Revises: de6ba296eafc
Create Date: 2025-06-11 20:11:26.526065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15ea6e11292b'
down_revision: Union[str, None] = 'de6ba296eafc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    print("Starting migration: Cleanup and rename tables...")
    
    # 1. Drop recurring_availability table
    print("Dropping recurring_availability table...")
    op.drop_table('recurring_availability')
    
    # 2. Remove old booking columns from instructor_profiles
    print("Removing old booking columns from instructor_profiles...")
    with op.batch_alter_table('instructor_profiles') as batch_op:
        batch_op.drop_column('buffer_time')
        batch_op.drop_column('minimum_advance_hours')
        batch_op.drop_column('default_session_duration')
    
    # 3. Rename tables
    print("Renaming specific_date_availability to instructor_availability...")
    op.rename_table('specific_date_availability', 'instructor_availability')
    
    print("Renaming date_time_slots to availability_slots...")
    op.rename_table('date_time_slots', 'availability_slots')
    
    # 4. Update foreign key and column name
    print("Updating foreign key constraints and column names...")
    with op.batch_alter_table('availability_slots') as batch_op:
        # Drop old foreign key constraint
        batch_op.drop_constraint('date_time_slots_date_override_id_fkey', type_='foreignkey')
        
        # Rename column
        batch_op.alter_column('date_override_id', new_column_name='availability_id')
        
        # Create new foreign key constraint
        batch_op.create_foreign_key(
            'availability_slots_availability_id_fkey',
            'instructor_availability',
            ['availability_id'], ['id'],
            ondelete='CASCADE'
        )
    
    # 5. Update indexes with new names
    print("Updating index names...")
    op.drop_index('idx_specific_date', table_name='instructor_availability')
    op.create_index('idx_instructor_availability_instructor_date', 
                    'instructor_availability', ['instructor_id', 'date'])
    
    op.create_index('idx_availability_slots_availability_id', 
                    'availability_slots', ['availability_id'])
    
    print("Migration completed successfully!")


def downgrade():
    # Reversal operations (if needed)
    print("Downgrade not implemented - this is a one-way migration")
    raise NotImplementedError("Downgrade not supported for this migration")

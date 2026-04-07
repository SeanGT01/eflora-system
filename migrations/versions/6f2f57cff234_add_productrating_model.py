"""Add ProductRating model

Revision ID: 6f2f57cff234
Revises: add_delivery_proof_001
Create Date: 2026-04-08 00:01:24.159782

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f2f57cff234'
down_revision = 'add_delivery_proof_001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('product_ratings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('order_item_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('customer_id', 'order_item_id', name='unique_customer_order_item_rating')
    )


def downgrade():
    op.drop_table('product_ratings')
    op.drop_table('pagc_rules')
    op.drop_table('zip_lookup_all')
    op.drop_table('state_lookup')
    op.drop_table('zip_state_loc')
    op.drop_table('tabblock20')
    op.drop_table('geocode_settings')
    with op.batch_alter_table('county', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_tiger_county'))

    op.drop_table('county')
    op.drop_table('tract')
    with op.batch_alter_table('state', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_tiger_state_the_geom_gist'), postgresql_using='gist')

    op.drop_table('state')
    op.drop_table('tabblock')
    with op.batch_alter_table('featnames', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_tiger_featnames_lname'))
        batch_op.drop_index(batch_op.f('idx_tiger_featnames_snd_name'))
        batch_op.drop_index(batch_op.f('idx_tiger_featnames_tlid_statefp'))

    op.drop_table('featnames')
    op.drop_table('zcta5')
    op.drop_table('zip_state')
    op.drop_table('loader_lookuptables')
    op.drop_table('pagc_gaz')
    with op.batch_alter_table('place', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('tiger_place_the_geom_gist'), postgresql_using='gist')

    op.drop_table('place')
    with op.batch_alter_table('county_lookup', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('county_lookup_name_idx'))
        batch_op.drop_index(batch_op.f('county_lookup_state_idx'))

    op.drop_table('county_lookup')
    op.drop_table('loader_variables')
    with op.batch_alter_table('faces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_tiger_faces_countyfp'))
        batch_op.drop_index(batch_op.f('idx_tiger_faces_tfid'))
        batch_op.drop_index(batch_op.f('tiger_faces_the_geom_gist'), postgresql_using='gist')

    op.drop_table('faces')
    with op.batch_alter_table('secondary_unit_lookup', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('secondary_unit_lookup_abbrev_idx'))

    op.drop_table('secondary_unit_lookup')
    with op.batch_alter_table('place_lookup', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('place_lookup_name_idx'))
        batch_op.drop_index(batch_op.f('place_lookup_state_idx'))

    op.drop_table('place_lookup')
    with op.batch_alter_table('countysub_lookup', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('countysub_lookup_name_idx'))
        batch_op.drop_index(batch_op.f('countysub_lookup_state_idx'))

    op.drop_table('countysub_lookup')
    with op.batch_alter_table('edges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_edges_tlid'))
        batch_op.drop_index(batch_op.f('idx_tiger_edges_countyfp'))
        batch_op.drop_index(batch_op.f('idx_tiger_edges_the_geom_gist'), postgresql_using='gist')

    op.drop_table('edges')
    with op.batch_alter_table('direction_lookup', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('direction_lookup_abbrev_idx'))

    op.drop_table('direction_lookup')
    with op.batch_alter_table('cousub', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('tige_cousub_the_geom_gist'), postgresql_using='gist')

    op.drop_table('cousub')
    with op.batch_alter_table('addrfeat', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_addrfeat_geom_gist'), postgresql_using='gist')
        batch_op.drop_index(batch_op.f('idx_addrfeat_tlid'))
        batch_op.drop_index(batch_op.f('idx_addrfeat_zipl'))
        batch_op.drop_index(batch_op.f('idx_addrfeat_zipr'))

    op.drop_table('addrfeat')
    op.drop_table('layer')
    op.drop_table('zip_lookup_base')
    op.drop_table('topology')
    with op.batch_alter_table('cloudinary_cleanup_queue', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_cleanup_queue_status'))

    op.drop_table('cloudinary_cleanup_queue')
    op.drop_table('zip_lookup')
    with op.batch_alter_table('street_type_lookup', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('street_type_lookup_abbrev_idx'))

    op.drop_table('street_type_lookup')
    op.drop_table('bg')
    op.drop_table('loader_platform')
    op.drop_table('spatial_ref_sys')
    op.drop_table('geocode_settings_default')
    with op.batch_alter_table('addr', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_tiger_addr_tlid_statefp'))
        batch_op.drop_index(batch_op.f('idx_tiger_addr_zip'))

    op.drop_table('addr')
    with op.batch_alter_table('cart_items', schema=None) as batch_op:
        batch_op.alter_column('is_selected',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('true'))

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_categories_is_active'))
        batch_op.drop_index(batch_op.f('idx_categories_slug'))
        batch_op.drop_index(batch_op.f('idx_categories_sort_order'))

    with op.batch_alter_table('gcash_qrs', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('gcash_qrs_public_id_unique'), type_='unique')
        batch_op.drop_index(batch_op.f('idx_gcash_qrs_public_id'))
        batch_op.drop_column('cloudinary_version')
        batch_op.drop_column('cloudinary_format')

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.alter_column('payment_proof',
               existing_type=sa.VARCHAR(length=255),
               comment=None,
               existing_comment='DEPRECATED: Use payment_proof_public_id and payment_proof_url instead',
               existing_nullable=True)
        batch_op.drop_index(batch_op.f('idx_orders_payment_proof_public_id'))
        batch_op.drop_column('payment_proof_format')
        batch_op.drop_column('payment_proof_version')

    with op.batch_alter_table('pos_order_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_pos_order_items_product_id'))

    with op.batch_alter_table('pos_orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_pos_orders_created_at'))
        batch_op.drop_index(batch_op.f('idx_pos_orders_store_created'))

    with op.batch_alter_table('product_images', schema=None) as batch_op:
        batch_op.alter_column('filename',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
        batch_op.drop_index(batch_op.f('idx_product_images_public_id'))
        batch_op.drop_column('mime_type')
        batch_op.drop_column('image_data')

    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_product_variants_image_public_id'))
        batch_op.drop_column('image_mime_type')
        batch_op.drop_column('image_data')
        batch_op.drop_column('image_version')

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column('main_category_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_index(batch_op.f('idx_products_categories_composite'))
        batch_op.drop_index(batch_op.f('idx_products_main_category'))
        batch_op.drop_index(batch_op.f('idx_products_main_category_id'))
        batch_op.drop_index(batch_op.f('idx_products_store_all_categories'))
        batch_op.drop_index(batch_op.f('idx_products_store_category'))
        batch_op.drop_index(batch_op.f('idx_products_store_category_id'))
        batch_op.drop_index(batch_op.f('idx_products_store_main_category'))
        batch_op.drop_constraint(batch_op.f('products_main_category_id_fkey'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('products_store_category_id_fkey'), type_='foreignkey')
        batch_op.create_foreign_key(None, 'categories', ['main_category_id'], ['id'])
        batch_op.create_foreign_key(None, 'store_categories', ['store_category_id'], ['id'])
        batch_op.drop_column('category')

    with op.batch_alter_table('seller_applications', schema=None) as batch_op:
        batch_op.alter_column('store_logo_path',
               existing_type=sa.VARCHAR(length=500),
               comment=None,
               existing_comment='DEPRECATED: Use store_logo_public_id and store_logo_url instead',
               existing_nullable=True)
        batch_op.alter_column('government_id_path',
               existing_type=sa.VARCHAR(length=500),
               comment=None,
               existing_comment='DEPRECATED: Use government_id_public_id and government_id_url instead',
               existing_nullable=True)
        batch_op.drop_column('store_logo_format')
        batch_op.drop_column('store_logo_version')
        batch_op.drop_column('government_id_version')
        batch_op.drop_column('government_id_format')

    with op.batch_alter_table('stock_reductions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_stock_reductions_created_at'))
        batch_op.drop_index(batch_op.f('idx_stock_reductions_product_date'))
        batch_op.drop_index(batch_op.f('idx_stock_reductions_product_id'))
        batch_op.drop_index(batch_op.f('idx_stock_reductions_reason'))
        batch_op.drop_index(batch_op.f('idx_stock_reductions_reduced_by'))
        batch_op.drop_index(batch_op.f('idx_stock_reductions_variant_id'))
        batch_op.drop_constraint(batch_op.f('stock_reductions_product_id_fkey'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('stock_reductions_reduced_by_fkey'), type_='foreignkey')
        batch_op.create_foreign_key(None, 'products', ['product_id'], ['id'])
        batch_op.create_foreign_key(None, 'users', ['reduced_by'], ['id'])

    with op.batch_alter_table('store_categories', schema=None) as batch_op:
        batch_op.alter_column('custom_attributes',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=True)
        batch_op.drop_index(batch_op.f('idx_store_categories_is_active'))
        batch_op.drop_index(batch_op.f('idx_store_categories_main_category'))
        batch_op.drop_index(batch_op.f('idx_store_categories_sort_order'))
        batch_op.drop_index(batch_op.f('idx_store_categories_store_id'))
        batch_op.drop_index(batch_op.f('idx_store_categories_store_main'))

    with op.batch_alter_table('stores', schema=None) as batch_op:
        batch_op.alter_column('delivery_area',
               existing_type=geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True),
               type_=geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry'),
               existing_nullable=True)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('idx_users_avatar_public_id'))
        batch_op.drop_column('cloudinary_version')
        batch_op.drop_column('cloudinary_format')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cloudinary_format', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('cloudinary_version', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.create_index(batch_op.f('idx_users_avatar_public_id'), ['avatar_public_id'], unique=False)

    with op.batch_alter_table('stores', schema=None) as batch_op:
        batch_op.alter_column('delivery_area',
               existing_type=geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry'),
               type_=geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True),
               existing_nullable=True)

    with op.batch_alter_table('store_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_store_categories_store_main'), ['store_id', 'main_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_store_categories_store_id'), ['store_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_store_categories_sort_order'), ['sort_order'], unique=False)
        batch_op.create_index(batch_op.f('idx_store_categories_main_category'), ['main_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_store_categories_is_active'), ['is_active'], unique=False)
        batch_op.alter_column('custom_attributes',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=True)

    with op.batch_alter_table('stock_reductions', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('stock_reductions_reduced_by_fkey'), 'users', ['reduced_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(batch_op.f('stock_reductions_product_id_fkey'), 'products', ['product_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index(batch_op.f('idx_stock_reductions_variant_id'), ['variant_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_stock_reductions_reduced_by'), ['reduced_by'], unique=False)
        batch_op.create_index(batch_op.f('idx_stock_reductions_reason'), ['reason'], unique=False)
        batch_op.create_index(batch_op.f('idx_stock_reductions_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_stock_reductions_product_date'), ['product_id', sa.literal_column('created_at DESC')], unique=False)
        batch_op.create_index(batch_op.f('idx_stock_reductions_created_at'), [sa.literal_column('created_at DESC')], unique=False)

    with op.batch_alter_table('seller_applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('government_id_format', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('government_id_version', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('store_logo_version', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('store_logo_format', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.alter_column('government_id_path',
               existing_type=sa.VARCHAR(length=500),
               comment='DEPRECATED: Use government_id_public_id and government_id_url instead',
               existing_nullable=True)
        batch_op.alter_column('store_logo_path',
               existing_type=sa.VARCHAR(length=500),
               comment='DEPRECATED: Use store_logo_public_id and store_logo_url instead',
               existing_nullable=True)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('products_store_category_id_fkey'), 'store_categories', ['store_category_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(batch_op.f('products_main_category_id_fkey'), 'categories', ['main_category_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index(batch_op.f('idx_products_store_main_category'), ['store_id', 'main_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_products_store_category_id'), ['store_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_products_store_category'), ['store_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_products_store_all_categories'), ['store_id', 'main_category_id', 'store_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_products_main_category_id'), ['main_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_products_main_category'), ['main_category_id'], unique=False)
        batch_op.create_index(batch_op.f('idx_products_categories_composite'), ['main_category_id', 'store_category_id'], unique=False)
        batch_op.alter_column('main_category_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_version', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('image_data', postgresql.BYTEA(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('image_mime_type', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
        batch_op.create_index(batch_op.f('idx_product_variants_image_public_id'), ['image_public_id'], unique=False)

    with op.batch_alter_table('product_images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_data', postgresql.BYTEA(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('mime_type', sa.VARCHAR(length=50), server_default=sa.text("'image/jpeg'::character varying"), autoincrement=False, nullable=True))
        batch_op.create_index(batch_op.f('idx_product_images_public_id'), ['public_id'], unique=False)
        batch_op.alter_column('filename',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)

    with op.batch_alter_table('pos_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_pos_orders_store_created'), ['store_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('idx_pos_orders_created_at'), ['created_at'], unique=False)

    with op.batch_alter_table('pos_order_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_pos_order_items_product_id'), ['product_id'], unique=False)

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_proof_version', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('payment_proof_format', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.create_index(batch_op.f('idx_orders_payment_proof_public_id'), ['payment_proof_public_id'], unique=False)
        batch_op.alter_column('payment_proof',
               existing_type=sa.VARCHAR(length=255),
               comment='DEPRECATED: Use payment_proof_public_id and payment_proof_url instead',
               existing_nullable=True)

    with op.batch_alter_table('gcash_qrs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cloudinary_format', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('cloudinary_version', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
        batch_op.create_index(batch_op.f('idx_gcash_qrs_public_id'), ['public_id'], unique=False)
        batch_op.create_unique_constraint(batch_op.f('gcash_qrs_public_id_unique'), ['public_id'], postgresql_nulls_not_distinct=False)

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_categories_sort_order'), ['sort_order'], unique=False)
        batch_op.create_index(batch_op.f('idx_categories_slug'), ['slug'], unique=False)
        batch_op.create_index(batch_op.f('idx_categories_is_active'), ['is_active'], unique=False)

    with op.batch_alter_table('cart_items', schema=None) as batch_op:
        batch_op.alter_column('is_selected',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('true'))

    op.create_table('addr',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('tlid', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('fromhn', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('tohn', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('side', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('zip', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('plus4', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('fromtyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('totyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('fromarmid', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('toarmid', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('arid', sa.VARCHAR(length=22), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('gid', name=op.f('addr_pkey'))
    )
    with op.batch_alter_table('addr', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_tiger_addr_zip'), ['zip'], unique=False)
        batch_op.create_index(batch_op.f('idx_tiger_addr_tlid_statefp'), ['tlid', 'statefp'], unique=False)

    op.create_table('geocode_settings_default',
    sa.Column('name', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('setting', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('unit', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('category', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('short_desc', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('name', name=op.f('geocode_settings_default_pkey'))
    )
    op.create_table('spatial_ref_sys',
    sa.Column('srid', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('auth_name', sa.VARCHAR(length=256), autoincrement=False, nullable=True),
    sa.Column('auth_srid', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('srtext', sa.VARCHAR(length=2048), autoincrement=False, nullable=True),
    sa.Column('proj4text', sa.VARCHAR(length=2048), autoincrement=False, nullable=True),
    sa.CheckConstraint('srid > 0 AND srid <= 998999', name=op.f('spatial_ref_sys_srid_check')),
    sa.PrimaryKeyConstraint('srid', name=op.f('spatial_ref_sys_pkey'))
    )
    op.create_table('loader_platform',
    sa.Column('os', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('declare_sect', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('pgbin', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('wget', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('unzip_command', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('psql', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('path_sep', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('loader', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('environ_set_command', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('county_process_command', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('os', name=op.f('loader_platform_pkey'))
    )
    op.create_table('bg',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tractce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('blkgrpce', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('bg_id', sa.VARCHAR(length=12), autoincrement=False, nullable=False),
    sa.Column('namelsad', sa.VARCHAR(length=13), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('awater', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.CheckConstraint("geometrytype(the_geom) = 'MULTIPOLYGON'::text OR the_geom IS NULL", name=op.f('enforce_geotype_geom')),
    sa.CheckConstraint('st_ndims(the_geom) = 2', name=op.f('enforce_dims_geom')),
    sa.CheckConstraint('st_srid(the_geom) = 4269', name=op.f('enforce_srid_geom')),
    sa.PrimaryKeyConstraint('bg_id', name=op.f('bg_pkey')),
    comment='block groups'
    )
    op.create_table('street_type_lookup',
    sa.Column('name', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('abbrev', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('is_hw', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('name', name=op.f('street_type_lookup_pkey'))
    )
    with op.batch_alter_table('street_type_lookup', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('street_type_lookup_abbrev_idx'), ['abbrev'], unique=False)

    op.create_table('zip_lookup',
    sa.Column('zip', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('st_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('state', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('co_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('county', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('cs_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('cousub', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('pl_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('place', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('cnt', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('zip', name=op.f('zip_lookup_pkey'))
    )
    op.create_table('cloudinary_cleanup_queue',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('table_name', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('record_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('public_id', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('action', sa.VARCHAR(length=20), server_default=sa.text("'delete'::character varying"), autoincrement=False, nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), server_default=sa.text("'pending'::character varying"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), autoincrement=False, nullable=True),
    sa.Column('processed_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudinary_cleanup_queue_pkey'))
    )
    with op.batch_alter_table('cloudinary_cleanup_queue', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_cleanup_queue_status'), ['status'], unique=False)

    op.create_table('topology',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('srid', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('precision', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=False),
    sa.Column('hasz', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('useslargeids', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('topology_pkey')),
    sa.UniqueConstraint('name', name=op.f('topology_name_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_table('zip_lookup_base',
    sa.Column('zip', sa.VARCHAR(length=5), autoincrement=False, nullable=False),
    sa.Column('state', sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    sa.Column('county', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('city', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('zip', name=op.f('zip_lookup_base_pkey'))
    )
    op.create_table('layer',
    sa.Column('topology_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('layer_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('schema_name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('table_name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('feature_column', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('feature_type', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('level', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('child_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['topology_id'], ['topology.id'], name=op.f('layer_topology_id_fkey')),
    sa.PrimaryKeyConstraint('topology_id', 'layer_id', name=op.f('layer_pkey')),
    sa.UniqueConstraint('schema_name', 'table_name', 'feature_column', name=op.f('layer_schema_name_table_name_feature_column_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_table('addrfeat',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('tlid', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('aridl', sa.VARCHAR(length=22), autoincrement=False, nullable=True),
    sa.Column('aridr', sa.VARCHAR(length=22), autoincrement=False, nullable=True),
    sa.Column('linearid', sa.VARCHAR(length=22), autoincrement=False, nullable=True),
    sa.Column('fullname', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('lfromhn', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('ltohn', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('rfromhn', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('rtohn', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('zipl', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('zipr', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('edge_mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('parityl', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('parityr', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('plus4l', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('plus4r', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('lfromtyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('ltotyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('rfromtyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('rtotyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('offsetl', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('offsetr', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='LINESTRING', srid=4329, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('gid', name=op.f('addrfeat_pkey'))
    )
    with op.batch_alter_table('addrfeat', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_addrfeat_zipr'), ['zipr'], unique=False)
        batch_op.create_index(batch_op.f('idx_addrfeat_zipl'), ['zipl'], unique=False)
        batch_op.create_index(batch_op.f('idx_addrfeat_tlid'), ['tlid'], unique=False)
        batch_op.create_index(batch_op.f('idx_addrfeat_geom_gist'), ['the_geom'], unique=False, postgresql_using='gist')

    op.create_table('cousub',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('cousubfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('cousubns', sa.VARCHAR(length=8), autoincrement=False, nullable=True),
    sa.Column('cosbidfp', sa.VARCHAR(length=10), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('namelsad', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('lsad', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('classfp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('cnectafp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('nectafp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('nctadvfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.NUMERIC(precision=14, scale=0), autoincrement=False, nullable=True),
    sa.Column('awater', sa.NUMERIC(precision=14, scale=0), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('cosbidfp', name=op.f('cousub_pkey')),
    sa.UniqueConstraint('gid', name=op.f('uidx_cousub_gid'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    with op.batch_alter_table('cousub', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('tige_cousub_the_geom_gist'), ['the_geom'], unique=False, postgresql_using='gist')

    op.create_table('direction_lookup',
    sa.Column('name', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('abbrev', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('name', name=op.f('direction_lookup_pkey'))
    )
    with op.batch_alter_table('direction_lookup', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('direction_lookup_abbrev_idx'), ['abbrev'], unique=False)

    op.create_table('edges',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tlid', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('tfidl', sa.NUMERIC(precision=10, scale=0), autoincrement=False, nullable=True),
    sa.Column('tfidr', sa.NUMERIC(precision=10, scale=0), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('fullname', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('smid', sa.VARCHAR(length=22), autoincrement=False, nullable=True),
    sa.Column('lfromadd', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('ltoadd', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('rfromadd', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('rtoadd', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('zipl', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('zipr', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('featcat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('hydroflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('railflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('roadflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('olfflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('passflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('divroad', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('exttyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('ttyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('deckedroad', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('artpath', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('persist', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('gcseflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('offsetl', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('offsetr', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('tnidf', sa.NUMERIC(precision=10, scale=0), autoincrement=False, nullable=True),
    sa.Column('tnidt', sa.NUMERIC(precision=10, scale=0), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTILINESTRING', srid=4269, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('gid', name=op.f('edges_pkey'))
    )
    with op.batch_alter_table('edges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_tiger_edges_the_geom_gist'), ['the_geom'], unique=False, postgresql_using='gist')
        batch_op.create_index(batch_op.f('idx_tiger_edges_countyfp'), ['countyfp'], unique=False)
        batch_op.create_index(batch_op.f('idx_edges_tlid'), ['tlid'], unique=False)

    op.create_table('countysub_lookup',
    sa.Column('st_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('state', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('co_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('county', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('cs_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('st_code', 'co_code', 'cs_code', name=op.f('countysub_lookup_pkey'))
    )
    with op.batch_alter_table('countysub_lookup', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('countysub_lookup_state_idx'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('countysub_lookup_name_idx'), [sa.literal_column('soundex(name::text)')], unique=False)

    op.create_table('place_lookup',
    sa.Column('st_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('state', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('pl_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('st_code', 'pl_code', name=op.f('place_lookup_pkey'))
    )
    with op.batch_alter_table('place_lookup', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('place_lookup_state_idx'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('place_lookup_name_idx'), [sa.literal_column('soundex(name::text)')], unique=False)

    op.create_table('secondary_unit_lookup',
    sa.Column('name', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('abbrev', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('name', name=op.f('secondary_unit_lookup_pkey'))
    )
    with op.batch_alter_table('secondary_unit_lookup', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('secondary_unit_lookup_abbrev_idx'), ['abbrev'], unique=False)

    op.create_table('faces',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('tfid', sa.NUMERIC(precision=10, scale=0), autoincrement=False, nullable=True),
    sa.Column('statefp00', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp00', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tractce00', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('blkgrpce00', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('blockce00', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('cousubfp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('submcdfp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('conctyfp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('placefp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('aiannhfp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('aiannhce00', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('comptyp00', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('trsubfp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('trsubce00', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('anrcfp00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('elsdlea00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('scsdlea00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('unsdlea00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('uace00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('cd108fp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('sldust00', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('sldlst00', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('vtdst00', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('zcta5ce00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('tazce00', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('ugace00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('puma5ce00', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tractce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('blkgrpce', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('blockce', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('cousubfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('submcdfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('conctyfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('placefp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('aiannhfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('aiannhce', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('comptyp', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('trsubfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('trsubce', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('anrcfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('ttractce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('tblkgpce', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('elsdlea', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('scsdlea', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('unsdlea', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('uace', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('cd111fp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('sldust', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('sldlst', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('vtdst', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('zcta5ce', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('tazce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('ugace', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('puma5ce', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('csafp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('cbsafp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('metdivfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('cnectafp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('nectafp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('nctadvfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('lwflag', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('offset', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('atotal', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.Column('tractce20', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('blkgrpce20', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('blockce20', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('countyfp20', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('statefp20', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('gid', name=op.f('faces_pkey'))
    )
    with op.batch_alter_table('faces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('tiger_faces_the_geom_gist'), ['the_geom'], unique=False, postgresql_using='gist')
        batch_op.create_index(batch_op.f('idx_tiger_faces_tfid'), ['tfid'], unique=False)
        batch_op.create_index(batch_op.f('idx_tiger_faces_countyfp'), ['countyfp'], unique=False)

    op.create_table('loader_variables',
    sa.Column('tiger_year', sa.VARCHAR(length=4), autoincrement=False, nullable=False),
    sa.Column('website_root', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('staging_fold', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('data_schema', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('staging_schema', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('tiger_year', name=op.f('loader_variables_pkey'))
    )
    op.create_table('county_lookup',
    sa.Column('st_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('state', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('co_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('st_code', 'co_code', name=op.f('county_lookup_pkey'))
    )
    with op.batch_alter_table('county_lookup', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('county_lookup_state_idx'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('county_lookup_name_idx'), [sa.literal_column('soundex(name::text)')], unique=False)

    op.create_table('place',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('placefp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('placens', sa.VARCHAR(length=8), autoincrement=False, nullable=True),
    sa.Column('plcidfp', sa.VARCHAR(length=7), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('namelsad', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('lsad', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('classfp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('cpi', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('pcicbsa', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('pcinecta', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('awater', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('plcidfp', name=op.f('place_pkey')),
    sa.UniqueConstraint('gid', name=op.f('uidx_tiger_place_gid'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    with op.batch_alter_table('place', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('tiger_place_the_geom_gist'), ['the_geom'], unique=False, postgresql_using='gist')

    op.create_table('pagc_gaz',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('seq', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('word', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('stdword', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('token', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('is_custom', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pagc_gaz_pkey'))
    )
    op.create_table('loader_lookuptables',
    sa.Column('process_order', sa.INTEGER(), server_default=sa.text('1000'), autoincrement=False, nullable=False),
    sa.Column('lookup_name', sa.TEXT(), autoincrement=False, nullable=False, comment='This is the table name to inherit from and suffix of resulting output table -- how the table will be named --  edges here would mean -- ma_edges , pa_edges etc. except in the case of national tables. national level tables have no prefix'),
    sa.Column('table_name', sa.TEXT(), autoincrement=False, nullable=True, comment='suffix of the tables to load e.g.  edges would load all tables like *edges.dbf(shp)  -- so tl_2010_42129_edges.dbf .  '),
    sa.Column('single_mode', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('load', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False, comment="Whether or not to load the table.  For states and zcta5 (you may just want to download states10, zcta510 nationwide file manually) load your own into a single table that inherits from tiger.states, tiger.zcta5.  You'll get improved performance for some geocoding cases."),
    sa.Column('level_county', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('level_state', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('level_nation', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False, comment='These are tables that contain all data for the whole US so there is just a single file'),
    sa.Column('post_load_process', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('single_geom_mode', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=True),
    sa.Column('insert_mode', sa.CHAR(length=1), server_default=sa.text("'c'::bpchar"), autoincrement=False, nullable=False),
    sa.Column('pre_load_process', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('columns_exclude', postgresql.ARRAY(sa.TEXT()), autoincrement=False, nullable=True, comment='List of columns to exclude as an array. This is excluded from both input table and output table and rest of columns remaining are assumed to be in same order in both tables. gid, geoid,cpi,suffix1ce are excluded if no columns are specified.'),
    sa.Column('website_root_override', sa.TEXT(), autoincrement=False, nullable=True, comment='Path to use for wget instead of that specified in year table.  Needed currently for zcta where they release that only for 2000 and 2010'),
    sa.PrimaryKeyConstraint('lookup_name', name=op.f('loader_lookuptables_pkey'))
    )
    op.create_table('zip_state',
    sa.Column('zip', sa.VARCHAR(length=5), autoincrement=False, nullable=False),
    sa.Column('stusps', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('zip', 'stusps', name=op.f('zip_state_pkey'))
    )
    op.create_table('zcta5',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('zcta5ce', sa.VARCHAR(length=5), autoincrement=False, nullable=False),
    sa.Column('classfp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('awater', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('partflg', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('zcta5ce', 'statefp', name=op.f('pk_tiger_zcta5_zcta5ce'))
    )
    op.create_table('featnames',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('tlid', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('fullname', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('predirabrv', sa.VARCHAR(length=15), autoincrement=False, nullable=True),
    sa.Column('pretypabrv', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('prequalabr', sa.VARCHAR(length=15), autoincrement=False, nullable=True),
    sa.Column('sufdirabrv', sa.VARCHAR(length=15), autoincrement=False, nullable=True),
    sa.Column('suftypabrv', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('sufqualabr', sa.VARCHAR(length=15), autoincrement=False, nullable=True),
    sa.Column('predir', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('pretyp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('prequal', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('sufdir', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('suftyp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('sufqual', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('linearid', sa.VARCHAR(length=22), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('paflag', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('gid', name=op.f('featnames_pkey'))
    )
    with op.batch_alter_table('featnames', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_tiger_featnames_tlid_statefp'), ['tlid', 'statefp'], unique=False)
        batch_op.create_index(batch_op.f('idx_tiger_featnames_snd_name'), [sa.literal_column('soundex(name::text)')], unique=False)
        batch_op.create_index(batch_op.f('idx_tiger_featnames_lname'), [sa.literal_column('lower(name::text)')], unique=False)

    op.create_table('tabblock',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tractce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('blockce', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('tabblock_id', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('ur', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('uace', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('awater', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.CheckConstraint("geometrytype(the_geom) = 'MULTIPOLYGON'::text OR the_geom IS NULL", name=op.f('enforce_geotype_geom')),
    sa.CheckConstraint('st_ndims(the_geom) = 2', name=op.f('enforce_dims_geom')),
    sa.CheckConstraint('st_srid(the_geom) = 4269', name=op.f('enforce_srid_geom')),
    sa.PrimaryKeyConstraint('tabblock_id', name=op.f('tabblock_pkey'))
    )
    op.create_table('state',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('region', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('division', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('statens', sa.VARCHAR(length=8), autoincrement=False, nullable=True),
    sa.Column('stusps', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('lsad', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('awater', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('statefp', name=op.f('pk_tiger_state')),
    sa.UniqueConstraint('gid', name=op.f('uidx_tiger_state_gid'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('stusps', name=op.f('uidx_tiger_state_stusps'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    with op.batch_alter_table('state', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_tiger_state_the_geom_gist'), ['the_geom'], unique=False, postgresql_using='gist')

    op.create_table('tract',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tractce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('tract_id', sa.VARCHAR(length=11), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=7), autoincrement=False, nullable=True),
    sa.Column('namelsad', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('awater', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.CheckConstraint("geometrytype(the_geom) = 'MULTIPOLYGON'::text OR the_geom IS NULL", name=op.f('enforce_geotype_geom')),
    sa.CheckConstraint('st_ndims(the_geom) = 2', name=op.f('enforce_dims_geom')),
    sa.CheckConstraint('st_srid(the_geom) = 4269', name=op.f('enforce_srid_geom')),
    sa.PrimaryKeyConstraint('tract_id', name=op.f('tract_pkey'))
    )
    op.create_table('county',
    sa.Column('gid', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('countyns', sa.VARCHAR(length=8), autoincrement=False, nullable=True),
    sa.Column('cntyidfp', sa.VARCHAR(length=5), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('namelsad', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('lsad', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('classfp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('csafp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('cbsafp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('metdivfp', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.BIGINT(), autoincrement=False, nullable=True),
    sa.Column('awater', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('cntyidfp', name=op.f('pk_tiger_county')),
    sa.UniqueConstraint('gid', name=op.f('uidx_county_gid'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    with op.batch_alter_table('county', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_tiger_county'), ['countyfp'], unique=False)

    op.create_table('geocode_settings',
    sa.Column('name', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('setting', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('unit', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('category', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('short_desc', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('name', name=op.f('geocode_settings_pkey'))
    )
    op.create_table('tabblock20',
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('countyfp', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('tractce', sa.VARCHAR(length=6), autoincrement=False, nullable=True),
    sa.Column('blockce', sa.VARCHAR(length=4), autoincrement=False, nullable=True),
    sa.Column('geoid', sa.VARCHAR(length=15), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=10), autoincrement=False, nullable=True),
    sa.Column('mtfcc', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('ur', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('uace', sa.VARCHAR(length=5), autoincrement=False, nullable=True),
    sa.Column('uatype', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('funcstat', sa.VARCHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('aland', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('awater', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('intptlat', sa.VARCHAR(length=11), autoincrement=False, nullable=True),
    sa.Column('intptlon', sa.VARCHAR(length=12), autoincrement=False, nullable=True),
    sa.Column('the_geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4269, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', _spatial_index_reflected=True), autoincrement=False, nullable=True),
    sa.Column('housing', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('pop', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('geoid', name=op.f('pk_tabblock20'))
    )
    op.create_table('zip_state_loc',
    sa.Column('zip', sa.VARCHAR(length=5), autoincrement=False, nullable=False),
    sa.Column('stusps', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('statefp', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('place', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('zip', 'stusps', 'place', name=op.f('zip_state_loc_pkey'))
    )
    op.create_table('state_lookup',
    sa.Column('st_code', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    sa.Column('abbrev', sa.VARCHAR(length=3), autoincrement=False, nullable=True),
    sa.Column('statefp', sa.CHAR(length=2), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('st_code', name=op.f('state_lookup_pkey')),
    sa.UniqueConstraint('abbrev', name=op.f('state_lookup_abbrev_key'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('name', name=op.f('state_lookup_name_key'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('statefp', name=op.f('state_lookup_statefp_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_table('zip_lookup_all',
    sa.Column('zip', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('st_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('state', sa.VARCHAR(length=2), autoincrement=False, nullable=True),
    sa.Column('co_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('county', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('cs_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('cousub', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('pl_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('place', sa.VARCHAR(length=90), autoincrement=False, nullable=True),
    sa.Column('cnt', sa.INTEGER(), autoincrement=False, nullable=True)
    )
    op.create_table('pagc_rules',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('rule', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('is_custom', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pagc_rules_pkey'))
    )
    op.create_table('pagc_lex',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('seq', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('word', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('stdword', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('token', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('is_custom', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pagc_lex_pkey'))
    )
    op.drop_table('product_ratings')
    # ### end Alembic commands ###

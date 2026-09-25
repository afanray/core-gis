from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate

class CRUDProduct:
    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[Product]:
        result = await db.execute(select(Product).where(Product.id == id))
        return result.scalars().first()

    async def get_multi(self, db: AsyncSession, active_only: bool = False) -> List[Product]:
        query = select(Product)
        if active_only:
            query = query.where(Product.is_active == True)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, obj_in: ProductCreate) -> Product:
        db_obj = Product(
            id=obj_in.id,
            title=obj_in.title,
            description=obj_in.description,
            amount=obj_in.amount,
            currency=obj_in.currency,
            billing_period=obj_in.billing_period,
            trial_days=obj_in.trial_days,
            google_play_product_id=obj_in.google_play_product_id,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(self, db: AsyncSession, db_obj: Product, obj_in: ProductUpdate) -> Product:
        update_data = obj_in.model_dump(exclude_unset=True)
        if "title" in update_data and update_data["title"] is not None:
            db_obj.title = update_data["title"]
        if "description" in update_data and update_data["description"] is not None:
            db_obj.description = update_data["description"]
        if "amount" in update_data and update_data["amount"] is not None:
            db_obj.amount = update_data["amount"]
        if "currency" in update_data and update_data["currency"] is not None:
            db_obj.currency = update_data["currency"]
        if "billing_period" in update_data and update_data["billing_period"] is not None:
            db_obj.billing_period = update_data["billing_period"]
        if "trial_days" in update_data and update_data["trial_days"] is not None:
            db_obj.trial_days = update_data["trial_days"]
        if "google_play_product_id" in update_data and update_data["google_play_product_id"] is not None:
            db_obj.google_play_product_id = update_data["google_play_product_id"]
        if "is_active" in update_data and update_data["is_active"] is not None:
            db_obj.is_active = update_data["is_active"]
            
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, id: str) -> bool:
        product = await self.get_by_id(db, id)
        if product:
            await db.delete(product)
            await db.commit()
            return True
        return False

crud_product = CRUDProduct()

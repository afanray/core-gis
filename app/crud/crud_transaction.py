from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, desc, asc
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate

class CRUDTransaction:
    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[Transaction]:
        result = await db.execute(select(Transaction).where(Transaction.id == id))
        return result.scalars().first()

    async def get_by_user_email(self, db: AsyncSession, user_email: str) -> List[Transaction]:
        result = await db.execute(
            select(Transaction)
            .where(Transaction.user_email == user_email)
            .order_by(desc(Transaction.created_at))
        )
        return list(result.scalars().all())

    async def get_filtered(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        status: Optional[str] = None,
        product_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "createdAt",
        order: str = "desc"
    ) -> Tuple[List[Transaction], int]:
        query = select(Transaction)
        count_query = select(func.count(Transaction.id))

        filters = []
        if q:
            search = f"%{q}%"
            filters.append(
                or_(
                    Transaction.user_name.ilike(search),
                    Transaction.user_email.ilike(search),
                    Transaction.id.ilike(search),
                    Transaction.name.ilike(search)
                )
            )
        if status and status.lower() != "all":
            filters.append(Transaction.status == status)
        if product_id and product_id.lower() != "all":
            filters.append(Transaction.product_id == product_id)
        if start_date:
            try:
                dt_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                filters.append(Transaction.created_at >= dt_start)
            except Exception:
                pass
        if end_date:
            try:
                dt_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                filters.append(Transaction.created_at <= dt_end)
            except Exception:
                pass

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        # Sorting
        sort_column = Transaction.created_at
        if sort_by == "amount":
            sort_column = Transaction.amount
        elif sort_by == "userName":
            sort_column = Transaction.user_name

        if order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        # Count total records
        total_result = await db.execute(count_query)
        total = total_result.scalar_one_or_none() or 0

        # Execute paginated query
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def create(self, db: AsyncSession, obj_in: TransactionCreate, tx_id: Optional[str] = None) -> Transaction:
        import uuid
        final_id = tx_id or f"TX-{uuid.uuid4().hex[:8].upper()}"
        db_obj = Transaction(
            id=final_id,
            product_id=obj_in.productId,
            name=obj_in.name,
            amount=obj_in.amount,
            currency=obj_in.currency,
            status=obj_in.status,
            user_name=obj_in.userName,
            user_email=obj_in.userEmail,
            order_id=obj_in.orderId,
            purchase_token=obj_in.purchaseToken,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update_status(self, db: AsyncSession, tx: Transaction, new_status: str) -> Transaction:
        tx.status = new_status
        await db.commit()
        await db.refresh(tx)
        return tx

    async def delete(self, db: AsyncSession, id: str) -> bool:
        tx = await self.get_by_id(db, id)
        if tx:
            await db.delete(tx)
            await db.commit()
            return True
        return False

crud_transaction = CRUDTransaction()

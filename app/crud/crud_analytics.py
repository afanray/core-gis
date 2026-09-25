from typing import Dict, List, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, extract
from app.models.transaction import Transaction

class CRUDAnalytics:
    async def get_overview(self, db: AsyncSession) -> Dict[str, Any]:
        # Filter for successful transactions
        success_filter = Transaction.status == "Success"

        # Total support and count
        total_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0.0).label("totalSupport"),
            func.count(Transaction.id).label("totalCount")
        ).where(success_filter)
        
        total_res = await db.execute(total_stmt)
        total_row = total_res.first()
        total_support = float(total_row.totalSupport) if total_row else 0.0
        total_count = int(total_row.totalCount) if total_row else 0

        avg_support = total_support / total_count if total_count > 0 else 0.0

        # Current month (July 2026 for simulation, or active current month)
        # Let's filter for current month in 2026 or calendar month
        now = datetime.now(timezone.utc)
        current_year = 2026
        current_month = 7  # July
        
        month_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0.0).label("monthSupport")
        ).where(
            success_filter,
            extract("year", Transaction.created_at) == current_year,
            extract("month", Transaction.created_at) == current_month
        )
        month_res = await db.execute(month_stmt)
        month_row = month_res.first()
        current_month_support = float(month_row.monthSupport) if month_row else 0.0

        return {
            "totalSupport": total_support,
            "totalCount": total_count,
            "currentMonthSupport": current_month_support,
            "averageSupport": avg_support
        }

    async def get_monthly_trends(self, db: AsyncSession) -> List[Dict[str, Any]]:
        # Group successful transactions by month
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        stmt = select(
            extract("month", Transaction.created_at).label("month_idx"),
            extract("year", Transaction.created_at).label("year_val"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("sum_amount"),
            func.count(Transaction.id).label("count_tx")
        ).where(
            Transaction.status == "Success"
        ).group_by(
            extract("year", Transaction.created_at),
            extract("month", Transaction.created_at)
        ).order_by(
            extract("year", Transaction.created_at),
            extract("month", Transaction.created_at)
        )

        res = await db.execute(stmt)
        rows = res.all()
        
        results = []
        for r in rows:
            m_idx = int(r.month_idx) - 1
            y_val = int(r.year_val)
            m_name = month_names[m_idx] if 0 <= m_idx < 12 else str(m_idx)
            results.append({
                "month": m_name,
                "year": y_val,
                "totalSupport": float(r.sum_amount),
                "totalCount": int(r.count_tx)
            })

        return results

    async def get_product_stats(self, db: AsyncSession) -> List[Dict[str, Any]]:
        labels = {
            "support_10000": "Rp10.000 (Kopi)",
            "support_25000": "Rp25.000 (Camilan)",
            "support_50000": "Rp50.000 (Makan Siang)",
            "support_100000": "Rp100.000 (Premium)",
        }
        stmt = select(
            Transaction.product_id,
            func.count(Transaction.id).label("count_tx"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("sum_amount")
        ).where(
            Transaction.status == "Success"
        ).group_by(Transaction.product_id)

        res = await db.execute(stmt)
        rows = res.all()

        results = []
        found_pids = set()
        for r in rows:
            pid = str(r.product_id)
            found_pids.add(pid)
            lbl = labels.get(pid, f"Produk {pid}")
            results.append({
                "productId": pid,
                "label": lbl,
                "count": int(r.count_tx),
                "sum": float(r.sum_amount)
            })

        # Fill default product packages if missing
        for pid, lbl in labels.items():
            if pid not in found_pids:
                results.append({
                    "productId": pid,
                    "label": lbl,
                    "count": 0,
                    "sum": 0.0
                })

        return results

    async def get_status_distribution(self, db: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(
            Transaction.status,
            func.count(Transaction.id).label("count_tx")
        ).group_by(Transaction.status)

        res = await db.execute(stmt)
        rows = res.all()

        total = sum(int(r.count_tx) for r in rows)
        results = []
        for r in rows:
            cnt = int(r.count_tx)
            pct = round((cnt / total) * 100, 2) if total > 0 else 0.0
            results.append({
                "status": str(r.status),
                "count": cnt,
                "percentage": pct
            })

        return results

crud_analytics = CRUDAnalytics()

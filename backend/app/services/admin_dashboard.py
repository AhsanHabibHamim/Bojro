"""Explicit Bangladesh-local admin dashboard metric definitions."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.enums import OrderStatus, PaymentStatus, ProductStatus, UserRole
from app.db.models import Order, OrderItem, Product, ProductVariant, User
from app.schemas.admin_commerce import (
    DashboardLowStock,
    DashboardResponse,
    DashboardSeriesPoint,
    DashboardStatusMetric,
    DashboardTopProduct,
)

_DHAKA = ZoneInfo("Asia/Dhaka")
_FULFILLED = {OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.COMPLETED}
_GROSS_EXCLUDED = {
    OrderStatus.CANCELLED,
    OrderStatus.RETURNED,
    OrderStatus.REFUNDED,
}


class AdminDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def metrics(
        self,
        from_date: date,
        to_date: date,
        bucket: str,
        low_stock_threshold: int,
    ) -> DashboardResponse:
        start = datetime.combine(from_date, time.min, _DHAKA).astimezone(UTC)
        end = datetime.combine(to_date + timedelta(days=1), time.min, _DHAKA).astimezone(UTC)
        orders = list(
            await self._session.scalars(
                select(Order)
                .where(Order.placed_at >= start, Order.placed_at < end)
                .order_by(Order.placed_at, Order.id)
            )
        )
        gross_orders = [order for order in orders if order.status not in _GROSS_EXCLUDED]
        fulfilled_orders = [
            order
            for order in orders
            if order.status in _FULFILLED and order.payment_status == PaymentStatus.PAID
        ]
        series: dict[date, list[Order]] = defaultdict(list)
        for order in orders:
            series[_bucket_date(order.placed_at.astimezone(_DHAKA).date(), bucket)].append(order)
        bucket_keys = sorted(
            {
                _bucket_date(from_date + timedelta(days=offset), bucket)
                for offset in range((to_date - from_date).days + 1)
            }
        )
        points = [
            DashboardSeriesPoint(
                bucket=key,
                gross_sales_poisha=sum(
                    order.grand_total for order in values if order.status not in _GROSS_EXCLUDED
                ),
                recognized_revenue_poisha=sum(
                    order.grand_total
                    for order in values
                    if order.status in _FULFILLED and order.payment_status == PaymentStatus.PAID
                ),
                order_count=len(values),
            )
            for key in bucket_keys
            for values in [series.get(key, [])]
        ]
        statuses = {status: 0 for status in OrderStatus}
        for order in orders:
            statuses[order.status] += 1
        new_customers = int(
            await self._session.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.CUSTOMER,
                    User.is_guest.is_(False),
                    User.created_at >= start,
                    User.created_at < end,
                )
            )
            or 0
        )
        active_customers = int(
            await self._session.scalar(
                select(func.count(func.distinct(Order.user_id))).where(
                    Order.placed_at >= start, Order.placed_at < end
                )
            )
            or 0
        )
        top_products = await self._top_products([order.id for order in fulfilled_orders])
        low_stock = await self._low_stock(low_stock_threshold)
        return DashboardResponse(
            from_date=from_date,
            to_date=to_date,
            timezone="Asia/Dhaka",
            bucket=bucket,
            gross_sales_poisha=sum(order.grand_total for order in gross_orders),
            recognized_revenue_poisha=sum(order.grand_total for order in fulfilled_orders),
            order_count=len(orders),
            new_customer_count=new_customers,
            active_customer_count=active_customers,
            series=points,
            orders_by_status=[
                DashboardStatusMetric(status=status, count=statuses[status])
                for status in OrderStatus
            ],
            top_products=top_products,
            low_stock_variants=low_stock,
            generated_at=datetime.now(UTC),
        )

    async def _top_products(self, order_ids: list[object]) -> list[DashboardTopProduct]:
        if not order_ids:
            return []
        rows = (
            await self._session.execute(
                select(
                    OrderItem.product_id,
                    OrderItem.name_bn,
                    OrderItem.name_en,
                    func.sum(OrderItem.quantity),
                    func.sum(OrderItem.line_total),
                )
                .where(OrderItem.order_id.in_(order_ids))
                .group_by(OrderItem.product_id, OrderItem.name_bn, OrderItem.name_en)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(10)
            )
        ).all()
        return [
            DashboardTopProduct(
                product_id=row[0],
                name_bn=row[1],
                name_en=row[2],
                fulfilled_quantity=int(row[3]),
                revenue_poisha=int(row[4]),
            )
            for row in rows
        ]

    async def _low_stock(self, threshold: int) -> list[DashboardLowStock]:
        variants = list(
            await self._session.scalars(
                select(ProductVariant)
                .join(Product, Product.id == ProductVariant.product_id)
                .options(selectinload(ProductVariant.product))
                .where(
                    Product.status == ProductStatus.ACTIVE,
                    ProductVariant.is_active.is_(True),
                    ProductVariant.stock_on_hand - ProductVariant.stock_reserved <= threshold,
                )
                .order_by(
                    ProductVariant.stock_on_hand - ProductVariant.stock_reserved,
                    ProductVariant.id,
                )
                .limit(50)
            )
        )
        return [
            DashboardLowStock(
                product_id=variant.product_id,
                variant_id=variant.id,
                sku=variant.sku,
                name_bn=variant.product.name_bn,
                name_en=variant.product.name_en,
                available_stock=max(0, variant.stock_on_hand - variant.stock_reserved),
            )
            for variant in variants
        ]


def _bucket_date(value: date, bucket: str) -> date:
    if bucket == "day":
        return value
    if bucket == "week":
        return value - timedelta(days=value.weekday())
    return value.replace(day=1)

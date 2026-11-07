from app.core.config import Settings
from app.main import create_app


def test_phase5_openapi_has_complete_frozen_surface(test_settings: Settings) -> None:
    schema = create_app(test_settings).openapi()
    paths = schema["paths"]
    expected = {
        "/api/v1/admin/auth/login",
        "/api/v1/admin/auth/totp/verify",
        "/api/v1/admin/auth/session",
        "/api/v1/admin/auth/refresh",
        "/api/v1/admin/auth/logout",
        "/api/v1/admin/auth/logout-all",
        "/api/v1/admin/auth/password/change",
        "/api/v1/admin/auth/totp/setup",
        "/api/v1/admin/auth/totp/confirm",
        "/api/v1/admin/auth/totp/disable",
        "/api/v1/admin/dashboard/metrics",
        "/api/v1/admin/products",
        "/api/v1/admin/products/{product_id}",
        "/api/v1/admin/products/{product_id}/variants",
        "/api/v1/admin/products/{product_id}/variants/{variant_id}",
        "/api/v1/admin/products/{product_id}/variants/{variant_id}/stock-adjustments",
        "/api/v1/admin/products/{product_id}/images",
        "/api/v1/admin/products/{product_id}/images/{image_id}",
        "/api/v1/admin/products/{product_id}/images/order",
        "/api/v1/admin/products/imports/validate",
        "/api/v1/admin/products/imports",
        "/api/v1/admin/products/imports/{import_id}",
        "/api/v1/admin/products/export.csv",
        "/api/v1/admin/categories",
        "/api/v1/admin/categories/{category_id}",
        "/api/v1/admin/categories/order",
        "/api/v1/admin/brands",
        "/api/v1/admin/brands/{brand_id}",
        "/api/v1/admin/orders",
        "/api/v1/admin/orders/{order_id}",
        "/api/v1/admin/orders/{order_id}/status",
        "/api/v1/admin/orders/{order_id}/notes",
        "/api/v1/admin/orders/{order_id}/shipments",
        "/api/v1/admin/orders/courier-capabilities",
        "/api/v1/admin/orders/{order_id}/invoice.pdf",
        "/api/v1/admin/orders/{order_id}/packing-slip.pdf",
        "/api/v1/admin/customers",
        "/api/v1/admin/customers/{customer_id}",
        "/api/v1/admin/customers/{customer_id}/status",
        "/api/v1/admin/customers/{customer_id}/orders",
        "/api/v1/admin/reviews",
        "/api/v1/admin/reviews/{review_id}",
        "/api/v1/admin/reviews/{review_id}/moderation",
        "/api/v1/admin/coupons",
        "/api/v1/admin/coupons/{coupon_id}",
        "/api/v1/admin/flash-sales",
        "/api/v1/admin/flash-sales/{sale_id}",
        "/api/v1/admin/homepage-sections",
        "/api/v1/admin/homepage-sections/{section_id}",
        "/api/v1/admin/homepage-sections/order",
        "/api/v1/admin/banners",
        "/api/v1/admin/banners/{banner_id}",
        "/api/v1/admin/banners/order",
        "/api/v1/admin/pages",
        "/api/v1/admin/pages/{page_id}",
        "/api/v1/admin/pages/{page_id}/publish",
        "/api/v1/admin/pages/{page_id}/unpublish",
        "/api/v1/admin/blog-posts",
        "/api/v1/admin/blog-posts/{post_id}",
        "/api/v1/admin/blog-posts/{post_id}/publish",
        "/api/v1/admin/blog-posts/{post_id}/unpublish",
        "/api/v1/admin/settings",
        "/api/v1/admin/settings/{section}",
        "/api/v1/admin/media",
        "/api/v1/admin/media/uploads",
        "/api/v1/admin/media/uploads/{upload_id}/complete",
        "/api/v1/admin/media/uploads/{upload_id}",
        "/api/v1/admin/media/{asset_id}",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/audit-logs/{audit_id}",
        "/api/v1/content/pages/{slug}",
        "/api/v1/content/blog",
        "/api/v1/content/blog/{slug}",
    }
    assert not (expected - set(paths))

    operation_ids: list[str] = []
    for path, item in paths.items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_ids.append(operation["operationId"])
            if path.startswith("/api/v1/admin"):
                success = next(
                    response
                    for code, response in operation["responses"].items()
                    if str(code).startswith("2")
                )
                assert "Cache-Control" in success.get("headers", {})
    assert len(operation_ids) == len(set(operation_ids))

    schemes = schema["components"]["securitySchemes"]
    assert schemes["AdminAccessCookie"]["name"] == "__Host-bojro_admin_access"
    assert schemes["AdminRefreshCookie"]["name"] == "__Secure-bojro_admin_refresh"


def test_phase5_openapi_marks_command_and_concurrency_headers_required(
    test_settings: Settings,
) -> None:
    schema = create_app(test_settings).openapi()
    checked_commands = 0
    checked_updates = 0
    for path, item in schema["paths"].items():
        if not path.startswith("/api/v1/admin/"):
            continue
        for method, operation in item.items():
            if method not in {"post", "put", "patch", "delete"}:
                continue
            parameters = {
                parameter["name"]: parameter
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "header"
            }
            if "Idempotency-Key" in parameters:
                checked_commands += 1
                assert parameters["Idempotency-Key"]["required"] is True
                responses = operation["responses"]
                success = next(
                    response for code, response in responses.items() if str(code).startswith("2")
                )
                assert "Idempotent-Replayed" in success["headers"]
            if "If-Match" in parameters:
                checked_updates += 1
                assert parameters["If-Match"]["required"] is True
                assert "412" in operation["responses"]
                assert "428" in operation["responses"]
    assert checked_commands >= 35
    assert checked_updates >= 25

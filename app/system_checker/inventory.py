"""
E-FLORA Discovered Feature Inventory and Coverage Matrix Registry.

Derived directly from the codebase inspection across:
- Flask blueprints: auth, customer, seller, rider, admin, checkout, archive, cloudinary, chat, store_admin
- Database models in app/models.py
- Services in app/utils/ (SMS, Email, Push, Reports, Geocoding, Schedule, Controls)
- Templates and UI workflows in app/templates/
- Flutter mobile application in eflowers_app/
"""

from typing import Dict, List, Any

FEATURE_INVENTORY: List[Dict[str, Any]] = [
    # ==========================================
    # 1. AUTHENTICATION & SECURITY
    # ==========================================
    {
        "id": "auth_customer_otp_registration",
        "module": "Authentication & Security",
        "name": "Customer Email OTP Registration",
        "description": "6-digit OTP generation, delivery via Gmail OAuth2/SendGrid, 10-minute expiry, cooldown resend, and verification before customer account creation.",
        "roles": ["customer"],
        "endpoints": [
            "POST /api/v1/auth/customer/send-otp",
            "POST /api/v1/auth/customer/resend-otp",
            "POST /api/v1/auth/customer/verify-otp",
            "POST /api/v1/auth/customer/register"
        ],
        "models": ["CustomerOTP", "User"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_customer_otp_registration_flow"
    },
    {
        "id": "auth_password_reset_otp",
        "module": "Authentication & Security",
        "name": "Password Reset via OTP (Email/SMS)",
        "description": "Password reset flow with OTP dispatch, verification check, password hash updating with Werkzeug security, and OTP token invalidation.",
        "roles": ["customer", "seller", "rider", "admin"],
        "endpoints": [
            "POST /api/v1/auth/forgot-password/send-otp",
            "POST /api/v1/auth/forgot-password/resend-otp",
            "POST /api/v1/auth/forgot-password/verify-otp",
            "POST /api/v1/auth/forgot-password/reset"
        ],
        "models": ["PasswordResetOTP", "User"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_password_reset_otp_flow"
    },
    {
        "id": "auth_phone_binding_sms",
        "module": "Authentication & Security",
        "name": "Phone Binding & SMS Verification",
        "description": "Philippine mobile number validation, Smart/TNT/Globe prefix detection, smart carrier routing (sms8.io/iProg), and OTP confirmation before updating profile phone.",
        "roles": ["customer", "seller", "rider"],
        "endpoints": [
            "POST /api/v1/auth/profile/phone/send-otp",
            "POST /api/v1/auth/profile/phone/verify"
        ],
        "models": ["User", "SystemControl"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_phone_binding_and_sms_routing"
    },
    {
        "id": "auth_login_jwt_session",
        "module": "Authentication & Security",
        "name": "User Authentication & Session/JWT Issuance",
        "description": "Login authentication by email or phone, password verification, active ban inspection, JWT access/refresh token generation, and web session cookie management.",
        "roles": ["customer", "seller", "rider", "admin", "store_admin"],
        "endpoints": [
            "POST /api/v1/auth/login",
            "GET /api/v1/auth/me",
            "GET /login",
            "GET /logout"
        ],
        "models": ["User", "AccountBan"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_login_and_token_generation"
    },
    {
        "id": "auth_account_ban_enforcement",
        "module": "Authentication & Security",
        "name": "Account Ban & Access Restriction",
        "description": "Admin capability to place active bans with reason/duration on users, rejecting authentication attempts with clear ban message until unbanned.",
        "roles": ["admin"],
        "endpoints": [
            "POST /api/admin/users/<id>/ban",
            "POST /api/admin/users/<id>/unban",
            "GET /api/admin/users/bans"
        ],
        "models": ["AccountBan", "User"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_account_ban_and_unban_enforcement"
    },
    {
        "id": "auth_role_permissions_rbac",
        "module": "Authentication & Security",
        "name": "Role-Based Access Control (RBAC)",
        "description": "Enforcement of role separation (admin, seller, store_admin, rider, customer) preventing unauthorized privilege escalation across protected endpoints.",
        "roles": ["admin", "seller", "rider", "customer"],
        "endpoints": [
            "GET /api/v1/admin/*",
            "GET /api/v1/seller/*",
            "GET /api/v1/rider/*"
        ],
        "models": ["User", "StoreAdmin"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_role_based_access_control"
    },
    {
        "id": "auth_account_deletion_cascade",
        "module": "Authentication & Security",
        "name": "Account Deletion with Integrity Preservation",
        "description": "Safe customer account deletion with proper anonymization or cascade handling without leaving dangling foreign key references.",
        "roles": ["customer"],
        "endpoints": ["POST /api/v1/auth/account/delete"],
        "models": ["User", "Cart", "UserAddress", "WishlistItem"],
        "has_test": True,
        "test_suite": "test_auth_security",
        "test_function": "test_account_deletion_safety"
    },

    # ==========================================
    # 2. CUSTOMER & STOREFRONT MODULE
    # ==========================================
    {
        "id": "customer_catalog_search_filters",
        "module": "Customer Module",
        "name": "Product Catalog, Search, and Filtering",
        "description": "Product browsing with keyword search, category filtering, price range sorting (asc/desc/newest/popular), and store availability checks.",
        "roles": ["customer"],
        "endpoints": [
            "GET /api/v1/customer/products",
            "GET /api/v1/customer/products/<id>",
            "GET /api/v1/customer/categories",
            "GET /api/v1/customer/stores"
        ],
        "models": ["Product", "Category", "Store", "ProductVariant"],
        "has_test": True,
        "test_suite": "test_customer_storefront",
        "test_function": "test_product_catalog_and_filtering"
    },
    {
        "id": "customer_cart_operations",
        "module": "Customer Module",
        "name": "Cart Management & Stock Validation",
        "description": "Cart creation, adding product/variants, quantity bounds enforcement, real-time stock availability verification, and item/addon removal.",
        "roles": ["customer"],
        "endpoints": [
            "GET /api/v1/customer/cart",
            "POST /api/v1/customer/cart/items",
            "PUT /api/v1/customer/cart/items/<id>",
            "DELETE /api/v1/customer/cart/items/<id>",
            "POST /api/v1/customer/cart/clear"
        ],
        "models": ["Cart", "CartItem", "Product", "ProductVariant"],
        "has_test": True,
        "test_suite": "test_customer_storefront",
        "test_function": "test_cart_operations_and_bounds"
    },
    {
        "id": "customer_product_addons",
        "module": "Customer Module",
        "name": "Floral Addons & Custom Options",
        "description": "Attaching addon options (wrapping paper, chocolates, teddy bears, greeting cards) to cart items with correct price accumulation.",
        "roles": ["customer"],
        "endpoints": [
            "POST /api/v1/customer/cart/items",
            "DELETE /api/v1/customer/cart/items/<id>/addons/<addon_id>"
        ],
        "models": ["ProductAddonGroup", "ProductAddonOption", "CartItemAddon"],
        "has_test": True,
        "test_suite": "test_customer_storefront",
        "test_function": "test_product_addon_calculations"
    },
    {
        "id": "customer_wishlist_management",
        "module": "Customer Module",
        "name": "Customer Wishlist",
        "description": "Adding/removing products from user wishlist, querying wishlist status, and preventing duplicate wishlist items.",
        "roles": ["customer"],
        "endpoints": [
            "GET /api/v1/customer/wishlist",
            "POST /api/v1/customer/wishlist/toggle",
            "DELETE /api/v1/customer/wishlist/<id>"
        ],
        "models": ["WishlistItem", "Product"],
        "has_test": True,
        "test_suite": "test_customer_storefront",
        "test_function": "test_wishlist_toggle_and_retrieval"
    },
    {
        "id": "customer_address_laguna_geo",
        "module": "Customer Module",
        "name": "Saved Addresses & Laguna Location Handling",
        "description": "Managing customer delivery addresses, default address toggle, Laguna municipality/barangay resolution, and coordinate storage.",
        "roles": ["customer"],
        "endpoints": [
            "GET /api/account/addresses",
            "POST /api/account/addresses",
            "PUT /api/account/addresses/<id>/set-default",
            "DELETE /api/account/addresses/<id>"
        ],
        "models": ["UserAddress", "MunicipalityBoundary"],
        "has_test": True,
        "test_suite": "test_customer_storefront",
        "test_function": "test_customer_address_management"
    },
    {
        "id": "customer_ratings_and_reviews",
        "module": "Customer Module",
        "name": "Order, Product, and Store Ratings",
        "description": "Submitting 1-5 star ratings and reviews for completed orders, updating store and product average rating metrics.",
        "roles": ["customer"],
        "endpoints": [
            "POST /api/v1/customer/orders/<id>/rate",
            "GET /api/v1/customer/orders/<id>/ratings",
            "GET /api/v1/customer/products/<id>/ratings"
        ],
        "models": ["ProductRating", "StoreRating", "Order"],
        "has_test": True,
        "test_suite": "test_customer_storefront",
        "test_function": "test_ratings_submission_and_averages"
    },

    # ==========================================
    # 3. SELLER & STORE OPERATIONS MODULE
    # ==========================================
    {
        "id": "seller_store_settings_schedule",
        "module": "Seller & Store Management",
        "name": "Store Profile, Schedule, and Delivery Settings",
        "description": "Configuring store bio, operating hours via store_schedule.py, delivery radiuses, pickup availability, and GCash payment QR upload.",
        "roles": ["seller"],
        "endpoints": [
            "GET /api/seller/store/settings",
            "POST /api/seller/store/settings",
            "POST /api/v1/cloudinary/store/<id>/gcash-qr"
        ],
        "models": ["Store", "StorePaymentSetting", "GCashQR"],
        "has_test": True,
        "test_suite": "test_seller_store",
        "test_function": "test_store_settings_and_schedule"
    },
    {
        "id": "seller_product_variant_crud",
        "module": "Seller & Store Management",
        "name": "Product & Variant Management",
        "description": "Creating and updating flower arrangements, price setting, SKU/stock levels, variant combinations (colors, sizes), and addon associations.",
        "roles": ["seller", "store_admin"],
        "endpoints": [
            "GET /api/v1/seller/products",
            "POST /api/v1/seller/products",
            "POST /api/seller/variants/create",
            "PUT /api/seller/variants/<id>"
        ],
        "models": ["Product", "ProductVariant", "ProductImage"],
        "has_test": True,
        "test_suite": "test_seller_store",
        "test_function": "test_product_and_variant_crud"
    },
    {
        "id": "seller_product_archival",
        "module": "Seller & Store Management",
        "name": "Product Archival & Safe Restoration",
        "description": "Soft-archiving inactive products, restoring archived items, and permanent deletion with order history protection.",
        "roles": ["seller", "store_admin"],
        "endpoints": [
            "POST /api/v1/seller/archive/products/<id>/archive",
            "POST /api/v1/seller/archive/products/<id>/restore",
            "DELETE /api/v1/seller/archive/products/<id>/permanent-delete",
            "GET /api/v1/seller/archive/stats"
        ],
        "models": ["Product"],
        "has_test": True,
        "test_suite": "test_seller_store",
        "test_function": "test_product_archiving_and_restoration"
    },
    {
        "id": "seller_pos_custom_orders",
        "module": "Seller & Store Management",
        "name": "Point of Sale (POS) & Walk-In Invoicing",
        "description": "In-store POS counter orders, instant inventory adjustment, custom floral inclusions, dedicated printed receipt format.",
        "roles": ["seller", "store_admin"],
        "endpoints": [
            "GET /seller/pos",
            "POST /api/seller/pos/orders",
            "GET /api/seller/pos/next-order-id"
        ],
        "models": ["POSOrder", "POSOrderItem", "Product"],
        "has_test": True,
        "test_suite": "test_seller_store",
        "test_function": "test_pos_order_creation_and_inventory"
    },
    {
        "id": "seller_store_admins_rbac",
        "module": "Seller & Store Management",
        "name": "Store Staff (Store Admin) Delegation & Permissions",
        "description": "Inviting staff via StoreAdminOTP, assigning granular permissions (products, orders, POS, inventory, reports), and permission enforcement.",
        "roles": ["seller"],
        "endpoints": [
            "GET /api/seller/admins",
            "POST /api/seller/admins",
            "PUT /api/seller/admins/<id>/permissions",
            "PUT /api/seller/admins/<id>/status"
        ],
        "models": ["StoreAdmin", "StoreAdminOTP", "User"],
        "has_test": True,
        "test_suite": "test_seller_store",
        "test_function": "test_store_admin_invitation_and_permissions"
    },
    {
        "id": "seller_application_onboarding",
        "module": "Seller & Store Management",
        "name": "Seller Onboarding Application & Approval",
        "description": "Customer submitting seller application with business permits, administrator review, approval converting role to seller, or rejection with remarks.",
        "roles": ["customer", "admin"],
        "endpoints": [
            "POST /api/v1/customer/seller-application",
            "GET /api/v1/customer/seller-application",
            "POST /api/admin/seller-applications/<id>/approve",
            "POST /api/admin/seller-applications/<id>/reject"
        ],
        "models": ["SellerApplication", "Store", "User"],
        "has_test": True,
        "test_suite": "test_seller_store",
        "test_function": "test_seller_application_lifecycle"
    },

    # ==========================================
    # 4. RIDER & DELIVERY MODULE
    # ==========================================
    {
        "id": "rider_invitation_onboarding",
        "module": "Rider & Delivery",
        "name": "Rider Invitation & Account Setup",
        "description": "Seller inviting rider by mobile number, SMS/email OTP dispatch, rider credential setup, and activation.",
        "roles": ["seller", "rider"],
        "endpoints": [
            "POST /api/seller/riders",
            "POST /api/seller/riders/verify-otp",
            "POST /api/rider/set-password",
            "PUT /api/seller/riders/<id>/status"
        ],
        "models": ["Rider", "RiderOTP", "User"],
        "has_test": True,
        "test_suite": "test_rider_delivery",
        "test_function": "test_rider_invitation_and_setup"
    },
    {
        "id": "rider_order_assignment_workflow",
        "module": "Rider & Delivery",
        "name": "Rider Order Assignment & Acceptance",
        "description": "Store assigning ready order to store rider, rider querying available/assigned jobs, and accepting delivery assignment.",
        "roles": ["seller", "rider"],
        "endpoints": [
            "GET /api/v1/rider/orders",
            "GET /api/v1/rider/orders/available",
            "POST /api/v1/rider/orders/<id>/accept"
        ],
        "models": ["Order", "Rider"],
        "has_test": True,
        "test_suite": "test_rider_delivery",
        "test_function": "test_rider_assignment_and_acceptance"
    },
    {
        "id": "rider_delivery_status_and_pod",
        "module": "Rider & Delivery",
        "name": "Delivery Execution & Proof of Delivery (POD)",
        "description": "Transitioning order from accepted to out_for_delivery, uploading Proof of Delivery photo to Cloudinary, and marking delivery completed.",
        "roles": ["rider"],
        "endpoints": [
            "PUT /api/v1/rider/orders/<id>/update-status",
            "POST /api/v1/rider/orders/<id>/upload-delivery-proof"
        ],
        "models": ["Order", "Rider"],
        "has_test": True,
        "test_suite": "test_rider_delivery",
        "test_function": "test_delivery_progression_and_pod"
    },
    {
        "id": "rider_gps_realtime_tracking",
        "module": "Rider & Delivery",
        "name": "Real-time Rider GPS Tracking",
        "description": "Rider mobile device streaming coordinates via POST /location, RiderLocation spatial POINT storage, and customer live tracking view.",
        "roles": ["rider", "customer"],
        "endpoints": [
            "POST /api/v1/rider/location",
            "GET /api/v1/rider/location/history",
            "GET /api/v1/customer/orders/<id>/tracking"
        ],
        "models": ["RiderLocation", "Order"],
        "has_test": True,
        "test_suite": "test_rider_delivery",
        "test_function": "test_rider_gps_location_tracking"
    },

    # ==========================================
    # 5. ORDERS, CHECKOUT & INVENTORY
    # ==========================================
    {
        "id": "orders_multi_store_checkout",
        "module": "Orders & Inventory",
        "name": "Multi-Store Order Creation & Price Computation",
        "description": "Splitting customer cart across multiple stores into distinct store orders, calculating subtotals, delivery fees, and grand total correctly.",
        "roles": ["customer"],
        "endpoints": [
            "POST /api/v1/checkout/create-orders",
            "POST /api/v1/checkout/buy-now/create-order",
            "GET /api/v1/checkout/active-order-limit"
        ],
        "models": ["Order", "OrderItem", "OrderItemAddon"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_order_pricing_and_store_splitting"
    },
    {
        "id": "orders_stock_reduction_and_restoration",
        "module": "Orders & Inventory",
        "name": "Stock Deductions & Cancellation Restoration",
        "description": "Immediate stock quantity reduction upon checkout, tracking in StockReduction, and automatic inventory restoration when an order is cancelled or rejected.",
        "roles": ["system", "customer", "seller"],
        "endpoints": [
            "POST /api/v1/checkout/create-orders",
            "POST /api/v1/customer/orders/<id>/cancel",
            "PUT /api/seller/orders/<id>/status"
        ],
        "models": ["Product", "ProductVariant", "StockReduction", "Order"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_stock_reduction_and_restoration"
    },
    {
        "id": "orders_overselling_prevention",
        "module": "Orders & Inventory",
        "name": "Overselling Prevention & Pre-Checkout Validation",
        "description": "Validation ensuring requested quantities do not exceed available inventory before proceeding with order placement.",
        "roles": ["customer"],
        "endpoints": [
            "POST /api/v1/checkout/validate-stock",
            "POST /api/v1/checkout/validate"
        ],
        "models": ["Product", "ProductVariant"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_overselling_prevention"
    },
    {
        "id": "orders_valid_status_state_machine",
        "module": "Orders & Inventory",
        "name": "Order Status Lifecycle State Machine",
        "description": "Validating permissible status transitions (pending -> accepted -> preparing -> ready -> out_for_delivery -> completed) and blocking invalid jumps.",
        "roles": ["seller", "rider", "customer"],
        "endpoints": [
            "PUT /api/seller/orders/<id>/status",
            "PUT /api/v1/rider/orders/<id>/update-status"
        ],
        "models": ["Order"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_order_status_state_machine"
    },
    {
        "id": "inventory_weighted_moving_average_costing",
        "module": "Orders & Inventory",
        "name": "Weighted Moving Average Costing (AVCO)",
        "description": "Blended weighted average cost calculations on stock replenishment, 0-stock baseline reset, and unit cost tracking in StockReduction.",
        "roles": ["seller", "system"],
        "endpoints": [
            "POST /api/seller/inventory/add-stock",
            "POST /seller/products/add"
        ],
        "models": ["Product", "ProductVariant", "StockReduction"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_weighted_moving_average_inventory_costing"
    },
    {
        "id": "financials_cogs_profit_margin_calculation",
        "module": "Payments & Financials",
        "name": "COGS, Gross Profit & Margin Reporting",
        "description": "Calculation of Cost of Goods Sold, Gross Profit, and Gross Profit Margin % across seller and admin financial reports with 60% fallback basis.",
        "roles": ["seller", "admin"],
        "endpoints": [
            "GET /reports",
            "GET /api/v1/admin/analytics"
        ],
        "models": ["OrderItem", "POSOrderItem", "OrderItemAddon"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_profit_margin_and_cogs_calculation"
    },
    {
        "id": "orders_cost_snapshotting",
        "module": "Orders & Inventory",
        "name": "Order Item Wholesale Cost Snapshotting",
        "description": "Freezing cost price on order items, POS items, and add-ons at time of purchase to ensure historical profit margins are immutable.",
        "roles": ["system", "customer", "seller"],
        "endpoints": [
            "POST /api/v1/checkout/create-orders",
            "POST /api/v1/checkout/buy-now/create-order",
            "POST /api/seller/pos/create-order"
        ],
        "models": ["OrderItem", "POSOrderItem", "OrderItemAddon"],
        "has_test": True,
        "test_suite": "test_orders_inventory",
        "test_function": "test_order_item_cost_snapshotting"
    },

    # ==========================================
    # 6. PAYMENTS & FINANCIALS
    # ==========================================
    {
        "id": "payments_gcash_receipt_verification",
        "module": "Payments & Financials",
        "name": "GCash Receipt Upload & Seller Verification",
        "description": "Customer uploading GCash receipt proof, status set to pending_verification, seller review, acceptance marking order paid or rejection requesting reupload.",
        "roles": ["customer", "seller"],
        "endpoints": [
            "POST /api/v1/checkout/order/<id>/payment-proof",
            "GET /api/v1/seller/payments/pending",
            "POST /api/v1/seller/payments/order/<id>/verify",
            "POST /api/v1/seller/payments/order/<id>/reject"
        ],
        "models": ["Order"],
        "has_test": True,
        "test_suite": "test_payments_financials",
        "test_function": "test_gcash_payment_verification_workflow"
    },
    {
        "id": "payments_cod_and_cop_methods",
        "module": "Payments & Financials",
        "name": "Cash on Delivery (COD) & Cash on Pickup (COP)",
        "description": "Handling Cash on Delivery with seller active order limits and Cash on Pickup for in-store order collection without delivery fees.",
        "roles": ["customer", "seller"],
        "endpoints": [
            "POST /api/v1/checkout/create-orders",
            "GET /api/v1/checkout/active-order-limit"
        ],
        "models": ["Order", "StorePaymentSetting"],
        "has_test": True,
        "test_suite": "test_payments_financials",
        "test_function": "test_cod_and_cop_payment_rules"
    },

    # ==========================================
    # 7. CHAT, MESSAGING & CUSTOM QUOTES
    # ==========================================
    {
        "id": "chat_conversations_and_support",
        "module": "Chat & Messaging",
        "name": "Real-time Chat & Support Tickets",
        "description": "Creating conversations between customer & seller or customer & rider, support ticketing, presence heartbeats, and typing indicators.",
        "roles": ["customer", "seller", "rider"],
        "endpoints": [
            "GET /api/v1/chat/conversations",
            "POST /api/v1/chat/conversations",
            "POST /api/v1/chat/conversations/support",
            "POST /api/v1/chat/conversations/<id>/messages",
            "GET /api/v1/chat/unread-count"
        ],
        "models": ["Conversation", "ChatMessage"],
        "has_test": True,
        "test_suite": "test_chat_messaging",
        "test_function": "test_chat_conversation_and_messaging"
    },
    {
        "id": "chat_custom_quotation_tickets",
        "module": "Chat & Messaging",
        "name": "Custom Floral Quotations in Chat",
        "description": "Seller creating custom floral quotation ticket during chat negotiation, customer accepting and checking out directly from the ticket.",
        "roles": ["seller", "customer"],
        "endpoints": [
            "POST /api/v1/chat/conversations/<id>/custom-ticket",
            "GET /api/v1/chat/custom-ticket/<id>",
            "POST /api/v1/chat/custom-ticket/<id>/checkout"
        ],
        "models": ["CustomQuoteTicket", "Order"],
        "has_test": True,
        "test_suite": "test_chat_messaging",
        "test_function": "test_custom_quote_ticket_and_checkout"
    },

    # ==========================================
    # 8. ADMINISTRATOR MODULE & ANALYTICS
    # ==========================================
    {
        "id": "admin_user_and_store_moderation",
        "module": "Administrator Module",
        "name": "User & Store Moderation",
        "description": "Admin browsing user directory, store status toggle (active, suspended, closed), reviewing seller applications, and platform oversight.",
        "roles": ["admin"],
        "endpoints": [
            "GET /api/admin/users/list",
            "PUT /api/v1/admin/users/<id>/status",
            "GET /api/v1/admin/stores",
            "PUT /api/v1/admin/stores/<id>/status"
        ],
        "models": ["User", "Store"],
        "has_test": True,
        "test_suite": "test_admin_module",
        "test_function": "test_admin_user_and_store_moderation"
    },
    {
        "id": "admin_feature_controls",
        "module": "Administrator Module",
        "name": "System Controls & Feature Switches",
        "description": "Dynamic toggles for maintenance mode, customer phone OTP requirement, sms8.io primary SMS gateway, and iProg backup gateway.",
        "roles": ["admin"],
        "endpoints": [
            "GET /api/admin/feature-controls",
            "PUT /api/admin/feature-controls",
            "GET /api/public/feature-flags"
        ],
        "models": ["SystemControl"],
        "has_test": True,
        "test_suite": "test_admin_module",
        "test_function": "test_admin_system_feature_controls"
    },
    {
        "id": "admin_analytics_and_reporting",
        "module": "Administrator Module",
        "name": "Sales Analytics, Repeat Customers, and Report Generation",
        "description": "Calculating gross revenue, order volume, repeat customer percentage, date period slicing (today/week/month/year), and PDF export.",
        "roles": ["admin"],
        "endpoints": [
            "GET /api/v1/admin/analytics",
            "GET /analytics",
            "GET /reports"
        ],
        "models": ["Order", "OrderAnalytics", "POSOrder"],
        "has_test": True,
        "test_suite": "test_admin_module",
        "test_function": "test_analytics_and_reporting_calculations"
    },

    # ==========================================
    # 9. EXTERNAL INTEGRATIONS
    # ==========================================
    {
        "id": "integrations_sms_routing",
        "module": "External Integrations",
        "name": "SMS Gateway Telco Routing & Fallback",
        "description": "Smart carrier routing between sms8.io (Smart/TNT) and iProg SMS (Globe/TM/DITO) with automatic failover.",
        "roles": ["system"],
        "endpoints": ["Internal Service (app/utils/sms_helper.py)"],
        "models": ["SystemControl"],
        "has_test": True,
        "test_suite": "test_integrations",
        "test_function": "test_sms_routing_and_telco_detection"
    },
    {
        "id": "integrations_email_oauth2",
        "module": "External Integrations",
        "name": "Gmail OAuth2 & SendGrid Fallback",
        "description": "Sending transactional emails via Google OAuth2 refresh tokens, handling token refresh, and falling back to SendGrid.",
        "roles": ["system"],
        "endpoints": ["Internal Service (app/utils/email_helper.py)"],
        "models": [],
        "has_test": True,
        "test_suite": "test_integrations",
        "test_function": "test_email_service_configuration"
    },
    {
        "id": "integrations_maps_geocoding",
        "module": "External Integrations",
        "name": "Mapbox & Google Maps Geocoding & Distance",
        "description": "Reverse geocoding coordinates, distance calculations for delivery fee quotes, and boundary constraint verification.",
        "roles": ["system"],
        "endpoints": [
            "GET /api/v1/customer/maps/geocode/reverse",
            "GET /api/v1/customer/maps/places/search"
        ],
        "models": ["MunicipalityBoundary"],
        "has_test": True,
        "test_suite": "test_integrations",
        "test_function": "test_maps_and_distance_calculations"
    },

    # ==========================================
    # 10. FLUTTER MOBILE APP MODULE
    # ==========================================
    {
        "id": "flutter_mobile_client",
        "module": "Flutter Mobile App",
        "name": "Flutter Client Models & Screen Workflows",
        "description": "Cross-platform Flutter application powering customer storefront, seller operations, and rider delivery routing.",
        "roles": ["customer", "seller", "rider"],
        "endpoints": ["Client App (eflowers_app)"],
        "models": [],
        "has_test": True,
        "test_suite": "flutter_tests",
        "test_function": "run_flutter_test_suite"
    }
]


def get_feature_inventory() -> List[Dict[str, Any]]:
    return FEATURE_INVENTORY


def get_inventory_summary() -> Dict[str, Any]:
    total_features = len(FEATURE_INVENTORY)
    features_with_tests = sum(1 for f in FEATURE_INVENTORY if f.get("has_test"))
    features_without_tests = total_features - features_with_tests
    coverage_pct = round((features_with_tests / total_features) * 100, 1) if total_features else 0.0

    modules = {}
    for f in FEATURE_INVENTORY:
        mod = f["module"]
        if mod not in modules:
            modules[mod] = {"total": 0, "tested": 0}
        modules[mod]["total"] += 1
        if f.get("has_test"):
            modules[mod]["tested"] += 1

    return {
        "total_features": total_features,
        "features_with_tests": features_with_tests,
        "features_without_tests": features_without_tests,
        "coverage_percentage": coverage_pct,
        "modules": modules
    }

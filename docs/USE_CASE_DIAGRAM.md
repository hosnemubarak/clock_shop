# Clock Shop - Use Case Diagram

## System Overview

This document describes the use cases for the Clock Shop Inventory & Sales Management System.

## Actors

| Actor | Description |
|-------|-------------|
| **Admin** | System administrator with full access to all features |
| **Staff** | Shop employee who handles daily operations |
| **Customer** | End customer who purchases products (indirect actor) |

## Use Case Diagram (Text Representation)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CLOCK SHOP SYSTEM                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    AUTHENTICATION                                    │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │   Login     │  │  Register   │  │   Logout    │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    INVENTORY MANAGEMENT                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  Manage     │  │  Manage     │  │  Manage     │                  │    │
│  │  │  Products   │  │  Categories │  │  Brands     │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  Stock In   │  │  Stock Out  │  │   View      │                  │    │
│  │  │  (Batches)  │  │  (Damage)   │  │   Batches   │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    SALES MANAGEMENT                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  Create     │  │   View      │  │   Cancel    │                  │    │
│  │  │   Sale      │  │   Sales     │  │   Sale      │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │  ┌─────────────┐  ┌─────────────┐                                   │    │
│  │  │   Print     │  │  Add Custom │                                   │    │
│  │  │  Invoice    │  │    Items    │                                   │    │
│  │  └─────────────┘  └─────────────┘                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    CUSTOMER MANAGEMENT                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  Manage     │  │  Receive    │  │   View      │                  │    │
│  │  │  Customers  │  │  Payments   │  │   History   │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │  ┌─────────────┐  ┌─────────────┐                                   │    │
│  │  │   Add       │  │   Track     │                                   │    │
│  │  │   Notes     │  │    Dues     │                                   │    │
│  │  └─────────────┘  └─────────────┘                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    WAREHOUSE MANAGEMENT                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  Manage     │  │  Transfer   │  │   View      │                  │    │
│  │  │ Warehouses  │  │   Stock     │  │  Transfers  │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    REPORTING & ANALYTICS                             │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │   Sales     │  │   Profit    │  │   Stock     │                  │    │
│  │  │   Report    │  │   Report    │  │   Report    │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │  Customer   │  │ Dead Stock  │  │   Batch     │                  │    │
│  │  │   Report    │  │   Report    │  │  Analysis   │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │  ┌─────────────┐  ┌─────────────┐                                   │    │
│  │  │  Transfer   │  │    View     │                                   │    │
│  │  │   Report    │  │  Dashboard  │                                   │    │
│  │  └─────────────┘  └─────────────┘                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    ADMINISTRATION (Admin Only)                       │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │   Manage    │  │    View     │  │   Approve   │                  │    │
│  │  │   Users     │  │ Audit Logs  │  │   Users     │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

        ┌───────┐                                          ┌───────┐
        │ Admin │ ─────────── All Use Cases ──────────────│ Staff │
        └───────┘                                          └───────┘
            │                                                  │
            │                                                  │
            ▼                                                  ▼
    [Full System Access]                            [Operational Access]
    - User Management                               - Inventory Operations
    - System Configuration                          - Sales Operations
    - All Reports                                   - Customer Management
    - Audit Logs                                    - Basic Reports
```

## Detailed Use Cases

### UC-01: Manage Products
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Create, view, edit, and deactivate products |
| **Preconditions** | User is logged in |
| **Main Flow** | 1. Navigate to Products<br>2. Select action (Add/Edit/View)<br>3. Fill in product details<br>4. Save changes |
| **Postconditions** | Product is created/updated in the system |

### UC-02: Stock In (Create Batch)
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Add new stock by creating a batch |
| **Preconditions** | Product exists, Warehouse exists |
| **Main Flow** | 1. Navigate to Stock In<br>2. Select product and warehouse<br>3. Enter quantity, buy price, supplier<br>4. Save batch |
| **Postconditions** | New batch created, product stock updated |

### UC-03: Stock Out
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Remove stock for non-sale reasons (damage, loss, etc.) |
| **Preconditions** | Batch exists with available stock |
| **Main Flow** | 1. Navigate to Stock Out<br>2. Select warehouse<br>3. Add items to remove<br>4. Select reason<br>5. Complete stock out |
| **Postconditions** | Stock reduced, audit trail created |

### UC-04: Create Sale
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Create a new sale/invoice |
| **Preconditions** | Products with stock exist |
| **Main Flow** | 1. Navigate to New Sale<br>2. Select customer (optional)<br>3. Add items with batch selection<br>4. Apply discounts (optional)<br>5. Complete sale |
| **Postconditions** | Sale created, stock deducted, invoice generated |

### UC-05: Receive Payment
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Record payment from customer |
| **Preconditions** | Customer has outstanding balance or sale exists |
| **Main Flow** | 1. Navigate to Receive Payment<br>2. Select customer<br>3. Enter amount and method<br>4. Link to invoice (optional)<br>5. Save payment |
| **Postconditions** | Payment recorded, customer balance updated |

### UC-06: Transfer Stock
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Transfer stock between warehouses |
| **Preconditions** | Source warehouse has stock, destination warehouse exists |
| **Main Flow** | 1. Navigate to New Transfer<br>2. Select source and destination<br>3. Add items to transfer<br>4. Complete transfer |
| **Postconditions** | Stock moved, transfer record created |

### UC-07: View Reports
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | Generate and view various reports |
| **Preconditions** | User is logged in |
| **Main Flow** | 1. Navigate to Reports<br>2. Select report type<br>3. Set date range/filters<br>4. View results with charts |
| **Postconditions** | Report displayed |

### UC-08: View Dashboard
| Field | Description |
|-------|-------------|
| **Actor** | Admin, Staff |
| **Description** | View real-time business metrics |
| **Preconditions** | User is logged in |
| **Main Flow** | 1. Login to system<br>2. View dashboard with KPIs, charts, alerts |
| **Postconditions** | Dashboard displayed with current data |

## System Workflows

### Sales Workflow
```
[Create Sale] → [Select Batch] → [Deduct Stock] → [Generate Invoice] → [Receive Payment]
```

### Stock In Workflow
```
[Receive Goods] → [Create Batch] → [Update Product Stock] → [Create Audit Log]
```

### Stock Out Workflow
```
[Identify Issue] → [Create Stock Out] → [Select Items] → [Deduct Stock] → [Create Audit Log]
```

### Transfer Workflow
```
[Create Transfer] → [Add Items] → [Complete Transfer] → [Update Both Warehouses]
```

## Data Flow Diagram

```
                    ┌─────────────┐
                    │    User     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Django     │
                    │  Views      │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     ┌──────────┐   ┌──────────┐   ┌──────────┐
     │ Inventory│   │  Sales   │   │ Customers│
     │  Models  │   │  Models  │   │  Models  │
     └────┬─────┘   └────┬─────┘   └────┬─────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │   SQLite    │
                  │  Database   │
                  └─────────────┘
```

## Entity Relationship Summary

```
Warehouse ──┬── Batch ──── Product ──── Category
            │      │              │
            │      │              └── Brand
            │      │
            │      └── SaleItem ── Sale ── Customer
            │              │
            │              └── Payment
            │
            └── StockTransfer ── StockTransferItem
            │
            └── StockOut ── StockOutItem
```

---

*Last Updated: January 2026*

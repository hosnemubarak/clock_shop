# Clock Shop - User Use Case Guide

## Retail Clock Shop Inventory & Sales Management System

**Version:** 2.0  
**Last Updated:** January 2026

> This guide covers all features of the Clock Shop Inventory & Sales Management System with step-by-step instructions for every workflow.

---

## Table of Contents

1. [Dashboard](#1-dashboard)
2. [Inventory](#2-inventory)
3. [New Sale](#3-new-sale)
4. [Customer](#4-customer)
5. [Warehouse](#5-warehouse)
6. [Reports & Audit Log](#6-reports--audit-log)

---

## 1. Dashboard

### Overview
The Dashboard is your central hub for monitoring business performance at a glance. It displays key metrics, recent activities, and quick action buttons.

### Accessing the Dashboard
1. Log in to the system with your credentials
2. You will be automatically redirected to the Dashboard
3. Alternatively, click **Dashboard** in the sidebar menu

### Dashboard Widgets & Cards

#### Top Row - Financial Metrics
| Card | Description | Click Action |
|------|-------------|--------------|
| **Today's Sales** | Total sales amount for the current day | Opens Sales List |
| **Monthly Sales** | Total sales for the current month | Opens Sales Report |
| **Monthly Profit** | Profit earned this month | Opens Profit Report |
| **Outstanding Dues** | Total unpaid customer balances | Opens Customer Report |

#### Second Row - Inventory Metrics
| Card | Description | Click Action |
|------|-------------|--------------|
| **Total Products** | Number of active products | Opens Product List |
| **Low Stock Items** | Products below minimum threshold | Opens Stock Report (filtered) |
| **Total Customers** | Number of registered customers | Opens Customer List |
| **Quick Actions** | New Sale & Add Stock buttons | Opens respective forms |

### Interactive Elements
- **All cards are clickable** - Click any metric card to navigate to its detail page
- **Quick Action Buttons** - Instant access to create sales or add stock
- **Recent Sales Table** - Shows last 10 sales with clickable invoice numbers
- **Low Stock Alerts** - Lists products needing restocking

### Mobile Responsiveness
- Cards stack vertically on mobile devices
- Sidebar collapses to hamburger menu
- All metrics remain accessible via scrolling

---

## 2. Inventory

### Overview
The Inventory module manages products, categories, brands, batches, and purchases. All stock is tracked at the **batch level** to maintain accurate cost tracking.

### 2.1 Managing Products

#### Adding a New Product
1. Navigate to **Inventory → Products** in the sidebar
2. Click **Add Product** button
3. Fill in the required fields:
   - **SKU** - Unique product code
   - **Name** - Product name
   - **Category** - Select from dropdown
   - **Default Selling Price** - Standard retail price
4. Optional fields: Brand, Description, Image
5. Click **Save Product**

#### Validation Modals
- **Missing Required Fields**: A modal will appear if SKU, Name, or Price is empty
- **Duplicate SKU**: Modal alerts if SKU already exists

#### Editing Products
1. Go to **Inventory → Products**
2. Click the dropdown menu (⋯) on the product row
3. Select **Edit**
4. Modify fields and click **Save**

#### Deleting Products
1. Click dropdown menu → **Delete**
2. Confirmation modal appears: "Are you sure you want to delete this product?"
3. Click **Confirm** to delete or **Cancel** to abort

### 2.2 Managing Categories & Brands

#### Adding a Category
1. Navigate to **Inventory → Categories**
2. Click **Add Category**
3. Enter Name and Description
4. Click **Save**

#### Adding a Brand
1. Navigate to **Inventory → Brands**
2. Click **Add Brand**
3. Enter Name and Description
4. Click **Save**

### 2.3 Managing Batches (Stock)

Batches are the core of inventory tracking. Each batch represents a specific purchase with its own:
- **Buy Price** (cost)
- **Quantity**
- **Warehouse location**
- **Purchase date**

#### Adding Stock (Creating a Batch)
1. Navigate to **Inventory → Add Stock**
2. Select the **Warehouse** where stock will be stored
3. Click **Add Item** to add products:
   - Select Product
   - Enter Quantity
   - Enter Buy Price (cost per unit)
4. Add multiple products as needed
5. Enter Supplier name and Purchase Date
6. Click **Save Purchase**

#### Validation Modals
| Validation | Modal Message |
|------------|---------------|
| No items added | "Please add at least one item before saving" |
| Invalid quantity | "Quantity must be greater than zero" |
| Missing warehouse | "Please select a warehouse" |
| Missing buy price | "Please enter a valid buy price" |

### 2.4 Viewing Stock by Warehouse

1. Navigate to **Warehouse → [Warehouse Name]**
2. View all batches with:
   - Product name
   - Batch number
   - Available quantity
   - Buy price
   - Total value

### 2.5 Stock Transfers

See [Section 5: Warehouse](#5-warehouse) for detailed transfer instructions.

---

## 3. New Sale

### Overview
The New Sale module is the primary interface for recording customer purchases. It supports:
- **Manual batch selection** for accurate cost tracking
- **Partial and full payments**
- **Automatic profit calculation**
- **Customer credit management**

### Creating a New Sale

#### Step 1: Access New Sale
1. Click **Sales → New Sale** in the sidebar
2. Or click **New Sale** button on the Dashboard

#### Step 2: Select Customer (Optional)
1. Choose a customer from the dropdown
2. Or leave as "Walk-in Customer" for cash sales
3. Customer's credit limit and outstanding dues are displayed

#### Step 3: Add Sale Items

##### Manual Batch Selection
1. Click **Add Item** button
2. Select a **Product** from the dropdown
3. A list of **available batches** appears showing:
   - Batch number
   - Available quantity
   - Buy price (cost)
   - Warehouse location
4. Select the batch to sell from
5. Enter **Quantity** to sell
6. Adjust **Selling Price** if needed (defaults to product's default price)
7. Click **Add to Sale**

##### Adding Multiple Items
- Repeat the above process for each product
- Items appear in the sale table with:
  - Product name
  - Batch number
  - Quantity
  - Unit price
  - Total

##### Removing Items
- Click the **×** button on any item row
- The item is removed and stock is restored

#### Step 4: Review Totals
The system automatically calculates:
| Field | Description |
|-------|-------------|
| **Subtotal** | Sum of all item totals |
| **Discount** | Enter discount amount or percentage |
| **Tax** | Calculated based on settings |
| **Grand Total** | Final amount due |
| **Profit** | (Selling Price - Cost) per item |

#### Step 5: Record Payment
1. Enter payment amount received
2. Select payment method (Cash, Card, Bank Transfer)
3. Enter reference number if applicable

##### Payment Status
| Status | Condition |
|--------|-----------|
| **Paid** | Payment equals or exceeds total |
| **Partial** | Payment is less than total |
| **Unpaid** | No payment recorded |

#### Step 6: Complete Sale
1. Review all details
2. Click **Complete Sale**
3. Invoice is generated with unique number
4. Stock is automatically deducted from selected batches

### Validation Modals

| Scenario | Modal Message |
|----------|---------------|
| No items added | "Please add at least one item to the sale" |
| Quantity exceeds stock | "Only [X] units available in this batch" |
| Invalid quantity | "Please enter a valid quantity" |
| No batch selected | "Please select a batch for [Product Name]" |
| Payment exceeds due | "Payment amount exceeds the due amount" |
| Customer credit exceeded | "This sale exceeds customer's credit limit" |

### Printing Invoice
1. After sale completion, click **Print Invoice**
2. A print-friendly version opens
3. Use browser's print function (Ctrl+P)

### Viewing Past Sales
1. Navigate to **Sales → Sales List**
2. Filter by date, customer, or payment status
3. Click invoice number to view details

---

## 4. Customer

### Overview
The Customer module manages customer profiles, tracks purchase history, monitors outstanding dues, and records payments.

### 4.1 Adding a New Customer

1. Navigate to **Customers → Customer List**
2. Click **Add Customer**
3. Fill in the details:

| Field | Required | Description |
|-------|----------|-------------|
| Name | Yes | Customer's full name |
| Phone | No | Contact number |
| Email | No | Email address |
| Address | No | Delivery/billing address |
| Credit Limit | No | Maximum credit allowed |
| Notes | No | Internal notes |

4. Click **Save Customer**

### Validation Modals
- **Missing Name**: "Customer name is required"
- **Invalid Email**: "Please enter a valid email address"
- **Invalid Credit Limit**: "Credit limit must be a positive number"

### 4.2 Viewing Customer Profile

1. Go to **Customers → Customer List**
2. Click on customer name
3. View customer dashboard showing:
   - Contact information
   - Total purchases
   - Total payments
   - Outstanding balance
   - Credit limit usage

### 4.3 Customer Purchase History

1. Open customer profile
2. Scroll to **Purchase History** section
3. View all invoices with:
   - Invoice number
   - Date
   - Amount
   - Payment status
4. Click invoice number for details

### 4.4 Recording Customer Payments

The payment system now features **dynamic invoice loading** - when you select a customer, their outstanding invoices are automatically loaded for easy selection.

#### From Payment Creation Page
1. Navigate to **Customers → Payments → New Payment**
2. **Select Customer** from the dropdown
3. Outstanding invoices automatically load in a table showing:
   - Invoice number
   - Sale date
   - Total amount
   - Already paid
   - Due amount
   - Checkbox for selection
4. **Select invoices** to apply payment to (check one or more)
5. Enter **Payment Amount**
6. Select **Payment Method** (Cash, Card, Bank Transfer)
7. Enter **Reference Number** (optional)
8. Click **Save Payment**

#### Payment Allocation
- Payment is distributed to selected invoices
- Partial payments are tracked per invoice
- Customer balance automatically updated

#### From Customer Profile
1. Open customer profile
2. Click **Receive Payment** button
3. Invoices are pre-filtered for this customer
4. Follow steps above

### Validation Modals
| Scenario | Modal Message |
|----------|---------------|
| No customer selected | "Please select a customer" |
| No invoices selected | "Please select at least one invoice" |
| No amount entered | "Please enter a payment amount" |
| Amount exceeds total due | "Payment amount exceeds the total due for selected invoices" |
| Invalid amount | "Please enter a valid positive amount" |

### 4.5 Customer Statement

1. Open customer profile
2. Click **View Statement**
3. See chronological list of:
   - Purchases (debits)
   - Payments (credits)
   - Running balance
4. Filter by date range

### 4.6 Searching & Filtering Customers

| Filter | Description |
|--------|-------------|
| Search | Search by name, phone, or email |
| Status | Active/Inactive customers |
| Has Due | Customers with outstanding balance |

---

## 5. Warehouse

### Overview
The Warehouse module manages storage locations and enables batch-level stock transfers between warehouses while preserving cost information.

### 5.1 Adding a New Warehouse

1. Navigate to **Warehouse → Warehouse List**
2. Click **Add Warehouse**
3. Fill in the details:

| Field | Required | Description |
|-------|----------|-------------|
| Name | Yes | Warehouse name |
| Code | Yes | Short unique code |
| Phone | No | Contact number |
| Address | No | Physical address |
| Is Shop | No | Mark if this is a retail location |
| Active | Yes | Enable/disable warehouse |

4. Click **Save Warehouse**

### Validation Modals
- **Missing Name**: "Warehouse name is required"
- **Missing Code**: "Warehouse code is required"
- **Duplicate Code**: "A warehouse with this code already exists"

### 5.2 Viewing Warehouse Stock

1. Go to **Warehouse → Warehouse List**
2. Click on warehouse name
3. View stock summary:
   - Total items
   - Total value
   - Stock by product
   - Individual batches

### 5.3 Stock Transfers

Stock transfers move inventory between warehouses at the **batch level**, preserving the original buy price.

#### Creating a Transfer

1. Navigate to **Warehouse → Transfers**
2. Click **New Transfer**
3. Select **Source Warehouse** (where stock is moving FROM)
4. Select **Destination Warehouse** (where stock is moving TO)
5. Add items to transfer:
   - Batches from source warehouse are displayed
   - Select a batch
   - Enter quantity to transfer
   - Click **Add**
6. Review items and total value
7. Click **Create Transfer**

#### Transfer Status
| Status | Description |
|--------|-------------|
| **Pending** | Transfer created but not yet completed |
| **Completed** | Stock has been moved |
| **Cancelled** | Transfer was cancelled |

#### Completing a Transfer

1. Open the transfer from transfer list
2. Review items
3. Click **Complete Transfer**
4. Confirmation modal: "Complete this transfer? This will move stock from [Source] to [Destination]"
5. Click **Confirm**

Stock movement:
- Source batch quantity is **decreased**
- Destination batch is **created or updated** with same buy price
- Product total stock is recalculated

#### Cancelling a Transfer

1. Open pending transfer
2. Click **Cancel Transfer**
3. Confirmation modal: "Cancel this transfer? No stock will be moved."
4. Click **Confirm**

### Validation Modals

| Scenario | Modal Message |
|----------|---------------|
| Same source/destination | "Source and destination warehouses must be different" |
| No items added | "Please add at least one item to transfer" |
| Quantity exceeds stock | "Only [X] units available in this batch" |
| No source selected | "Please select a source warehouse" |
| No destination selected | "Please select a destination warehouse" |
| Invalid quantity | "Please enter a valid quantity" |

### 5.4 Filtering Transfers

| Filter | Options |
|--------|---------|
| Status | All, Pending, Completed, Cancelled |
| Source | Filter by source warehouse |
| Destination | Filter by destination warehouse |

---

## 6. Reports & Audit Log

### Overview
The Reports module provides comprehensive business analytics and the Audit Log tracks all system changes for accountability.

### 6.1 Available Reports

#### Sales Report
**Path:** Reports → Sales Report

| Metric | Description |
|--------|-------------|
| Total Sales | Sum of all sales in period |
| Sales by Date | Daily/weekly/monthly breakdown |
| Top Products | Best-selling products |
| Sales by Customer | Customer-wise analysis |

**Filters:**
- Date range (From - To)
- Customer
- Payment status

#### Profit Report
**Path:** Reports → Profit Report

| Metric | Description |
|--------|-------------|
| Gross Profit | Total revenue minus cost |
| Profit Margin | Percentage of profit |
| Profit by Product | Product-wise breakdown |
| Profit by Category | Category-wise analysis |

**How Profit is Calculated:**
```
Profit = Selling Price - Buy Price (from batch)
```

#### Stock Report
**Path:** Reports → Stock Report

| Section | Description |
|---------|-------------|
| Stock Summary | Total items and value |
| Stock by Product | Current stock per product |
| Stock by Warehouse | Warehouse-wise distribution |
| Low Stock Alerts | Products below threshold |

**Filters:**
- Warehouse
- Category
- Stock Level (All, Low, Out of Stock)

#### Customer Report
**Path:** Reports → Customer Report

| Metric | Description |
|--------|-------------|
| Total Customers | Active customer count |
| Customers with Dues | Count and total owed |
| Top Customers | By purchase volume |
| Recent Payments | Latest payments received |

#### Dead Stock Report
**Path:** Reports → Dead Stock Report

| Section | Description |
|---------|-------------|
| Dead Stock | No sales in 90+ days |
| Slow Moving | Low sales frequency |
| Aging Analysis | Stock age breakdown |

#### Transfer Report
**Path:** Reports → Transfer Report

| Metric | Description |
|--------|-------------|
| Total Transfers | Count by status |
| Transfer Value | Total value moved |
| By Warehouse | Source/destination analysis |

### 6.2 Batch Analysis

**Path:** Reports → Batch Report

View detailed batch information:
- Batch number
- Purchase date
- Age (days)
- Initial quantity
- Current quantity
- Sold quantity
- Value

### 6.3 Audit Log

**Path:** Dashboard → Audit Logs

The Audit Log tracks all system changes:

| Field | Description |
|-------|-------------|
| Timestamp | When the action occurred |
| User | Who performed the action |
| Action | CREATE, UPDATE, DELETE, TRANSFER |
| Model | What was affected |
| Details | Specific changes made |

**Actions Logged:**
- Product creation/modification
- Sale completion
- Payment receipt
- Stock transfers
- Customer updates
- Warehouse changes

**Filtering:**
- Date range
- User
- Action type
- Model type

### 6.4 Confirmation Modals for Critical Actions

| Action | Modal Message |
|--------|---------------|
| Delete Product | "This will permanently delete the product. Continue?" |
| Delete Customer | "This will remove customer and associated data. Continue?" |
| Complete Transfer | "This will move stock between warehouses. Confirm?" |
| Cancel Transfer | "This will cancel the transfer. No stock will be moved." |
| Finalize Sale | "Complete this sale? Stock will be deducted." |

---

## Appendix A: Quick Reference

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| Ctrl + P | Print current page |
| Esc | Close modal dialogs |

### Common Workflows

#### Daily Opening
1. Check Dashboard for overnight orders
2. Review low stock alerts
3. Check pending transfers

#### Processing a Sale
1. Dashboard → New Sale
2. Select customer (optional)
3. Add items with batch selection
4. Record payment
5. Complete and print invoice

#### End of Day
1. Review day's sales on Dashboard
2. Check outstanding payments
3. Verify stock levels

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Can't find product | Check if product is active |
| Stock shows 0 | Verify correct warehouse selected |
| Customer not in list | Check if customer is active |
| Payment not applying | Ensure invoice is not already paid |

---

## Appendix B: Mobile Usage

### Responsive Features
- Sidebar collapses to hamburger menu
- Tables scroll horizontally
- Cards stack vertically
- Touch-friendly buttons

### Mobile-Optimized Actions
- Tap cards to navigate
- Swipe tables for more columns
- Use dropdown menus for actions

---

## Appendix C: System Settings

### Business Settings
| Setting | Description | Environment Variable |
|---------|-------------|---------------------|
| Shop Name | Displayed on invoices | `SHOP_NAME` |
| Currency Symbol | Default: $ | `CURRENCY_SYMBOL` |
| Low Stock Threshold | Default: 10 units | `LOW_STOCK_THRESHOLD` |

### Deployment Options
| Method | Description |
|--------|-------------|
| **Docker** | Recommended for production. Use `docker-compose up -d` |
| **Manual** | Python venv + Gunicorn + Nginx |
| **Development** | `python manage.py runserver` |

See `README.md` for detailed deployment instructions.

### User Permissions
| Role | Capabilities |
|------|--------------|
| Admin | Full system access |
| Staff | Sales, customers, limited reports |
| Viewer | Read-only access |

---

**Document End**

*For technical support, contact your system administrator.*

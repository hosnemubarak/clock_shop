# User & Role Management Guide

This guide explains how to onboard new staff members, approve their accounts, and assign them the correct system roles to ensure security and proper access control.

---

## 1. The Registration Process

When a new employee needs access to the system:
1. They must go to the **Register** page (`/register/`) and create an account.
2. The system enforces **strong passwords** (minimum 8 characters, cannot be entirely numeric, cannot be too similar to their username).
3. Upon registering, their account is placed into a **Pending Approval** state. They **cannot** log in yet.

> [!WARNING]
> New registrations are always disabled by default. An Administrator must manually approve them and assign a role before they can access the system.

---

## 2. Managing Staff (Admin Only)

If you are logged in as a Superuser or Admin, you have access to the **Staff Directory**.

1. Look at the bottom of the left-hand sidebar navigation menu.
2. Click on **Staff Directory** (right above System Settings).
3. This page lists all registered users in the system, showing their **Account Status** and their current **Role**.

---

## 3. How to Approve a User and Assign a Role

From the **Staff Directory** page:
1. Locate the user who is marked as **Pending Approval**.
2. Click the **Edit Role** button on the right side of their row.
3. A popup modal will appear with two settings:
   - **Account Status:** Change this from "Pending / Disabled" to **"Approved (Active)"**.
   - **System Role:** Select the appropriate role from the dropdown menu.
4. Click **Save Changes**.

The user can now log in, and their menus will be automatically restricted based on the role you chose.

---

## 4. Understanding System Roles (RBAC)

The system uses Role-Based Access Control (RBAC). A user must have exactly one role to function properly.

| Role | Permissions |
|------|-------------|
| **Cashier** | Can access the POS (Create Sales). Can view the Dashboard, Customers, and Products. **Cannot** access Settings, Audit Logs, Inventory Stock In/Out, or process Returns. |
| **Manager** | Has full access to Inventory management, Stock movements, Warehouse transfers, Returns, and Reports. **Cannot** access System Settings or Audit Logs. |
| **Admin** | (Superuser). Has full access to everything in the system, including System Settings, the Staff Directory, and Audit Logs. |

---

## 5. Troubleshooting Lockouts

If an approved user reports that they are seeing an **"Unauthorized"** screen on every page they visit, it means they have been **Approved** but they have **No Role**.

**To fix this:**
1. Go to the **Staff Directory**.
2. Find their name (it will likely say "Approved" but "No Role").
3. Click **Edit Role** and assign them to either the **Cashier** or **Manager** group.
4. They will immediately regain access.

---

## 6. Disabling a User (Offboarding)

If an employee leaves the company:
1. Go to the **Staff Directory**.
2. Click **Edit Role** next to their name.
3. Change their Account Status to **"Pending / Disabled"**.
4. (Optional) Change their role back to **"-- No Role --"**.
5. Click **Save Changes**.

They will be instantly locked out of the system. Their previous sales and logs will remain perfectly intact in the database for historical reporting.

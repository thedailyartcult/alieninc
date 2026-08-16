# CENTRA Employee Self-Service Portal — Budibase Technical Specification

**Role:** Principal Solutions Architect, Internal Tooling  
**Platform:** Self-hosted Budibase (Docker)  
**Compliance target:** CMMC Level 2 / self-hosted, no external CDN  
**App name:** `CENTRA`

This document describes how to build the CENTRA Employee Self-Service Portal on top of the Budibase architecture using only internal services. The specification covers deployment, data model, RBAC, screen layouts, form logic, and backend automations.

---

## 1. Self-Hosted Deployment Architecture

Use the official Budibase Docker Compose stack from `https://github.com/budibase/budibase`. Run it in an isolated Docker network with no outbound dependency on public CDNs.

### 1.1 Core services

| Service | Purpose | CMMC-relevant hardening |
|---|---|---|
| `budibase/apps` | Serves the builder and apps | Bind to loopback/internal interface only |
| `budibase/worker` | Handles auth, automations, email | Restrict egress to internal SMTP/DB |
| `couchdb` / internal Budibase DB | App metadata and internal tables | Volume encryption, daily backups |
| `redis` | Caching / job queue | Require AUTH, network isolation |
| `minio` | File / attachment storage | TLS, bucket policies |
| Internal Postgres (optional binding) | Transactional audit-grade store | Enable audit logging, TLS, encrypted volumes |

### 1.2 Minimal `docker-compose.override.yml` principles

```yaml
version: "3"

services:
  budibase-apps:
    environment:
      - OFFLINE_MODE=true          # Serve all assets locally where supported
      - JWT_SECRET=${JWT_SECRET}
      - INTERNAL_API_KEY=${INTERNAL_API_KEY}
    networks:
      - centra-isolated

  budibase-worker:
    environment:
      - SMTP_HOST=${SMTP_HOST}      # Internal relay only; no SendGrid/Mailgun
      - SMTP_PORT=${SMTP_PORT}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASS=${SMTP_PASS}
      - SMTP_FROM=centra@alieninc.local
    networks:
      - centra-isolated

networks:
  centra-isolated:
    driver: bridge
    internal: true                  # No default internet access
```

### 1.3 No-CDN policy

- Do **not** reference external fonts, icons, or JS in custom components.
- Self-host any required font files (e.g., Inter) under `/public` inside the app or behind your reverse proxy.
- Configure the reverse proxy (nginx/Traefik) with a strict CSP such as:
  ```
  default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self';
  ```

---

## 2. Data Model

Create the tables below in the Budibase internal database (or bind to an isolated Postgres instance for stronger audit control).

### 2.1 `Personnel_Records` — master record table

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `User_Email` | Text | Primary key, required, email validator | Matches Budibase user email |
| `Employee_Name` | Text | Required | Human-readable name |
| `Clearance_Status` | Options | Required | Values: `None`, `Secret`, `Top Secret`, `TS/SCI`, `TS/SCI-Poly` |
| `Active_Accesses` | Long Form Text | | JSON array of programs/contracts |
| `Foreign_Travel_History` | Long Form Text | | JSON array of trips |
| `Foreign_Contacts` | Long Form Text | | JSON array of contacts |
| `Training_Completions` | Long Form Text | | JSON array of certificates/dates |
| `Manager_Email` | Text | Email validator | Used for Direct Reports view |

### 2.2 Transactional submission tables

All submission tables share these baseline fields, plus table-specific fields:

- `User_Email` (Text, required) — auto-populated from session
- `Submission_Date` (Date/Time, required) — auto-populated as `{{ now }}`
- `Status` (Options) — default `Pending`; values: `Pending`, `Under Review`, `Approved`, `Rejected`, `Closed`
- `Approval_Notes` (Long Form Text) — hidden from non-security users

#### `Access_Requests`

| Field | Type | Notes |
|---|---|---|
| `Access_Requests_ID` | Auto ID | Primary key |
| `User_Email` | Text | Auto-filled |
| `Submission_Date` | Date/Time | Auto-filled |
| `Program_or_Contract` | Text | Human label: *Affiliated Program/Contract Name* |
| `Justification` | Long Form Text | |
| `Status` | Options | Default `Pending` |
| `Approval_Notes` | Long Form Text | Security Staff only |

#### `Foreign_Travel_Reports`

| Field | Type | Notes |
|---|---|---|
| `Travel_ID` | Auto ID | Primary key |
| `User_Email` | Text | Auto-filled |
| `Submission_Date` | Date/Time | Auto-filled |
| `Destination_Countries` | Text | Comma-separated or JSON |
| `Departure_Date` | Date | |
| `Return_Date` | Date | |
| `Travel_Purpose` | Long Form Text | |
| `SEAD3_PreTravel` | Long Form Text | Pre-travel questionnaire answers |
| `SEAD3_PostTravel` | Long Form Text | Post-travel questionnaire answers |
| `Status` | Options | Default `Pending` |
| `Approval_Notes` | Long Form Text | Security Staff only |

#### `Foreign_Contact_Disclosures`

| Field | Type | Notes |
|---|---|---|
| `Contact_ID` | Auto ID | Primary key |
| `User_Email` | Text | Auto-filled |
| `Submission_Date` | Date/Time | Auto-filled |
| `Contact_Name` | Text | |
| `Relationship_Type` | Options | e.g., `Family`, `Friend`, `Business`, `Other` |
| `Contact_Citizenship` | Text | |
| `PSQ_Form_Data` | Long Form Text | Auto-populated PSQ content |
| `Status` | Options | Default `Pending` |
| `Approval_Notes` | Long Form Text | Security Staff only |

#### `Reportable_Incidents`

| Field | Type | Notes |
|---|---|---|
| `Incident_ID` | Auto ID | Primary key |
| `User_Email` | Text | Auto-filled |
| `Submission_Date` | Date/Time | Auto-filled |
| `Incident_Type` | Options | e.g., `Data Spill`, `Lost Device`, `Foreign Contact`, `Other` |
| `Date_Occurred` | Date | |
| `Incident_Description` | Long Form Text | |
| `Status` | Options | Default `Pending` |
| `Approval_Notes` | Long Form Text | Security Staff only |

#### `Visit_Requests`

| Field | Type | Notes |
|---|---|---|
| `Visit_ID` | Auto ID | Primary key |
| `User_Email` | Text | Auto-filled |
| `Submission_Date` | Date/Time | Auto-filled |
| `Visit_Direction` | Options | `Outgoing`, `Incoming` |
| `Host_Organization` | Text | For outgoing; visitor organization for incoming |
| `Visit_Date` | Date | |
| `Group_Visitors` | Long Form Text | JSON array: `[{name, organization, citizenship}]` |
| `Status` | Options | Default `Pending` |
| `Approval_Notes` | Long Form Text | Security Staff only |

---

## 3. Role-Based Access Control (RBAC)

Create three custom roles in **Settings → Users → Roles**:

| Role | ID reference | Purpose |
|---|---|---|
| Employee | `EMPLOYEE` | Views own record; submits forms |
| Manager | `MANAGER` | Views Direct Reports; read-only |
| Security Staff | `SECURITY_STAFF` | Approves, edits, views everything |

### 3.1 Screen-level access

| Screen | Minimum role | Notes |
|---|---|---|
| Employee Dashboard | Employee | Read-only own `Personnel_Records` |
| Manager Direct Reports | Manager | Read-only where manager matches |
| Submission forms | Employee | Create only for own submissions |
| Security Review Dashboard | Security Staff | Full CRUD on all submission tables |

### 3.2 Row-level filters

#### Employee Dashboard — Personnel_Records table filter

In the **Data Provider** for the table, set the filter:

```handlebars
{{ Current User.Email }} == Personnel_Records.User_Email
```

> Implementation: Add a filter condition, choose column `User_Email`, operator `Equals`, value type `Binding`, and select `Current User.Email`.

#### Manager Direct Reports — Personnel_Records table filter

```handlebars
{{ Current User.Email }} == Personnel_Records.Manager_Email
```

#### Submission security review filter (Security Staff)

No row filter needed; Security Staff sees all rows. Optionally add a filter by status.

---

## 4. Screen Layout & Component Hierarchy

### 4.1 Recommended screen inventory

1. `Home` — role-aware redirect or landing message.
2. `Employee Dashboard` — role: Employee.
3. `Manager Dashboard` — role: Manager.
4. `New Access Request` — role: Employee.
5. `New Foreign Travel Report` — role: Employee.
6. `New Foreign Contact Disclosure` — role: Employee.
7. `New Reportable Incident` — role: Employee.
8. `New Visit Request` — role: Employee.
9. `Security Review` — role: Security Staff.

### 4.2 Employee Dashboard layout

```
Screen: Employee Dashboard
└── Container (max-width centered)
    ├── Heading: "My Personnel Security Record"
    ├── Data Provider → Personnel_Records
    │   └── Table (Read-only)
    │       Columns: Employee_Name, Clearance_Status, Active_Accesses, Foreign_Travel_History, Foreign_Contacts, Training_Completions
    └── Button Group / Cards
        ├── "Request Access" → navigate to New Access Request
        ├── "Report Foreign Travel" → New Foreign Travel Report
        ├── "Disclose Foreign Contact" → New Foreign Contact Disclosure
        ├── "Report Incident" → New Reportable Incident
        └── "Request Visit" → New Visit Request
```

### 4.3 Manager Dashboard layout

```
Screen: Manager Dashboard
└── Container
    ├── Heading: "Direct Reports"
    ├── Data Provider → Personnel_Records
    │   └── Table (Read-only)
    │       Filter: {{ Current User.Email }} == Manager_Email
    │       Columns: Employee_Name, Clearance_Status, Active_Accesses, Training_Completions
    └── Data Provider → Access_Requests (optional)
        └── Table (Read-only)
            Filter: Direct report emails (advanced filter)
```

### 4.4 Submission form layout (example: New Access Request)

```
Screen: New Access Request
└── Container
    ├── Heading: "Request Program/Contract Access"
    ├── Form Block → Access_Requests
    │   ├── User_Email (Hidden, default value binding)
    │   ├── Submission_Date (Hidden, default value binding)
    │   ├── Program_or_Contract (Text, label: "Affiliated Program/Contract Name")
    │   ├── Justification (Long Form Text)
    │   └── Save Button
    └── Navigation link back to Employee Dashboard
```

---

## 5. Field Labels & Conditional Visibility

### 5.1 Human-centric labels

In the **Design** panel, select each form field and change the **Label** property:

| DB field | Display label |
|---|---|
| `Program_or_Contract` | Affiliated Program/Contract Name |
| `Justification` | Business Justification |
| `Destination_Countries` | Countries to be Visited |
| `SEAD3_PreTravel` | Pre-Travel SEAD 3 Responses |
| `SEAD3_PostTravel` | Post-Travel SEAD 3 Responses |
| `Relationship_Type` | Nature of Relationship |
| `Contact_Citizenship` | Contact's Country of Citizenship |
| `PSQ_Form_Data` | Generated PSQ Form Content |
| `Incident_Type` | Type of Reportable Event |
| `Incident_Description` | Description of Incident |
| `Visit_Direction` | Outgoing or Incoming Visit |
| `Host_Organization` | Hosting / Visiting Organization |
| `Group_Visitors` | Group Visitor List (JSON) |

### 5.2 Auto-populated hidden fields

For every submission form, set the **Default Value** binding on hidden fields:

- `User_Email` → `{{ Current User.Email }}`
- `Submission_Date` → `{{ now }}`
- `Status` → `Pending`

To hide the field: set the component **Type** to `Hidden Field` or toggle **Hidden** in the settings.

### 5.3 Conditional visibility for `Approval_Notes`

The `Approval_Notes` field must be visible only to Security Staff.

#### Option A — Binding expression (recommended)

In the component settings, open **Conditions** and add:

```handlebars
Hide component if
{{ neq Current User.roleId "SECURITY_STAFF" }}
```

Replace `"SECURITY_STAFF"` with the exact role ID shown in **Settings → Users → Roles**.

#### Option B — JavaScript condition

```javascript
return $user.roleId !== "SECURITY_STAFF";
```

> Use the same role ID from the Roles page.

Apply the same condition to any approval buttons or status dropdowns that should be security-only.

---

## 6. Automated Backend Workflows

Create one automation per submission table. All automations follow the same pattern.

### 6.1 Automation template: "Access Request Submitted"

1. **Trigger:** Row Created → Table: `Access_Requests`
2. **Action 1:** Update Row → Table: `Access_Requests`
   - Row ID: `{{ trigger.row._id }}`
   - Set `Status` = `Submitted` (if not already set by default)
3. **Action 2:** Send Email → Internal SMTP
   - **To:** `compliance-lead@alieninc.local` (or bind to an `App_Users` lookup)
   - **Subject:** `CENTRA: New Access Request from {{ trigger.row.User_Email }}`
   - **Body:**
     ```
     A new access request has been submitted.

     Employee: {{ trigger.row.User_Email }}
     Program/Contract: {{ trigger.row.Program_or_Contract }}
     Justification: {{ trigger.row.Justification }}
     Submitted: {{ date trigger.row.Submission_Date "YYYY-MM-DD HH:mm" }}
     ```
4. **Action 3 (optional):** Create Row → `Audit_Log`
   - `Table_Name` = `Access_Requests`
   - `Record_ID` = `{{ trigger.row._id }}`
   - `Action` = `Created`
   - `Actor` = `{{ trigger.row.User_Email }}`
   - `Timestamp` = `{{ now }}`

### 6.2 Repeat for each submission table

| Automation | Trigger table | Email subject line |
|---|---|---|
| Foreign Travel Submitted | `Foreign_Travel_Reports` | `CENTRA: Foreign Travel Report from {{ trigger.row.User_Email }}` |
| Foreign Contact Submitted | `Foreign_Contact_Disclosures` | `CENTRA: Foreign Contact Disclosure from {{ trigger.row.User_Email }}` |
| Incident Submitted | `Reportable_Incidents` | `CENTRA: Reportable Incident from {{ trigger.row.User_Email }}` |
| Visit Request Submitted | `Visit_Requests` | `CENTRA: Visit Request from {{ trigger.row.User_Email }}` |

### 6.3 Central dashboard status update

The "central dashboard" status is simply the `Status` column in each submission table. The automation's **Update Row** step writes the initial status, and Security Staff update it during review. A Security Staff screen can show a unified view using a **Data Provider** with no row filter and a table grouped by `Status`.

---

## 7. Implementation Checklist

- [ ] Deploy Budibase stack in isolated Docker network.
- [ ] Disable external CDN assets; configure CSP on reverse proxy.
- [ ] Configure internal SMTP environment variables.
- [ ] Create `Personnel_Records` and five submission tables.
- [ ] Create roles `EMPLOYEE`, `MANAGER`, `SECURITY_STAFF`.
- [ ] Create screens and assign minimum roles.
- [ ] Apply row filters on Employee and Manager dashboards.
- [ ] Set hidden default values on all submission forms.
- [ ] Rename field labels to human-centric text.
- [ ] Hide `Approval_Notes` and status controls from non-security users.
- [ ] Build one automation per submission table.
- [ ] Test with sample users in each role.
- [ ] Back up volumes and document role IDs for production.

---

## 8. Binding Quick Reference

| Purpose | Snippet |
|---|---|
| Current user email | `{{ Current User.Email }}` |
| Current timestamp | `{{ now }}` |
| Current user role ID | `{{ Current User.roleId }}` |
| Trigger row field | `{{ trigger.row.FieldName }}` |
| Compare role | `{{ eq Current User.roleId "SECURITY_STAFF" }}` |
| Hide unless role | `{{ neq Current User.roleId "SECURITY_STAFF" }}` |
| Format date | `{{ date trigger.row.Submission_Date "YYYY-MM-DD" }}` |

---

*This specification is designed to keep every component, data source, and automation inside the self-hosted Budibase boundary, satisfying CMMC Level 2 isolation and audit requirements without relying on external CDNs or SaaS email providers.*

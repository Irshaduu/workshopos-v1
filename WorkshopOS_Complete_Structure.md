*Every screen in the app, as an outline. Re-derived from the nav bar and the
drawer on 2026-10-09. The drawer's own group labels are the headings in
brackets — a section belongs where the app puts it, not where a category would.*

├── HOME
│   ├── Live Cars
│   └── Filter the board to one mechanic (All · Amlah · Hijaz · Unassigned)
│
├── Job Card
│   ├── Create, Update
│   ├── Auto suggestion
│   ├── Chassis Code & VIN
│   ├── Known plate fills the car (the last customer only offered)
│   ├── Spare Parts — Shop Price · Transport · Customer Price, with a suggested
│   │   price and its markup badge
│   ├── Ordered → "Expected in __ days"
│   ├── Import from / Move to Unassigned (Office and Owner)
│   └── Photos
│
├── Live Report
│   ├── Not filled in Bills
│   ├── Warranty not filled
│   ├── [Spares] Received (last 5 days)
│   ├── [Spares] On the Way (days waited · days left)
│   ├── [Spares] Not Ordered
│   └── [Still to do] Car list under Mech, with each car's open concerns
│
├── Completed
│   └── Done cars, ready to bill
│
├── Pending Payments
│   └── Fleet Accounts
│       ├── Fleet Job Cards
│       └── Payments, History
│
├── Paid Bills
│
├── High Discounts
│
├── Change History   (Owner only)
│   └── Deleted · Edited · Back-dated
│
├── Spare Shops
│   ├── Shop List
│   ├── Shop Details
│   ├── Payments
│   ├── Record a Discount (the tag symbol)
│   ├── Purchase History
│   └── Print Ledger
│
├── Unassigned Spares
│
├── Supplies Shops
│   ├── Shop List
│   ├── Shop Details
│   ├── Shop Catalog
│   ├── Restock / Purchase Bills
│   ├── Payments
│   └── Record a Discount (the tag symbol)
│
├── Inventory
│   ├── Categories
│   ├── Stock
│   ├── Low Stock
│   ├── Stock History
│   └── Usage by Mechanic
│
├── Car Profiles
│   ├── Car Jobcards
│   ├── Total billed, Discount, Paid, Still owed
│   ├── Gross Profit (Owner only)
│   ├── The two documents a profile hands over
│   │   ├── Service History (choices → printed sheet)
│   │   └── All Invoices (every bill for one car, one PDF)
│   └── Warranty → that car's warranty page
│
├── Warranty   (Office and Owner)
│   ├── Waiting for shop price
│   ├── Warranty cards (This Year · Last Year · All Time)
│   ├── New claim → a car → its finished bills → Claim one part
│   └── Warranty card (laid out as the job card)
│       ├── Claimed part — the shop's answer: blank, free, or what it cost
│       ├── Warranty slip (no prices; closes on WARRANTY)
│       └── Cancel claim
│
├── Estimates
│
├── Invoice
│   ├── Unfilled tracking
│   └── WhatsApp the customer (Owner only)
│
├── Salary & Advance
│
├── Deposit & Rent
│   ├── What to hand the collector today
│   ├── Deposit log (one month) — edit or delete from each row's ⋮
│   └── Update Rent (Owner only) — rate history
│
├── Owner Withdrawals   (Owner only)
│
├── Cashbook
│   ├── General expenses (Bus, food)
│   └── General income (Black Oil)
│
├── Notifications
│
├── Analysis & Reports
│   ├── Profit
│   │   ├── Cash Tracking
│   │   ├── Turnover − Expenses = Profit (and what warranty claims cost)
│   │   ├── The same profit, by what earned it
│   │   └── Position Right Now
│   └── Deep Analysis
│       ├── Mechanics
│       ├── Spare Parts
│       ├── Inventory
│       ├── Vehicles
│       ├── Fleet
│       ├── Shops
│       ├── Warranty
│       ├── Cashbook
│       └── Operations
│
├── Control Hub
│   ├── User Management
│   ├── Staff / Roster
│   └── Sessions / Security
│
├── Master Data
│       ├── Car Brands
│       ├── Car Models
│       ├── Used Concerns
│       └── Used Spare Parts
│           └── Edit, Delete, Merge
│
├── Legacy Data   (the go-live starting position — one day, then locked)
│   ├── Old Bills   (Office and Owner — the Excel years, typed in for history)
│   │   ├── Year blocks → month chips → the bills in a month
│   │   ├── Add / Edit a bill
│   │   └── Fill from PDF (reads the bill's own saved PDF into the form)
│   ├── Opening Stock   (Owner only — what is on the shelf, and what one cost)
│   ├── Opening Balances   (Owner only — what each shop's own book says)
│   └── Lock Legacy Data   (Owner only — three confirmations, then read-only
│       for everyone; only `manage.py unlock_legacy_data` on the server reopens it)
│
├── About   (Owner only — the system map, and what every section does)
│
└── Account / Security
    ├── Login, Logout
    └── Password Reset

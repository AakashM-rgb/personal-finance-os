# BUILD A PRODUCTION-QUALITY AI PERSONAL FINANCE / EXPENSE TRACKER

You are a senior full-stack engineer, product designer, UI/UX designer, database architect, security engineer, and AI engineer.

I want you to build a **premium, modern, production-quality personal finance web application**.

This must NOT look like a basic college CRUD project.

The goal is to create a website that people can actually use every day to understand, control, and improve their finances.

The product should feel comparable in quality to a modern SaaS product.

---

# 1. PRODUCT VISION

Build a product that follows this core loop:

**Record → Understand → Predict → Improve**

The application should help users:

- Track income
- Track expenses
- Understand spending
- Create budgets
- Track savings goals
- Track subscriptions
- Track recurring payments
- Manage multiple accounts
- Split expenses
- Analyze financial habits
- Track net worth
- Store receipts
- Search financial history
- Ask an AI assistant questions about their finances
- Receive useful financial insights
- Export their data

The application should feel like a:

> **Personal Financial Operating System**

not just an expense tracker.

---

# 2. IMPORTANT PRODUCT PRINCIPLES

Follow these principles throughout development:

1. Simple for beginners.
2. Powerful for advanced users.
3. Extremely fast expense entry.
4. Beautiful and modern UI.
5. Mobile-first responsive design.
6. Desktop experience must also be excellent.
7. Privacy-first architecture.
8. Secure financial data handling.
9. Never overwhelm users with unnecessary information.
10. Every dashboard component must provide useful information.
11. Avoid unnecessary animations.
12. Avoid fake AI features.
13. Avoid meaningless charts.
14. Use real calculations from database data.
15. Make the application scalable.

---

# 3. TARGET USERS

Design for:

### Students

Examples:

- College students
- Hostel students
- Students receiving monthly allowances

### Young professionals

Examples:

- Salaried employees
- Freelancers
- Developers
- Creators

### Families

Users who want to understand household spending.

The interface should work for both a user with ₹5,000/month and a user with ₹5,00,000/month.

---

# 4. DESIGN DIRECTION

Create a **premium SaaS dashboard**.

Visual direction:

- Minimal
- Clean
- Professional
- Modern
- Trustworthy
- Financial
- Premium
- Excellent typography
- Excellent spacing
- Clear hierarchy

Do NOT create:

- Generic bootstrap-looking pages
- Excessive gradients
- Excessive glassmorphism
- Giant text everywhere
- Too many cards
- Rainbow colors
- Unnecessary animations
- Cluttered dashboards

Use subtle animations only where they improve UX.

The UI must feel intentional.

---

# 5. RESPONSIVE DESIGN

The application must work perfectly on:

- Mobile
- Tablet
- Laptop
- Desktop
- Large monitors

Do not simply shrink desktop UI.

Create proper responsive layouts.

On mobile:

- Bottom navigation can be used.
- Important actions should remain accessible.
- Expense entry should be extremely fast.

On desktop:

- Sidebar navigation
- Multi-column dashboard
- Keyboard shortcuts
- Rich analytics

---

# 6. APPLICATION STRUCTURE

Create these primary sections:

```text
Dashboard
Transactions
Analytics
Budgets
Goals
Subscriptions
Accounts
Calendar
Reports
AI Assistant
Receipts
Settings
```

Optional future sections:

```text
Investments
Net Worth
Family
Shared Expenses
Financial Calculators
```

---

# 7. DASHBOARD

The dashboard is the most important screen.

It should answer:

> "How am I doing financially?"

Show:

### Financial Overview

- Total balance
- Total income
- Total expenses
- Savings
- Savings rate
- Net worth

Example:

```text
Total Balance
₹42,580

Income
₹60,000

Expenses
₹17,420

Saved
₹42,580
```

---

# 8. FINANCIAL HEALTH SCORE

Create a financial health score from 0–100.

Example:

```text
Financial Health

82 / 100

GOOD
```

Calculate it from meaningful factors such as:

- Savings rate
- Budget adherence
- Debt burden
- Emergency fund
- Recurring expense ratio
- Spending consistency

Never randomly generate the score.

Explain why the score exists.

Example:

```text
+ Strong savings rate
+ Good budget control
+ Low recurring expenses
- High shopping spending
```

---

# 9. MONTHLY SPENDING

Show:

- Current month spending
- Previous month spending
- Percentage change
- Daily average
- Projected monthly spending

Example:

```text
September

Spent:
₹17,420

Last month:
₹15,200

+14.6%
```

---

# 10. CATEGORY BREAKDOWN

Default categories:

```text
Food
Transport
Shopping
Bills
Entertainment
Education
Health
Travel
Subscriptions
Rent
Utilities
Insurance
Investment
Other
```

Allow users to create custom categories.

Each category should support:

- Name
- Icon
- Color
- Budget
- Parent category

---

# 11. FAST EXPENSE ENTRY

This is one of the most important features.

Create a beautiful quick-add experience.

The user should be able to enter:

```text
120 food lunch
```

and the system should understand:

```text
Amount: ₹120
Category: Food
Description: Lunch
Date: Today
```

Another example:

```text
450 uber college
```

becomes:

```text
Amount: ₹450
Category: Transport
Description: Uber college
```

Also support:

```text
₹250 dinner
```

Provide normal form entry as a fallback.

---

# 12. VOICE EXPENSE ENTRY

Allow:

> "I spent 250 rupees on dinner."

Convert speech into a transaction.

Show a confirmation before permanently saving if confidence is low.

---

# 13. TRANSACTIONS PAGE

Create a powerful transaction management page.

Features:

- Search
- Filter
- Sort
- Date range
- Category filter
- Account filter
- Income/expense filter
- Amount range
- Recurring filter
- Tags

Example:

```text
Search:
"Amazon"

Filters:
September
Shopping
Above ₹1,000
```

---

# 14. TRANSACTION DETAILS

Every transaction should support:

```text
Amount
Type
Category
Description
Date
Time
Account
Payment method
Merchant
Tags
Notes
Receipt
Recurring status
```

Allow:

- Edit
- Delete
- Duplicate
- Attach receipt

---

# 15. BUDGETS

Users can create:

```text
Food          ₹5,000
Transport     ₹3,000
Shopping      ₹4,000
Entertainment ₹2,000
```

Display:

```text
Food
₹3,240 / ₹5,000

64.8%
```

Budget statuses:

- Healthy
- Warning
- Near limit
- Exceeded

Create smart warnings.

Example:

> You've used 85% of your food budget.

---

# 16. SMART BUDGET PREDICTION

Based on historical spending, estimate:

> "At your current rate, you'll spend approximately ₹5,650 on food this month."

Allow the user to accept or ignore suggested budgets.

---

# 17. SAVINGS GOALS

Users can create goals.

Example:

```text
Goal:
New Laptop

Target:
₹1,50,000

Current:
₹45,000

Remaining:
₹1,05,000
```

Show:

- Progress
- Target date
- Required monthly savings
- Required weekly savings

Example:

> Save ₹8,750/month to reach your target by September 2027.

Allow multiple goals.

---

# 18. RECURRING EXPENSES

Support:

- Daily
- Weekly
- Monthly
- Quarterly
- Yearly

Examples:

```text
Rent
Netflix
Spotify
Internet
Insurance
Gym
Loan
```

Automatically generate upcoming transactions.

---

# 19. SUBSCRIPTION MANAGER

Create a dedicated subscription page.

Display:

```text
Netflix       ₹649/month
Spotify       ₹119/month
Adobe         ₹1,675/month
GitHub        ₹400/month
```

Calculate:

```text
Monthly:
₹2,843

Yearly:
₹34,116
```

Show upcoming renewals.

Detect potentially unused subscriptions based on user activity only if the necessary data exists.

Never claim a subscription is unused without evidence.

---

# 20. MULTIPLE ACCOUNTS

Support:

```text
Bank Account
Cash
Credit Card
UPI
Savings Account
Wallet
```

Each account:

```text
Name
Type
Current balance
Currency
Institution name (optional)
```

Transfers between accounts must NOT count as income or expenses.

This is very important.

---

# 21. CREDIT CARD TRACKING

Support:

```text
Credit Limit
Current Usage
Available Credit
Statement Date
Payment Due Date
Minimum Payment
```

Show:

```text
₹32,450 / ₹1,00,000

32.45% utilization
```

Warn users when utilization becomes high.

---

# 22. EXPENSE SPLITTING

Allow users to split expenses.

Example:

```text
Dinner
₹2,400

4 people

You        ₹600
Person 2   ₹600
Person 3   ₹600
Person 4   ₹600
```

Track:

- Who paid
- Who owes
- Amount owed
- Settled/unsettled

---

# 23. CALENDAR

Create a financial calendar.

Each day can show:

- Total spending
- Income
- Bills
- Recurring expenses

Click a day to see transactions.

---

# 24. ANALYTICS

Create a professional analytics section.

Charts:

### Spending over time

Line chart.

### Category breakdown

Donut/pie chart.

### Income vs expenses

Bar chart.

### Savings trend

Line chart.

### Budget performance

Progress visualization.

### Daily spending

Bar chart.

### Recurring expenses

Breakdown.

Do not add charts just for decoration.

Every visualization must answer a question.

---

# 25. SPENDING INSIGHTS

Automatically detect useful patterns.

Examples:

> Food spending increased 28% compared with last month.

> Weekend spending is 42% higher than weekday spending.

> Your average daily spending is ₹580.

> Transport is your second-largest category.

> Your recurring expenses account for 31% of monthly spending.

Only generate insights when the underlying data actually supports them.

---

# 26. FINANCIAL AI ASSISTANT

Create an AI assistant specifically for the user's financial data.

Example questions:

```text
Where am I spending the most?

How much did I spend on food this month?

How much did I spend on Amazon?

Compare this month with last month.

What are my biggest recurring expenses?

Can I afford a ₹70,000 phone?

How much should I save each month?

What category increased the most?

How much did I spend this year?
```

The AI must use actual application data.

Do not hallucinate transactions.

If information isn't available:

> "I don't have enough data to answer that."

---

# 27. AI FINANCIAL SUMMARY

Every week/month, generate a concise summary.

Example:

```text
YOUR MONTHLY MONEY SUMMARY

You spent ₹17,420 this month.

Top category:
Food — ₹4,250

Compared with last month:
+14%

Good:
You saved 32% of your income.

Watch:
Shopping spending increased by 41%.

Suggestion:
Reducing shopping by ₹1,500/month would increase
your annual savings by approximately ₹18,000.
```

---

# 28. RECEIPT SCANNER

Allow users to upload:

- JPG
- PNG
- PDF

Extract:

```text
Merchant
Date
Total
Tax
Items
Category
```

Show extracted information before saving.

User must be able to correct OCR mistakes.

---

# 29. RECEIPT STORAGE

Attach receipts to transactions.

Example:

```text
Laptop
₹74,999

Receipt
Invoice.pdf

Purchase:
12 Aug 2026

Warranty:
1 year
```

---

# 30. NATURAL LANGUAGE SEARCH

Users should be able to search using natural language.

Examples:

```text
food last month

Amazon purchases above ₹1000

all transport expenses in August

my biggest expenses this year

weekend spending

subscriptions this month
```

Convert the request into safe database queries.

Never allow arbitrary AI-generated SQL to execute directly.

Use validated query structures.

---

# 31. NET WORTH

Create optional net worth tracking.

Assets:

```text
Cash
Bank
Investments
Gold
Property
Other assets
```

Liabilities:

```text
Credit cards
Loans
Other debt
```

Formula:

```text
Net Worth = Total Assets - Total Liabilities
```

Show historical net-worth growth.

---

# 32. REPORTS

Generate:

- Monthly report
- Yearly report
- Category report
- Income report
- Expense report
- Budget report
- Savings report
- Net worth report

Allow:

- PDF export
- CSV export
- Excel export

---

# 33. IMPORT

Support:

```text
CSV
Excel
Bank statement CSV
```

Create a mapping interface:

```text
Bank column → Application field

Transaction Date → Date
Description → Description
Debit → Expense
Credit → Income
```

Preview before importing.

Detect duplicates.

---

# 34. EXPORT

Users must be able to export their data.

Formats:

```text
CSV
Excel
JSON
PDF reports
```

The user should never feel locked into the platform.

---

# 35. NOTIFICATIONS

Useful notifications only.

Examples:

```text
Budget warning

Upcoming subscription

Upcoming credit-card payment

Savings goal progress

Unusual spending

Recurring expense
```

Allow users to configure notification preferences.

---

# 36. FINANCIAL CALCULATOR TOOLBOX

Add a separate tools section:

```text
EMI Calculator
SIP Calculator
Compound Interest Calculator
Savings Calculator
Loan Calculator
Inflation Calculator
Emergency Fund Calculator
Retirement Calculator
```

Make them fast and accurate.

---

# 37. EMERGENCY FUND

Allow users to define essential monthly expenses.

Calculate:

```text
Monthly essential expenses:
₹25,000

Target:
6 months

Emergency fund:
₹1,50,000
```

Show progress.

---

# 38. GAMIFICATION

Use subtle gamification.

Examples:

```text
7-day spending streak

Budget Master

First ₹10,000 saved

No-Spend Weekend

Goal Achieved
```

Do NOT make financial management feel like a childish game.

---

# 39. SEARCH-FIRST UX

Global search should be available.

Keyboard shortcut:

```text
Ctrl + K
```

Search:

- Transactions
- Accounts
- Goals
- Subscriptions
- Reports
- Settings

---

# 40. KEYBOARD SHORTCUTS

Add useful shortcuts.

Example:

```text
N → New transaction
G D → Dashboard
G T → Transactions
G A → Analytics
G B → Budgets
Ctrl + K → Search
Esc → Close modal
```

Display shortcuts in a help panel.

---

# 41. AUTHENTICATION

Implement secure authentication.

Support:

- Email/password
- Google OAuth if configured
- Email verification
- Password reset
- Session management
- Logout from all devices

Passwords must NEVER be stored in plaintext.

Use secure password hashing.

---

# 42. SECURITY

Treat financial data as sensitive.

Implement:

- Input validation
- Authentication checks
- Authorization checks
- Rate limiting
- CSRF protection where applicable
- Secure cookies
- SQL injection protection
- XSS protection
- File validation
- Upload limits
- Secure API design
- Proper error handling
- Audit logging for sensitive actions

Never expose private financial data through public endpoints.

Users can ONLY access their own data.

---

# 43. DATABASE DESIGN

Use a properly normalized database.

Core entities:

```text
users
accounts
transactions
categories
budgets
budget_items
goals
subscriptions
recurring_transactions
receipts
shared_expenses
expense_participants
notifications
financial_insights
user_settings
audit_logs
```

Every user-owned entity must have a clear ownership relationship.

Use proper foreign keys.

Add indexes to commonly queried fields.

---

# 44. TRANSACTION MODEL

A transaction should support:

```text
id
user_id
account_id
type
amount
currency
category_id
merchant
description
date
time
payment_method
notes
is_recurring
recurring_transaction_id
receipt_id
created_at
updated_at
```

For transfers, use a proper transfer model or linked transaction mechanism so that account transfers don't distort income/expense analytics.

---

# 45. MONEY HANDLING

NEVER use floating-point numbers for financial calculations.

Use:

- Decimal
- Integer minor units such as paise

Example:

₹120.50

Store safely as:

```text
12050 paise
```

or use a database decimal type.

All calculations must avoid floating-point errors.

---

# 46. CURRENCY

Initially prioritize INR.

Architecture must support future currencies:

```text
INR
USD
EUR
GBP
JPY
```

Each transaction should have a currency.

---

# 47. API DESIGN

Create clean REST APIs.

Example:

```text
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout

GET    /api/dashboard

GET    /api/transactions
POST   /api/transactions
GET    /api/transactions/{id}
PUT    /api/transactions/{id}
DELETE /api/transactions/{id}

GET    /api/categories
POST   /api/categories

GET    /api/budgets
POST   /api/budgets
PUT    /api/budgets/{id}

GET    /api/goals
POST   /api/goals
PUT    /api/goals/{id}

GET    /api/accounts
POST   /api/accounts

GET    /api/subscriptions
POST   /api/subscriptions

GET    /api/analytics

POST   /api/receipts/upload

POST   /api/ai/chat

GET    /api/reports/monthly
```

Use proper HTTP status codes.

Return consistent JSON responses.

---

# 48. FRONTEND ARCHITECTURE

Use a modern component-based architecture.

Components should be reusable.

Example:

```text
components/
├── ui/
├── dashboard/
├── transactions/
├── budgets/
├── goals/
├── analytics/
├── subscriptions/
├── accounts/
├── receipts/
├── ai/
└── charts/
```

Avoid giant components.

Separate business logic from presentation.

---

# 49. BACKEND ARCHITECTURE

Use clean architecture.

Example:

```text
backend/
├── app/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── repositories/
│   ├── auth/
│   ├── ai/
│   ├── analytics/
│   ├── utils/
│   └── main.py
├── migrations/
└── tests/
```

Use service layers for business logic.

Do not put all logic inside route handlers.

---

# 50. AI ARCHITECTURE

AI should NEVER have unrestricted access to the database.

Create controlled tools/functions such as:

```text
get_monthly_spending()
get_category_spending()
get_transactions()
get_budget_status()
get_savings_goals()
get_recurring_expenses()
get_account_balances()
compare_periods()
```

The AI can call these tools.

Then construct the answer from verified data.

---

# 51. AI SAFETY

The AI is an informational assistant.

It should NOT present itself as a licensed financial advisor.

For major financial decisions:

- Show assumptions
- Show calculations
- Explain limitations
- Avoid guaranteed returns
- Avoid personalized investment recommendations without appropriate safeguards

---

# 52. PERFORMANCE

Optimize for speed.

Requirements:

- Lazy loading
- Pagination
- Database indexes
- Efficient queries
- Caching where appropriate
- Optimized images
- Code splitting
- Debounced search
- Background processing for OCR
- Background processing for expensive AI tasks

Dashboard should load quickly.

---

# 53. EMPTY STATES

Do not show empty blank screens.

Example:

Instead of:

> No transactions.

Show:

> You haven't added any transactions yet.

Then provide:

**+ Add your first expense**

---

# 54. ERROR STATES

Errors should be understandable.

Bad:

> 500 Internal Server Error

Better:

> Something went wrong while loading your transactions. Please try again.

For forms:

> Amount must be greater than ₹0.

---

# 55. LOADING STATES

Use skeleton loaders rather than flashing blank screens.

Do not overuse spinners.

---

# 56. ACCESSIBILITY

Support:

- Keyboard navigation
- Screen readers
- Proper labels
- Focus states
- Sufficient contrast
- Semantic HTML
- Accessible modals
- Accessible charts where possible

---

# 57. DARK MODE

Support:

- Light mode
- Dark mode
- System preference

Persist the user's preference.

---

# 58. SETTINGS

Create:

```text
Profile
Currency
Language
Theme
Notifications
Security
Privacy
Data export
Data deletion
Connected accounts
AI settings
```

---

# 59. PRIVACY

Make privacy a major selling point.

Clearly communicate:

- What data is stored
- Why it is stored
- What AI can access
- How receipts are processed
- How data can be exported
- How the account can be deleted

Never sell financial data.

---

# 60. LANDING PAGE

Create a premium landing page.

Hero:

> **Know where your money goes.**
>
> Track spending, plan your future, and make smarter financial decisions.

CTA:

**Start Tracking Free**

Sections:

```text
Hero
Features
Dashboard preview
AI assistant
Analytics
Budgeting
Savings goals
Privacy
Testimonials placeholder
FAQ
CTA
Footer
```

Do not use fake testimonials.

---

# 61. DEMO MODE

Create optional demo data for first-time users.

Example:

```text
Income:
₹60,000

Expenses:
₹17,420

Savings:
₹42,580
```

This lets users understand the product immediately.

Clearly label demo data.

---

# 62. MOBILE UX

On mobile, prioritize:

```text
Home
Transactions
Add
Analytics
More
```

The Add button should be extremely accessible.

The user should be able to record an expense in a few seconds.

---

# 63. PWA

Make the website installable as a Progressive Web App if technically appropriate.

Support:

- Install
- Offline shell
- Cached UI
- Local draft expense entry

When offline, transactions can be queued locally and synced securely when connectivity returns.

Do NOT silently lose data.

---

# 64. TESTING

Create tests for:

### Backend

- Authentication
- Transactions
- Budgets
- Goals
- Recurring expenses
- Transfers
- Analytics
- Authorization
- Money calculations

### Frontend

- Forms
- Navigation
- Transaction creation
- Filters
- Responsive layouts

### Critical calculations

Test:

- Totals
- Budget percentages
- Savings rates
- Net worth
- Credit utilization
- Recurring expenses
- Currency calculations

---

# 65. SEED DATA

Create realistic seed/demo data.

Use realistic examples such as:

```text
Salary
Rent
Food
Uber
Amazon
Netflix
Spotify
Electricity
Internet
College
Shopping
```

Do not use real people's private data.

---

# 66. DEVELOPMENT PROCESS

Do NOT attempt to blindly generate the entire application in one huge file.

Work systematically.

### Phase 1

Set up:

- Repository
- Frontend
- Backend
- Database
- Environment configuration
- Authentication

### Phase 2

Build:

- Accounts
- Categories
- Transactions
- Dashboard

### Phase 3

Build:

- Budgets
- Goals
- Recurring expenses
- Subscriptions

### Phase 4

Build:

- Analytics
- Calendar
- Reports

### Phase 5

Build:

- Receipt OCR
- AI assistant
- Natural-language search

### Phase 6

Build:

- Security hardening
- Testing
- Performance optimization
- PWA
- Deployment

---

# 67. IMPORTANT CODING RULE

Before implementing a feature:

1. Understand the existing architecture.
2. Inspect relevant files.
3. Do not unnecessarily rewrite working code.
4. Reuse components.
5. Keep code maintainable.
6. Add types.
7. Validate inputs.
8. Handle errors.
9. Write tests for important business logic.

---

# 68. GIT WORKFLOW

Use meaningful commits.

Examples:

```text
feat: add transaction management
feat: add budget tracking
feat: add savings goals
feat: add subscription tracking
feat: add analytics dashboard
feat: add AI financial assistant
fix: correct transfer calculations
refactor: improve transaction service
```

Do not create meaningless commits.

---

# 69. ENVIRONMENT VARIABLES

Never hardcode:

- API keys
- Database passwords
- AI API keys
- OAuth secrets
- Encryption secrets

Use `.env`.

Create `.env.example`.

Never commit `.env`.

---

# 70. DOCUMENTATION

Create:

```text
README.md
ARCHITECTURE.md
API.md
DATABASE.md
SECURITY.md
AI.md
DEPLOYMENT.md
```

Explain:

- Setup
- Environment variables
- Database migrations
- Running locally
- Testing
- Deployment
- Architecture decisions

---

# 71. FINAL QUALITY BAR

Before considering the project complete, inspect the entire application.

Check:

### UX

- Does every page look polished?
- Are empty states good?
- Are loading states good?
- Are errors understandable?
- Is mobile responsive?

### Functionality

- Can users create transactions?
- Edit them?
- Delete them?
- Search them?
- Filter them?
- Create budgets?
- Track goals?
- Track subscriptions?
- Analyze spending?

### Security

- Can one user access another user's data?
- Are APIs protected?
- Are uploads validated?
- Are secrets protected?

### Financial correctness

- Are transfers excluded from income/expense calculations?
- Are decimal calculations accurate?
- Are budgets accurate?
- Is net worth accurate?
- Are recurring expenses handled correctly?

### AI

- Does AI use actual user data?
- Can it hallucinate transactions?
- Are tool calls controlled?
- Does it clearly state uncertainty?

---

# 72. MOST IMPORTANT PRODUCT FEATURE

The application should continuously answer:

> **"What should I know about my money right now?"**

For example:

```text
GOOD MORNING 👋

Your Money Today

💰 Balance
₹42,580

📊 Spending
₹580 today

🎯 Savings
₹8,200 / ₹10,000 goal

⚠️ Attention
Your shopping budget is 87% used.

📅 Upcoming
Internet bill — ₹999 tomorrow

🤖 AI Insight
You're spending 24% more on food
than your 3-month average.
```

This should make the dashboard feel alive and useful.

---

# 73. TECH STACK

Preferred stack:

### Frontend

- Next.js
- TypeScript
- Tailwind CSS
- Modern component library
- Recharts or another suitable charting library

### Backend

- Python
- FastAPI
- Pydantic

### Database

- PostgreSQL

### ORM

- SQLAlchemy

### Authentication

- Secure session/JWT architecture as appropriate

### AI

Use a provider abstraction so the AI provider can be changed later.

### Storage

Object storage for receipts.

### Background jobs

Use a proper job/queue system when required for:

- OCR
- AI processing
- recurring transaction generation
- notifications

---

# 74. IMPORTANT

Do NOT sacrifice functionality for visual design.

Do NOT sacrifice security for convenience.

Do NOT sacrifice financial correctness for AI features.

Do NOT build fake functionality.

If an external API is not configured, create a clean abstraction and a mock/demo implementation rather than pretending the integration works.

---

# 75. STARTING INSTRUCTION

First inspect the repository and existing project.

Determine:

1. What framework already exists?
2. What files exist?
3. What database exists?
4. What dependencies already exist?
5. What architecture is already present?

Then create a concise implementation plan.

After the plan, begin implementing the project systematically.

Do not ask unnecessary questions.

Make reasonable engineering decisions yourself.

If something is ambiguous, choose the most maintainable production-quality solution and document the decision.

Build the application feature-by-feature and keep the project runnable after each major phase.

The final result should feel like a **real premium personal-finance SaaS product**, not a tutorial project.

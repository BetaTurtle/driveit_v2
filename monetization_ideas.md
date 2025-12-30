# Monetization Strategies for DriveIt

Since DriveIt solves a specific convenience problem (saving Telegram files to Google Drive without downloading them locally first), users are likely willing to pay for **convenience**, **speed**, and **automation**.

Here are several models you can adopt:

## 1. Pay-Per-Use (The "Top-up" Model)
This is the simplest and most transparent model for utility bots.

### Tier Structure
| Type | Limit | Reset | Price |
| :--- | :--- | :--- | :--- |
| **Free Tier** | 100 MB | Daily | $0 |
| **Top-up (Small)** | 2 GB | Lifetime | **100 Stars** |
| **Top-up (Large)** | 10 GB | Lifetime | **400 Stars** |

### Why this works:
1. **Low Friction:** 100MB is enough for a few photos or documents. Users who want to save a video note or high-res photo will immediately hit the limit, prompting a small purchase.
2. **Predictable Costs:** You only pay for what the user actually uploads.
3. **High conversion:** Small amounts of Stars (100) are psychologically easy to spend for immediate convenience.

### Safe Estimation: Stars per GB
To cover costs (GCP Egress + CPU) while ensuring a healthy profit margin:

> [!TIP]
> **Recommended Rate: 50 Stars per 1 GB**
> - **Revenue:** 50 Stars (~$1.00 USD).
> - **Telegram Cut (30%):** You keep ~$0.70.
> - **Your Cost (GCP Egress):** ~$0.15.
> - **Profit:** **$0.55 per GB.**

### 5GB Bundle Comparison:
- **Cost to you:** ~$0.75.
- **Retail Price:** **200 Stars** (~$4.00).
- **Your Net Profit:** **~$2.05.**


## 3. Lifetime License
A one-time payment for permanent access.
- **Example:** $29.99 for lifetime access.
- **Why it works:** Telegram users often prefer one-time purchases over subscriptions for utilities.

## 4. Enterprise / Power User Features
Target heavy users or channels.
- **Auto-Backup Channels:** Automatically save *every* file posted in a specific channel to a specific Drive folder.
- **Team Drives:** Support for Google Workspace Shared Drives.
- **White Labeling:** Allow them to set their own bot name/icon (complex to implement).

## Technical Implementation

### 1. Daily Usage Tracking (Firestore)
To enforce the 100MB daily limit, we need to track usage with a date-check logic in `update_usage_stats`:

```python
# Proposed logic for app/services/firebase_service.py
today = datetime.utcnow().strftime('%Y-%m-%d')
user_data = doc_ref.get().to_dict()
daily_data = user_data.get('usage', {}).get('daily', {})

if daily_data.get('date') == today:
    # Increment existing daily total
    updates["usage.daily.bytes"] = firestore.Increment(file_size_bytes)
else:
    # Reset for a new day
    updates["usage.daily.date"] = today
    updates["usage.daily.bytes"] = file_size_bytes
```

### 2. Telegram Stars Transaction Flow
The transaction is a handshake between the Mini App UI and the Bot API backend.

1. **Initiation (Mini App)**:
   - User clicks "Buy 5GB".
   - Mini App calls your Deno/Python backend `/create-invoice`.
2. **Generation (Backend)**:
   - Backend calls Telegram Bot API `createInvoiceLink`.
   - Returns a unique `https://t.me/$invoice_hash` link to the Mini App.
3. **Payment (Telegram Native)**:
   - Mini App calls `Telegram.WebApp.openInvoice(url)`.
   - Telegram shows the native Star payment sheet.
4. **Confirmation (Bot API)**:
   - Telegram sends a `PreCheckoutQuery` to your bot.
   - Telegram sends a `SuccessfulPayment` message to your bot.
5. **Fulfillment (Backend)**:
   - Bot detects the payment and increments the user's `usage.paid_allowance` in Firestore.

### 3. Star Prices (Safe Estimates)

| Data Amount | Star Price | Your Profit |
| :--- | :--- | :--- |
| **5 GB** | **250 Stars** | ~$2.75 |
| **20 GB** | **800 Stars** | ~$9.00 |
| **50 GB** | **1800 Stars** | ~$22.00 |

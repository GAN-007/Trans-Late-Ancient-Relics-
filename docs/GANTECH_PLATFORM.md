# GAN-TECH platform: subscriptions and enquiries

Trans-Late Ancient Relics is one of the products of the GAN-TECH group. Customers subscribe to it on the group platform
([gan-tech.pro](https://gan-tech.pro)): organisations, plans, trials, invoices and M-Pesa payments live there.
This app asks the platform whether the person signing in belongs to an organisation with an active plan,
and can forward enquiries to the group inbox.

The client is `app/gantech_platform.py`: `has_access(email)`, `check_access(email)` and `forward_enquiry(...)`. It has no extra dependencies and **does nothing until it is configured**,
so merging this changes no behaviour.

## Switch it on

1. On the platform, issue this product's key (an administrator, against the platform database):
   `npm run keys:products -- trans-late-ancient-relics`. It prints the three values below once.
2. Set them in this app's environment:

   ```
   GANTECH_API_URL=https://gan-tech.pro/api/v1
   GANTECH_API_KEY=gt_live_…        # scopes: access_read, leads_write — limited to trans-late-ancient-relics
   GANTECH_PRODUCT=trans-late-ancient-relics
   GANTECH_ACCESS_FAIL_MODE=open    # or "closed" to refuse sign-in when the platform can't be reached
   ```

3. Add the check where people sign in:

```python
# Where a signed-in user starts a paid feature:
from app.gantech_platform import has_access

if not has_access(user_email):
    raise HTTPException(status_code=403, detail="Your organisation doesn't have an active Trans-Late plan.")
```

## What the platform answers

`GET /api/v1/access?email=…&product=trans-late-ancient-relics` returns `access` (true while the organisation's plan is on
a trial or active; false when pending payment, overdue, paused or ended) plus the organisation, the person's
role and each subscription's plan, status, seats, trial end and renewal date. Answers are cached for a minute.
Unknown people get `access: false`.

To react immediately instead of on the next sign-in, subscribe a webhook on the platform to
`subscription.created` / `subscription.updated` (signed with HMAC-SHA256, header `X-GanTech-Signature`).

## Tests

`python -m pytest -q tests/test_gantech_platform.py` — runs against a local fake platform; no network access.

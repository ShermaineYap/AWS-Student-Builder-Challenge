# Deploy checklist

About 45 minutes end to end. Do it in this order; each step has a check so you know it worked.

Deadline: **Fri 6 Nov, 11:59 PM PST = Sat 7 Nov, 3:59 PM Malaysia time.** Aim to submit by Friday afternoon your time.

## 0. Fill in the personal bits (10 min)

Already done: your GitHub profile and this repo are linked on the site. Still yours to add — search `index.html` for `TODO`:

| Where | What to put |
|---|---|
| ODL project | A link to your ODL notebook or report (the link is commented out until then) |
| AI Builder Cup | One or two sentences on what you actually built |
| Contact | Your LinkedIn URL (commented out until then); add email only if you want it public |
| About | Check every sentence is true for you now: degree status, city, what you're doing next |
| `README.md` | Live site URL (after step 2) |

Your student ID is deliberately left off the public site. Edit files right on GitHub (pencil icon) — each commit redeploys the site once Amplify is connected.

## 1. GitHub (done)

Everything is already in https://github.com/ShermaineYap/AWS-Student-Builder-Challenge on `main`, with `index.html` at the top level.

## 2. Amplify Hosting (5 min)

Follow Day 4 of the official guide: Amplify → Deploy an app → GitHub → select `AWS-Student-Builder-Challenge`, branch `main`. Build command empty, output directory `/`. Save and deploy.

Check: "Visit deployed URL" opens the site. Click the shuttlecock and play one point. (The leaderboard line won't appear yet; that's expected.)

📸 Screenshot: Amplify app overview showing **Deployed**.

## 3. Backend: leaderboard (10 min)

Use the **same AWS project and Region** as Amplify.

**Option A: console, no tools needed**
1. AWS Console → CloudFormation → Create stack → *With new resources* → *Upload a template file* → choose `backend/template.yaml`.
2. Stack name: `rally`.
3. Parameters:
   - `AllowedOrigin`: your Amplify URL, e.g. `https://main.d1abc2def3.amplifyapp.com` (no trailing slash)
   - `BudgetEmail`: your email
4. Tick "I acknowledge that AWS CloudFormation might create IAM resources" → Submit.
5. Wait for **CREATE_COMPLETE** (2–3 min). Open the **Outputs** tab and copy `ApiUrl`.

**Option B: your coding agent** (if you set up the Agent Toolkit on Day 2), paste:
> Deploy `backend/template.yaml` as a CloudFormation stack named `rally` in this project's Region with parameters AllowedOrigin=<your Amplify URL> and BudgetEmail=<your email>, acknowledging IAM capabilities. When it finishes, tell me the ApiUrl output. Don't change anything else.

If the stack fails on `MonthlyBudget` (some project accounts restrict Budgets), delete the failed stack, redeploy with `BudgetEmail` empty, and create a US$1 monthly budget by hand in Billing → Budgets.

Check: open `<ApiUrl>/stats` in your browser. You should see `{"matches": 0, "shots": 0, "reads": 0, "visitorWins": 0}`.

📸 Screenshots: CloudFormation stack Resources tab; Lambda function page; DynamoDB table; API Gateway routes; Budgets page.

## 4. Connect the site to the API (3 min)

1. In `config.js`, set `window.RALLY_API = "<ApiUrl>";` (no trailing slash).
2. Commit to GitHub. Amplify redeploys by itself in about a minute.

Check: play a full match on the live site. The end screen now says "Across N matches played on this site…". Refresh `<ApiUrl>/stats` and `matches` has gone up.

📸 Screenshots: the Rally end screen with the global line; DynamoDB item (Explore items) showing the totals.

## 5. Final checks before submitting

- [ ] Every nav link scrolls to its section; project links open the right pages
- [ ] Site on your phone: menu fits, game playable, no sideways scrolling
- [ ] Play with the keyboard only (number keys 1–9, Esc to close)
- [ ] Live URL works in a private/incognito window
- [ ] Don't delete or change the Amplify app or the stack until winners are announced (week of 23 Nov)

## Screenshots for the submission (collect as you go)

1. Hero on desktop  2. Rally mid-rally with the locked guess  3. Rally reveal with the prediction bars  4. End screen with the global stat  5. Mobile view  6. Amplify Deployed  7. CloudFormation resources  8. Lambda  9. DynamoDB item  10. API Gateway routes and throttling  11. Budgets  12. Architecture diagram (`docs/architecture.png`)

Hide your account ID and email in any console screenshot.

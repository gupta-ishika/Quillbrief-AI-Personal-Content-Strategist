# DESIGN: AI Personal Content Strategist

Status: Draft v1.1, under review
Scope: how the React UI should look and behave.

---

## 1. Style

Modern, minimal and professional. The product is a working tool for one creator, so clarity matters more than decoration. Every screen answers two questions: what needs my attention, and why did the system suggest this.

---

## 2. Design tokens

### Typography
- Font: Inter, with a system sans-serif fallback.
- Page title 24px semibold. Section title 18px semibold. Body 14px regular. Caption 12px.
- Line height 1.5 for body text.

### Colors
- Primary: `#6366F1`
- Background: `#F8FAFC`
- Surface (cards): `#FFFFFF`
- Text: `#0F172A`
- Muted text: `#64748B`
- Border: `#E2E8F0`
- Success: `#16A34A`. Warning: `#D97706`. Error: `#DC2626`. Info: `#2563EB`.

### Shape and spacing
- Card radius 12px. Button and input radius 8px.
- Spacing scale in multiples of 4px. Standard card padding 20px.
- Light shadow on cards. No heavy shadows.

---

## 3. Layout

- Left sidebar navigation on desktop. Content area with a maximum width of 1100px.
- On tablet the sidebar collapses to icons. On mobile it becomes a bottom bar.
- A badge on the Approvals item shows the number of pending requests.
- Main screen: Approvals inbox. It is the first place the creator goes, because paused runs wait there.
- Until onboarding is completed, the app shows the onboarding screen (section 4.0) instead of the navigation above.

Navigation items:
1. Home (new goal)
2. Approvals
3. Briefs
4. Library
5. Insights
6. Runs
7. Settings

---

## 4. Screens

### 4.0 First-run onboarding

Shown instead of the app shell (no sidebar) until onboarding is completed. Layout: centered card, progress text ("Step 2 of 4"), Back and Continue. Values are kept when moving backward. Each step saves when the creator continues.

**Step 1: Your niche.** "What do you create content about?" One required text input, placeholder "e.g., Python tutorials, backend development and FastAPI", live counter against 200. Continue is disabled when empty or over the limit.

**Step 2: Your tone.** "How should your content sound?" Five selectable preset cards (one required) and an optional text area "Additional tone instructions" with a counter against 500.

**Step 3: Your YouTube channel (optional).**
- Text input: "Channel handle, ID or URL". A Check button shows the resolved channel title for confirmation. Unsupported URL forms show "Paste your @handle or channel ID instead."
- Divider "or", then "Connect YouTube (read-only)" with the note "Lets you pick your channel and enables owner analytics. It cannot post or change anything."
- After connecting, a list of the account's channels appears. Selecting one marks it Verified. Denied consent or an error shows a plain message with Retry. The OAuth redirect returns to this screen with earlier steps intact.
- If the API key is not configured, a warning says: "Public video and comment data is unavailable until `YOUTUBE_API_KEY` is set in your `.env` file and the backend is restarted. A handle you enter now is saved as unverified."
- Help text: "Identifying your channel does not download anything by itself."
- "Skip for now" is always available. It saves the skip and goes to Review.

**Step 4: Review.** Summary rows: niche, tone and instructions, channel with a Verified, Unverified or None badge and an Add or Change action that returns to step 3, YouTube login status, YouTube API key status (read-only, no input), and Weekly Brief schedule with time zone (default Monday 08:00, Asia/Kolkata) with a Change action. The schedule comes from `GET /settings` and the rest from `GET /onboarding`. "Finish setup" is primary. If saving fails, values are kept and an error with Retry is shown. Finishing opens Home. No run starts.

**Rules:** no raw errors, labelled inputs with visible focus, keyboard navigation, tested at 375px, 768px and 1440px. After data deletion, onboarding appears again with a short note that data was removed. This applies only before "Finish setup" succeeds: if the creator skipped the channel step and reopens the app before finishing, onboarding resumes at Review, where the channel can still be added. Once setup is finished, the app opens directly on the main screen.

### 4.1 Home: new goal
- Large goal text box with an example placeholder.
- Depth selector with three options and a one-line explanation for each (Quick, Standard, Deep). Standard is preselected.
- Start button. After starting, the screen shows live run progress: current agent, task list, tokens used.

### 4.2 Approvals inbox
- List of pending requests, oldest first, with type badges: Plan, Draft, Depth increase. A plan that belongs to a Weekly Brief shows a "Weekly Brief" label next to its Plan badge.
- A request whose item was replaced by a newer version disappears from the pending list. If the creator opens an old link, the screen says "This item changed. Open the latest version to review it." and offers a link.
- Each row shows the title, the run goal and the time waiting.
- Empty state: "Nothing is waiting for you."

### 4.3 Plan review
- Plan items as cards. Each card shows topic, format, platform, objective and reason.
- A source badge on every card: Comment, Similar creator or Own idea. Opening the badge shows the evidence behind it.
- Actions for the whole plan: Approve, Reject with feedback, Edit. The creator can also drop single items.
- Header shows the plan version. Editing an approved plan creates a new version that needs approval again, and the screen says so before saving.
- Header shows what the plan is based on, for example "Based on 450 of 10,240 comments".

### 4.4 Draft review
- Draft text in a readable panel with a character or word count and the platform limit.
- Side panel: Critic score, rubric notes, remaining issues and the number of reviews used.
- If the review limit was reached, a clear banner says the draft still has open issues.
- Header shows the version, for example "Version 3", with a version list. Approval always applies to the version on screen.
- Actions: Approve, Reject with feedback, Edit inline. "Save and approve" runs the length and section checks, and shows the reasons if they fail. Editing an already approved draft shows: "Saving creates a new version that needs approval. The current approval will no longer apply."
- If the version on screen was replaced while the creator was reading, approving shows "This draft changed. Reload to review the latest version." and nothing is approved.
- After approval: Copy button, and a Mark as posted action that asks for an optional link or video ID. Without a link, the draft shows as "Posted (no link)" with the note "Automated metrics are unavailable until you add a link" and an Add link action.

### 4.5 Briefs
- Inbox list with unread marker, week date, a Scheduled or Manual label and status.
- A Run now button creates a manual brief. A note explains that it does not replace the scheduled brief. Next scheduled time is shown.
- Brief detail shows the sections: what worked, comment themes, similar-creator moves, next week's plan, open decisions.
- Plan section has its own Approve, Reject and Edit actions. They apply to the plan only. The brief itself needs no approval.
- Empty state: shows when the next brief is scheduled.

### 4.6 Library
- Tabs: Ready to post (latest approved versions only), Posted, All drafts. Posted drafts without a link are marked "Posted (no link)".
- Filter by platform and kind. Each row has Copy and Mark as posted.
- A draft group shows the original and its repurposed versions together.

### 4.7 Insights
- Comment themes: theme, count, example comments and coverage. Examples older than the 90-day retention show as "Example no longer available". Themes from a previous channel are not shown as current.
- Analyst findings: finding, recommendation, confidence badge and sample size.
- Strategy: active entries with reasons and history.

### 4.8 Runs
- Run history list with status, depth and tokens. Statuses include Interrupted.
- Run detail: task list and routing log as a timeline. Each step shows the chosen agent, the reason, whether code or the model decided, and tokens used.
- Cancel button for active runs. An interrupted run shows "This run stopped before it finished" with Resume and Cancel actions.
- A degraded run shows a banner: "Some steps used default choices or missing tools, so this result may be incomplete", with the reasons from the routing log.

### 4.9 Settings
- Depth default, brief day and time, time zone, niche, tone preset and tone instructions (same limits as onboarding: 200 and 500 characters), and the YouTube channel (handle, ID or URL, with a Verified or Unverified badge and Change and Remove actions). Saving a schedule change shows the next brief time returned by the backend.
- **Delete my data:** a clearly separated section. The creator types `DELETE MY DATA` to enable the button. Progress shows each step. If a step fails, the screen says the deletion is partial, lists the failed steps and offers Retry. Success is shown only when every step completed. The text explains that the `.env` file is not changed.
- Credentials status:
  - **YouTube API key:** read-only status row showing "Configured" or "Not configured". No input field, no edit and no remove action. Help text: "To change the key, edit `YOUTUBE_API_KEY` in your `.env` file and restart the backend." When not configured, the row shows a warning and states what is affected, for example "Public video and comment data is unavailable."
  - **YouTube login and Instagram:** connection status (Connected, Needs reconnect, Disconnected) with Connect, Reconnect and Disconnect actions. After the OAuth redirect, the screen shows a plain message for success, denied consent or an error.
  - Secrets are never displayed.
- A health panel showing whether Ollama, the models and the scheduler are working.

---

## 5. Components

- Buttons: primary, secondary, destructive. One primary action per area.
- Badges: status, source type, confidence.
- Cards, list rows, tabs, modal for reject feedback, toast notifications, timeline, progress indicator.
- Text editor: plain multi-line text area with a counter, since all drafts are plain text.

---

## 6. UX requirements

- Mobile responsive. Test widths: 375px, 768px and 1440px.
- Loading state for every list and every run. Runs show progress, not just a spinner.
- Empty state for every list with a clear message.
- Error state for every request with a message and a retry action.
- Accessible forms: labels, visible focus, keyboard navigation, sufficient contrast.
- Confirmation before Cancel run and before disconnecting a platform login. Deleting data needs the typed phrase.
- Never show raw errors or stack traces. Use plain messages.
- Reject always requires feedback text.
- Warn on unsaved edits.

---

## 7. Tone of text

Plain, direct and professional. Show reasons, not just results. Say what the system did not do, for example "Instagram data not connected, so Reel captions use no performance context."

---

## 8. Open points

- React build tool and styling library: Vite, TypeScript and Tailwind CSS, as accepted in ADR-019.
- Final icon set and logo.

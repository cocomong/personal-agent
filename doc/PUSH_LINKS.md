# Push-to-phone links (approval links via notification) — decision & design

Status: BUILT 2026-09-06 (autonomous window). Decided with user in discussion
first: "send the link through the notification; the voice part says the link
is sent" (vs. parsing/rendering tappable URLs inside the chat transcript).

## Problem
The assistant can produce approval links (estimate baseline approval,
change-order approval). Spoken aloud they get mangled by speech-to-text, and
the chat transcript only mirrors spoken turns, so links are unreliable to
read or tap. The app already has an FCM push channel (briefing-time
reconfiguration) — reuse it to deliver links as STRUCTURED DATA.

## Chosen flow (user-approved 2026-09-06)
1. PM asks, voice or text: "send the approval link for the Oakridge change
   order to my phone" (tools: get_estimate_approval_link /
   get_change_order_approval_link — same names, new behavior).
2. Gateway mints the link exactly as before, then pushes an FCM DATA message
   to every registered device:
       { type: 'open_url', url: <signed link>, title: <label>, body: <context> }
3. Voice reply says only: "Approval link for … sent to your phone — tap the
   notification to open it." Nothing long is spoken; no URL enters the
   transcript. (No device registered → assistant falls back to speaking the
   link, i.e. old behavior — happens only when notifications were never
   granted / no device.)
4. App receives the data message in ALL app states (foreground listener,
   background isolate, terminated launch), shows a LOCAL notification
   (flutter_local_notifications, channel 'link_actions') whose payload is the
   URL, and a single tap handler (onDidReceiveNotificationResponse +
   getNotificationAppLaunchDetails) opens the URL in the system browser via
   url_launcher (external app; no WebView in v1).

## Why notification > transcript links
- URL travels as structured FCM data — never spoken or re-transcribed → exact.
- Notification persists in the shade; works when the app is backgrounded.
- Transcript stays clean prose; voice reply is short and reliable.
- One push type + one tap handler = the pattern for ALL future link-shaped
  content (receipt pages, statements, portal pages once they exist).
- WebView/portal in-app viewing remains a separate, later feature.

## Scope boundaries (this build)
- Approval-link tools only (estimate + change order). Invoice preview links
  stay email-based by design (PM reviews in email). Future tools reuse the
  same push node pattern.
- No transcript linkify, no WebView, no assistant-text-reply transcript fix
  (the typed-chat render gap is tracked separately — links pushed to the
  phone make it low priority for link delivery).
- Not scoped by company yet: pushes go to all registered device tokens
  (single-company stage); Step 3 will scope device_tokens.

## Server-side details (voice-gateway.json)
- get_device_tokens query now guarantees one row (UNION ALL SELECT NULL WHERE
  NOT EXISTS) so chains always reach Format; briefing path unaffected.
- New Exec: approval_devices (same guaranteed-row query, dedicated node so
  chains never fan out across actions).
- Both approval-link lookups rewritten to LEFT JOIN guaranteed-row shape so
  "not found" reaches Format instead of silently ending the run.
- Chain: lookup → approval_devices → IF 'Link Kind?' (action) →
  Push Estimate Link / Push Change Order Link (code nodes cloned from the
  briefing FCM sender: service-account JWT → FCM v1) → Format.
- Push payload: type open_url + url + title + body (title/body name the
  project/CO for the notification line).
- Format replies: pushed>0 → "…sent to your phone — tap the notification to
  open it"; no devices → speaks the full link (old behavior, rare).

## App-side details (mobile-flutter)
- pubspec: + url_launcher.
- NotificationService: init becomes idempotent and accepts an onTap(payload)
  callback; registers onDidReceiveNotificationResponse and checks
  getNotificationAppLaunchDetails after initialize (terminated-launch tap);
  new showLink(title, body, url) posts an immediate notification on channel
  'link_actions' with payload = url; _notificationId range: briefing stays
  1001, links get 2000-series ids.
- FcmService._handleData + firebaseMessagingBackgroundHandler: new branch
  type == 'open_url' → NotificationService.showLink(...) (background isolate
  inits the plugin like the briefing handler does).
- main.dart bootstrap: pass onTap → url_launcher launchUrl(mode:
  externalApplication).
- No changes to agent_screen/vapi session for this build.

## QA performed
- App: flutter analyze clean; release APK builds (112MB).
- Server: JSON structural asserts, push-code control-flow harness (found /
  not-found / no-devices cases, correct URLs + titles), deployed (import +
  ACTIVATE + restart — activation is mandatory after every import), gateway
  HTTP 200.
- Live (real devices): estimate-approval link and change-order link both
  pushed successfully — voice replies "…sent to your phone — tap the
  notification to open it." CO not-found path replies "Change order not
  found." Two of three registered device tokens were STALE (FCM
  NotRegistered — app uninstalled/reinstalled at some point); the push code
  now skips stale tokens instead of aborting (first version aborted the whole
  send on the first NotRegistered — found + fixed during QA). A stale-token
  cleanup on device re-registration is a hygiene follow-up.
- Also fixed during QA: change_orders.change_order_number is an INTEGER
  column; the CO lookup previously compared it to the raw tool arg (e.g.
  'CO-002') and threw a cast error, silently ending the run. Lookup now
  accepts 'CO-002' or '2'. (Pre-existing latent bug, surfaced by this build.)
- Not yet testable here: notification tap on a physical device (needs the
  user's phone + installed APK). Manual QA list below.

## Manual QA (user, on phone)
1. Install the new APK, sign in, grant notifications.
2. Voice: "send the approval link for the Oakridge estimate to my phone" →
   assistant confirms sent; a notification appears; tap → browser opens the
   estimate approval page.
3. Repeat for a change order; tap works from app-open, backgrounded, and
   terminated states.
4. Open the notification from the shade after some minutes (still tappable).
5. Kill the app entirely, receive, tap → opens.

# Writing Tools Memory Leak Investigation

**Investigation date:** August 13, 2026  
**Application version inspected:** 9.30.6  
**Repository:** WritingTools Windows application

## Summary

Writing Tools is stable while idle on the computer that was inspected. However,
the investigation confirmed two activity-driven object-retention leaks and found
one additional resource-cleanup weakness.

Repeatedly opening and closing rewrite/response windows is the largest confirmed
risk. Repeatedly opening popup menus also retains menu objects. Over a long-running
session, these issues can cause Writing Tools to consume progressively more memory
and Windows resources.

The currently inspected Writing Tools process was not large enough by itself to
explain a computer using all available RAM. If memory remains full after every
Writing Tools process is terminated, another application, a Windows file cache, or
a driver/kernel allocation is likely contributing to the problem.

## Current Process Measurements

The main Writing Tools process had been running since August 4, 2026.

| Measurement | Observed value |
| --- | ---: |
| Working set (resident RAM) | 66.2 MB |
| Private committed memory | 201.2 MB |
| Process handles | 2,215 |
| GDI objects | 284 |
| USER objects | 85 |
| Threads | 4 |

A 20-second idle sample showed no growth:

- Working set remained at 66.2 MB.
- Private memory remained at 201.2 MB.
- Handle count remained at 2,215.
- Thread count remained at 4.

This indicates that the application is not continuously leaking resources while
idle. The confirmed leaks are triggered by application use.

## Confirmed Findings

### 1. Closed Response Windows Remain Alive

**Severity:** High  
**Status:** Confirmed with a controlled test

Each `ResponseWindow` connects its `handle_followup_response` method to the
long-lived application's `followup_response_signal`:

- `Windows_and_Linux/ui/ResponseWindow.py`, around line 325

The window's `closeEvent` clears `chat_history`, but it does not disconnect the
application signal, schedule the window for deletion, or enable Qt's
delete-on-close behavior:

- `Windows_and_Linux/ui/ResponseWindow.py`, around line 800

Because the application remains alive in the system tray, its signal keeps closed
response windows reachable. The retained window also keeps its rendered widgets,
selected source text, and displayed responses.

#### Test Evidence

A controlled offscreen Qt test created and normally closed 50 response windows.
After processing events and running garbage collection:

- 50 of 50 response windows remained alive.
- All 50 remained registered as top-level Qt widgets.

When the same windows were explicitly scheduled with `deleteLater()`, none remained
alive.

#### Recommended Fix

- Disconnect `followup_response_signal` in `ResponseWindow.closeEvent`.
- Stop the thinking timer during close.
- Clear references to rendered content and selected text where appropriate.
- Set `Qt.WidgetAttribute.WA_DeleteOnClose`, or call `deleteLater()` safely after
  closing.
- Add a regression test that creates and closes multiple response windows and
  verifies they are collected.

### 2. Popup Menus Accumulate Under the Long-Lived Popup

**Severity:** Medium  
**Status:** Confirmed with a controlled test

The popup creates a new `QMenu` with the persistent popup as its parent whenever
the user opens either menu:

- Edit/Manage menu: `Windows_and_Linux/ui/CustomPopupWindow.py`, around line 1384
- Pinned Text picker: `Windows_and_Linux/ui/CustomPopupWindow.py`, around line 1397

Closing a menu does not destroy it when the long-lived popup still owns it. Each
menu also owns its actions and submenus.

#### Test Evidence

A controlled test created 500 parent-owned menus and released all local Python
references. The parent still retained all 500 menu objects.

#### Recommended Fix

- Create each temporary menu without a persistent parent and explicitly delete it
  after `exec()` returns, or call `menu.deleteLater()` in a `finally` block.
- Add an object-count regression test that opens and closes these menus repeatedly.

## Additional Risk

### AI Provider Clients Are Replaced Without Explicit Cleanup

**Severity:** Medium  
**Status:** Plausible risk; not yet proven as an indefinite leak

`AIProvider.load_config()` calls `after_load()` to create a new provider client,
but it does not call `before_load()` first. OpenAI-compatible and GitHub providers
can therefore replace an existing client without explicitly closing its HTTP
connection pool.

Relevant locations include:

- `Windows_and_Linux/aiprovider.py`, around line 300
- OpenAI client construction around line 652
- Azure OpenAI client construction around line 736
- GitHub `httpx.Client` construction around lines 817 and 846

Python garbage collection may eventually release these clients, but relying on it
can delay the release of sockets, worker resources, and native handles.

#### Recommended Fix

- Call `before_load()` before applying new configuration.
- Implement provider-specific cleanup that calls `client.close()` where available.
- Explicitly close temporary validation clients in a `finally` block or context
  manager.

## Areas That Do Not Currently Show a RAM Leak

### Azure Speech In-Memory Cache

Azure Speech stores sentence audio and synthesis metadata only for the active Read
Aloud session. Its `finally` block clears navigation state and releases the local
cache when the session ends. This does not appear to be an ongoing memory leak.

### Azure Speech Temporary Files

The inspected computer contained 39 Azure Speech WAV files totaling approximately
10.75 MB. These consume disk space, not RAM. Some canceled or interrupted speech
sessions may leave files behind.

Recommended improvement: remove stale speech files at startup and periodically,
while avoiding files owned by an active session.

### Read Aloud Metrics

The JSONL metrics file is bounded to 500 records after it reaches its compaction
threshold. The CSV metrics file has no retention limit and will grow over time,
but it was only about 98 KB during this investigation. This is a disk-growth issue,
not a memory leak.

## How to Confirm the Problem on the Affected PC

1. Open Task Manager and select the **Details** tab.
2. Add or inspect the **Memory (active private working set)** and **Commit size**
   columns.
3. Record the Writing Tools values immediately after startup.
4. Use rewrite/response windows and popup menus repeatedly for several minutes.
5. Close every Writing Tools window while leaving the tray application running.
6. Check whether the Writing Tools process memory and handle count remain elevated.
7. Fully exit every Writing Tools process from the tray or Task Manager.

If total system memory drops after Writing Tools exits, Writing Tools contributed
to the usage. If total memory stays full after all Writing Tools processes are
gone, inspect other processes, Windows standby/file cache, and driver/kernel pools.

## Recommended Implementation Order

1. Fix response-window signal disconnection and deletion.
2. Delete temporary popup menus after use.
3. Explicitly close provider HTTP clients before replacement and after validation.
4. Add repeat-open/close memory and object-count regression tests.
5. Add stale Azure Speech file cleanup and CSV retention as maintenance work.

## Investigation Scope

This investigation used source review, live process measurements, Windows resource
counts, controlled Qt lifecycle tests, local application logs, and local data-file
inspection. No application code was changed as part of the investigation itself.

# ECHO MOVE SOC Dashboard (Approach A)

Approved: wall + side rail, no tabs, drop Citations, add System metrics.

## Layout
- Header (sticky): brand, live status pills, source controls (Camera + device picker + flip front/rear), mute, tools toggle
- Workspace (page scroll):
  - Main ops: video wall (left) | 3D + Detect/Session (right); Worker 3D hidden on mobile; no MATLAB IQA card
  - Deck panels (vertical stack):
    - Event stats (filters + KPI cards)
    - Event hourly chart (0–23h)
    - Event gallery (snapshots, ack / false-alarm, clips)
    - System metrics
    - IQA Live (left) + Cảnh báo IQA (right) one row, above Thống kê sự kiện
    - Cameras (server streams + feature guide when offline/empty) — bottom
- Tools drawer (collapsed): MATLAB, Bench, Report, Test, Log, WS URL
- Each `.panel` header has ⛶ zoom: expands that section fullscreen overlay; Escape / ✕ to exit

## Copy rules
- Cameras / Events offline states explain the feature — no GitHub Pages / make run / localhost setup notes in-panel

## Public URL
- Production demo: `https://test.antokr.com` (nginx TLS → Docker `:18080`)

## Out of scope
- Backend API changes, alert logic, IQA thresholds, deploy commands

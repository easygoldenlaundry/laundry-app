# Admin Command Room Dashboard Specification

## Objective
Build a single Admin Command Room page that gives managers instant, actionable, real-time control over the service to reliably meet SLAs.

## UI Layout & Behavior

### Row 1: Executive KPI Cards
- **% Orders ≤ 2.5h Turnaround (last 24h)**
- **% Pickups ≤ 15m (last 24h)**
- **% Deliveries ≤ 15m (last 24h)**
- **Image Coverage % (last 24h)**
- **Active In-flight Orders**
- **Claims Today**

### Row 2: Real-time Orders Table + Alerts Feed
**Table Columns:** Order ID, Customer, Status, Turnaround Time, SLA Countdown, Driver, Items Imaged, Actions.
**Sorting:** Breached SLAs first, then by urgency.
**Alerts:** Chronological feed of SLA warnings, machine alerts, driver issues, and new claims.

### Row 3: Station Mini-Panels
Cards for Imaging, Washing, Drying, Folding, QA showing queue length, processing times, throughput, and machine utilization.

### Row 4: Drilldowns
Future placeholder for detailed Driver metrics, Image Coverage, Claims, and a simple Capacity Forecast.

## Interactivity
- Real-time updates via Socket.IO on the `hub:1` room.
- Keyboard shortcuts for navigation (J/K) and actions (Enter, R, E).
- Action buttons call existing API endpoints to ensure business logic is respected.

## Thresholds & Colors
- **Turnaround:** Target ≤ 150 min. Green ≥90%, Amber 75–89%, Red <75%.
- **Pickup/Delivery:** Target ≤ 15 min. Green ≥92%, Amber 80–91%, Red <80%.
- **Image Coverage:** Target ≥ 98%. Green ≥98%, Amber 95–97%, Red <95%.
- **Station Utilization:** Amber >85%, Red >95%.
- **SLA State:** Approaching (<30 min left) = Amber, Breached = Red.
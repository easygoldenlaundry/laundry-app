// app/static/js/command_room.js
document.addEventListener('DOMContentLoaded', () => {
    // --- CONFIG & STATE ---
    const HUB_ID = 1;
    let ordersMap = new Map(); // For real-time in-flight orders
    let allOrdersData = []; // For historical table, fetched once or on demand
    let currentAggregatedTimeframe = '7days';
    let countdownInterval;

    // --- DOM SELECTORS ---
    const selectors = {
        kpiTurnaround: document.getElementById('kpi-turnaround'),
        kpiPickup: document.getElementById('kpi-pickup'),
        kpiDelivery: document.getElementById('kpi-delivery'),
        kpiImaging: document.getElementById('kpi-imaging'),
        kpiActiveOrders: document.getElementById('kpi-active-orders'),
        kpiClaims: document.getElementById('kpi-claims'),
        ordersTableBody: document.getElementById('orders-table-body'),
        alertsList: document.getElementById('alerts-list'),
        stations: {
            imaging: document.getElementById('station-imaging'),
            pretreat: document.getElementById('station-pretreat'),
            washing: document.getElementById('station-washing'),
            drying: document.getElementById('station-drying'),
            folding: document.getElementById('station-folding'),
            qa: document.getElementById('station-qa'), // Adjusted to 'qa'
        },
        allOrdersTableBody: document.getElementById('all-orders-table-body'),
        allOrdersSearch: document.getElementById('all-orders-search'),
        allOrdersTableHeaders: document.querySelectorAll('#all-orders-table th[data-sort-by]'),
        aggregatedStatsTableBody: document.getElementById('aggregated-stats-table-body'),
        timeframeButtons: document.querySelectorAll('.table-controls button[data-timeframe]')
    };

    // --- UTILITY FUNCTIONS ---
    const formatTime = (totalSeconds, includeSeconds = true) => {
        if (isNaN(totalSeconds) || totalSeconds < 0) return '00:00:00';
        const hours = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
        const seconds = Math.floor(totalSeconds % 60).toString().padStart(2, '0');
        return includeSeconds ? `${hours}:${minutes}:${seconds}` : `${hours}:${minutes}`;
    };
    
    const formatMinutes = (minutes) => {
        if (isNaN(minutes) || minutes < 0) return 'N/A';
        return `${minutes.toFixed(1)}m`;
    }

    const formatDateTime = (isoString) => {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleString(); // Uses user's locale
    };

    const getStatusColorClass = (value, thresholds) => {
        if (value >= thresholds.green) return 'status-green';
        if (value >= thresholds.amber) return 'status-amber';
        return 'status-red';
    };

    // --- RENDERING FUNCTIONS ---
    function renderKpis(data) {
        // Turnaround
        const turnaroundValue = selectors.kpiTurnaround.querySelector('.kpi-value');
        const turnaroundSubtext = selectors.kpiTurnaround.querySelector('.kpi-subtext');
        turnaroundValue.textContent = `${data.turnaround.percentage_on_time.toFixed(1)}%`;
        turnaroundValue.className = `kpi-value ${getStatusColorClass(data.turnaround.percentage_on_time, { green: 90, amber: 75 })}`;
        turnaroundSubtext.innerHTML = `(${data.turnaround.total_completed} orders)<br>P50: ${data.turnaround.p50_minutes}m, P90: ${data.turnaround.p90_minutes}m`;
        
        // Pickup
        const pickupValue = selectors.kpiPickup.querySelector('.kpi-value');
        const pickupSubtext = selectors.kpiPickup.querySelector('.kpi-subtext');
        pickupValue.textContent = `${data.pickup.percentage_on_time.toFixed(1)}%`;
        pickupValue.className = `kpi-value ${getStatusColorClass(data.pickup.percentage_on_time, { green: 92, amber: 80 })}`;
        pickupSubtext.innerHTML = `(${data.pickup.total_pickups} pickups)<br>Median: ${data.pickup.median_pickup_time}m`;

        // Delivery
        const deliveryValue = selectors.kpiDelivery.querySelector('.kpi-value');
        const deliverySubtext = selectors.kpiDelivery.querySelector('.kpi-subtext');
        deliveryValue.textContent = `${data.delivery.percentage_on_time.toFixed(1)}%`;
        deliveryValue.className = `kpi-value ${getStatusColorClass(data.delivery.percentage_on_time, { green: 92, amber: 80 })}`;
        deliverySubtext.innerHTML = `(${data.delivery.total_deliveries} deliveries)<br>Avg: ${data.delivery.avg_delivery_time}m`;

        // Imaging
        const imagingValue = selectors.kpiImaging.querySelector('.kpi-value');
        const imagingSubtext = selectors.kpiImaging.querySelector('.kpi-subtext');
        imagingValue.textContent = `${data.imaging.coverage_percent.toFixed(1)}%`;
        imagingValue.className = `kpi-value ${getStatusColorClass(data.imaging.coverage_percent, { green: 98, amber: 95 })}`;
        imagingSubtext.innerHTML = `${data.imaging.imaged_items}/${data.imaging.total_items} items imaged`;

        // Active Orders & Claims
        selectors.kpiActiveOrders.querySelector('.kpi-value').textContent = data.active_orders_count;
        selectors.kpiClaims.querySelector('.kpi-value').textContent = data.claims.open_count; 
        selectors.kpiClaims.querySelector('.kpi-subtext').innerHTML = `Total claims today: ${data.claims.count_today}`;
    }

    function renderStations(data) {
        for (const [key, stationEl] of Object.entries(selectors.stations)) {
            const metrics = data[key];
            if (metrics) {
                stationEl.querySelector('[data-metric="queue_length"]').textContent = metrics.queue_length;
                if (metrics.utilization_pct !== undefined) {
                    stationEl.querySelector('[data-metric="utilization_pct"]').textContent = metrics.utilization_pct.toFixed(1);
                }
                stationEl.querySelector('[data-metric="avg_time"]').textContent = metrics.avg_time.toFixed(1);
                stationEl.querySelector('[data-metric="p95_time"]').textContent = metrics.p95_time.toFixed(1);
                stationEl.querySelector('[data-metric="throughput_h"]').textContent = metrics.throughput_h.toFixed(1);

                if (metrics.bottleneck) {
                    stationEl.classList.add('bottleneck');
                } else {
                    stationEl.classList.remove('bottleneck');
                }
            } else {
                stationEl.querySelector('[data-metric="queue_length"]').textContent = 'N/A';
                if (stationEl.querySelector('[data-metric="utilization_pct"]')) stationEl.querySelector('[data-metric="utilization_pct"]').textContent = 'N/A';
                stationEl.querySelector('[data-metric="avg_time"]').textContent = 'N/A';
                stationEl.querySelector('[data-metric="p95_time"]').textContent = 'N/A';
                if (stationEl.querySelector('[data-metric="throughput_h"]')) stationEl.querySelector('[data-metric="throughput_h"]').textContent = 'N/A';
                stationEl.classList.remove('bottleneck');
            }
        }
    }

    function renderOrderRow(order) {
        const turnaroundSeconds = order.picked_up_at ? (new Date() - new Date(order.picked_up_at)) / 1000 : 0;
        
        return `
            <td><a href="/track/${order.tracking_token}" target="_blank">${order.id}</a></td>
            <td>${order.customer_name}</td>
            <td><strong>${order.status}</strong></td>
            <td class="turnaround-timer">${formatTime(turnaroundSeconds)}</td>
            <td class="sla-countdown" data-sla="${order.sla_deadline || ''}">-</td>
            <td>${order.assigned_driver_id || 'N/A'}</td>
            <td>${order.imaged_items_count}/${order.total_items}</td>
            <td><button data-action="details" data-order-id="${order.id}">...</button></td>
        `;
    }

    function updateOrInsertOrderRow(order) {
        let row = document.getElementById(`order-row-${order.id}`);
        if (!row) {
            row = document.createElement('tr');
            row.id = `order-row-${order.id}`;
            selectors.ordersTableBody.prepend(row); // Prepend new orders
        }
        row.innerHTML = renderOrderRow(order);
        ordersMap.set(order.id, order);
        updateSlaClass(row, order.sla_deadline);
    }

    function updateSlaClass(row, sla) {
        if (!sla) {
            row.className = '';
            return;
        }
        const diffMinutes = (new Date(sla) - new Date()) / 1000 / 60;
        if (diffMinutes < 0) {
            row.className = 'sla-breached';
        } else if (diffMinutes < 30) {
            row.className = 'sla-approaching';
        } else {
            row.className = '';
        }
    }
    
    function updateAllTimers() {
        document.querySelectorAll('#orders-table-body tr').forEach(row => {
            const orderId = parseInt(row.id.replace('order-row-', ''), 10);
            const order = ordersMap.get(orderId);
            if (!order) return;

            // Update turnaround timer
            if (order.picked_up_at) {
                const turnaroundEl = row.querySelector('.turnaround-timer');
                const turnaroundSeconds = (new Date() - new Date(order.picked_up_at)) / 1000;
                if(turnaroundEl) turnaroundEl.textContent = formatTime(turnaroundSeconds);
            }

            // Update SLA countdown
            const slaEl = row.querySelector('.sla-countdown');
            if (slaEl && order.sla_deadline) {
                const diffSeconds = (new Date(order.sla_deadline) - new Date()) / 1000;
                slaEl.textContent = (diffSeconds < 0 ? '-' : '') + formatTime(Math.abs(diffSeconds));
                updateSlaClass(row, order.sla_deadline);
            }
        });
    }

    // --- [NEW] Historical Orders Table ---
    const calculateOrderStageDuration = (order, startEventName, endEventName) => {
        if (!order.events || order.events.length === 0) return 'N/A';

        let startTimestamp = null;
        let endTimestamp = null;
        
        // Handle direct timestamp fields for order-level stages
        if (startEventName === 'Imaging' && order.imaging_started_at && order.processing_started_at) {
            startTimestamp = new Date(order.imaging_started_at);
            endTimestamp = new Date(order.processing_started_at);
        } else if (startEventName === 'QA' && order.qa_started_at) {
             startTimestamp = new Date(order.qa_started_at);
             // Find end: ReadyForDelivery or Processing (if QA failed)
             const readyEvent = order.events.find(e => e.to_status === 'ReadyForDelivery' && new Date(e.timestamp) > startTimestamp);
             const failEvent = order.events.find(e => e.to_status.includes('Processing') && e.meta && e.meta.includes('qa_failed_by') && new Date(e.timestamp) > startTimestamp);
             endTimestamp = (readyEvent || failEvent) ? new Date((readyEvent || failEvent).timestamp) : null;
        } else {
            // Generic event-based parsing for basket-level stages
            const starts = order.events.filter(e => e.to_status.includes(`Started-${startEventName.toLowerCase()}`));
            const ends = order.events.filter(e => e.to_status.includes(`Finished-${startEventName.toLowerCase()}`)); // Assuming a clear finished event

            if (starts.length === 0 || ends.length === 0) return 'N/A';

            // For simplicity, take the time between the earliest start and latest end for *any* basket in that stage
            // A more precise approach would match individual basket start/end pairs, then average or sum.
            startTimestamp = new Date(starts.sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp))[0].timestamp);
            endTimestamp = new Date(ends.sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp))[0].timestamp);
        }

        if (startTimestamp && endTimestamp) {
            const durationMinutes = (endTimestamp - startTimestamp) / (1000 * 60);
            return durationMinutes.toFixed(1);
        }
        return 'N/A';
    };


    function renderAllOrdersTable(orders, sortBy = 'created_at', sortDir = 'desc', searchTerm = '') {
        selectors.allOrdersTableBody.innerHTML = '';
        
        let filteredOrders = orders.filter(order => {
            const searchLower = searchTerm.toLowerCase();
            return (order.id && String(order.id).includes(searchLower)) ||
                   (order.customer_name && order.customer_name.toLowerCase().includes(searchLower)) ||
                   (order.status && order.status.toLowerCase().includes(searchLower));
        });

        // Pre-calculate derived values for sorting
        filteredOrders.forEach(order => {
            order.stain_count = order.events.filter(e => e.to_status.includes('Stain Flagged')).length;
            order.qa_outcome = 'Pending';
            const qaPass = order.events.find(e => e.to_status === 'ReadyForDelivery' && e.from_status === 'QA');
            const qaFail = order.events.find(e => e.to_status === 'Processing' && e.from_status === 'QA' && e.meta && e.meta.includes('qa_failed_by'));
            if (qaPass) order.qa_outcome = 'Passed';
            else if (qaFail) order.qa_outcome = 'Failed';

            order.imaging_duration = calculateOrderStageDuration(order, 'Imaging');
            order.pretreat_duration = calculateOrderStageDuration(order, 'Pretreat');
            order.washing_duration = calculateOrderStageDuration(order, 'washing');
            order.drying_duration = calculateOrderStageDuration(order, 'drying');
            order.folding_duration = calculateOrderStageDuration(order, 'folding');
            order.qa_duration = calculateOrderStageDuration(order, 'QA');
        });


        filteredOrders.sort((a, b) => {
            let valA = a[sortBy];
            let valB = b[sortBy];

            // Handle numeric sorting for durations and counts
            if (['id', 'total_items', 'basket_count', 'stain_count', 'imaging_duration', 'pretreat_duration', 'washing_duration', 'drying_duration', 'folding_duration', 'qa_duration'].includes(sortBy)) {
                valA = parseFloat(valA) || 0;
                valB = parseFloat(valB) || 0;
            } else if (sortBy === 'created_at' || sortBy === 'delivered_at') {
                valA = valA ? new Date(valA) : new Date(0); // Treat null dates as very old
                valB = valB ? new Date(valB) : new Date(0);
            }

            if (valA < valB) return sortDir === 'asc' ? -1 : 1;
            if (valA > valB) return sortDir === 'asc' ? 1 : -1;
            return 0;
        });

        if (filteredOrders.length === 0) {
            selectors.allOrdersTableBody.innerHTML = `<tr><td colspan="15" style="text-align:center;">No matching orders found.</td></tr>`;
            return;
        }

        filteredOrders.forEach(order => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><a href="/track/${order.tracking_token}" target="_blank">${order.id}</a></td>
                <td>${order.customer_name}</td>
                <td>${order.status}</td>
                <td>${formatDateTime(order.created_at)}</td>
                <td>${formatDateTime(order.delivered_at)}</td>
                <td>${order.total_items}</td>
                <td>${order.basket_count}</td>
                <td>${order.stain_count}</td>
                <td>${order.qa_outcome}</td>
                <td>${order.imaging_duration}</td>
                <td>${order.pretreat_duration}</td>
                <td>${order.washing_duration}</td>
                <td>${order.drying_duration}</td>
                <td>${order.folding_duration}</td>
                <td>${order.qa_duration}</td>
            `;
            selectors.allOrdersTableBody.appendChild(row);
        });
    }

    let currentSort = { by: 'created_at', dir: 'desc' };

    selectors.allOrdersTableHeaders.forEach(header => {
        header.addEventListener('click', () => {
            const sortBy = header.dataset.sortBy;
            let sortDir = 'asc';
            if (currentSort.by === sortBy && currentSort.dir === 'asc') {
                sortDir = 'desc';
            }
            
            selectors.allOrdersTableHeaders.forEach(h => {
                h.classList.remove('asc', 'desc');
            });
            header.classList.add(sortDir);

            currentSort = { by: sortBy, dir: sortDir };
            renderAllOrdersTable(allOrdersData, currentSort.by, currentSort.dir, selectors.allOrdersSearch.value);
        });
    });

    selectors.allOrdersSearch.addEventListener('input', () => {
        renderAllOrdersTable(allOrdersData, currentSort.by, currentSort.dir, selectors.allOrdersSearch.value);
    });

    // --- [NEW] Aggregated Statistics Table ---
    function renderAggregatedStatsTable(data) {
        selectors.aggregatedStatsTableBody.innerHTML = '';
        if (!data || Object.keys(data).length === 0) {
            selectors.aggregatedStatsTableBody.innerHTML = `<tr><td colspan="2" style="text-align:center;">No data for this timeframe.</td></tr>`;
            return;
        }

        const statsRows = [
            { metric: `Timeframe`, value: data.timeframe },
            { metric: `Total Orders Created`, value: data.total_orders_created },
            { metric: `Total Orders Completed`, value: data.total_orders_completed },
            { metric: `Avg Turnaround Time`, value: `${data.avg_turnaround_minutes.toFixed(1)} min` },
            { metric: `Avg Pickup Time`, value: `${data.avg_pickup_minutes.toFixed(1)} min` },
            { metric: `Avg Items per Order`, value: data.avg_items_per_order.toFixed(1) },
            { metric: `Avg Imaging Time`, value: `${data.avg_imaging_time.toFixed(1)} min` },
            { metric: `Avg Pretreat Time`, value: `${data.avg_pretreat_time.toFixed(1)} min` },
            { metric: `Avg Washing Time`, value: `${data.avg_washing_time.toFixed(1)} min` },
            { metric: `Avg Drying Time`, value: `${data.avg_drying_time.toFixed(1)} min` },
            { metric: `Avg Folding Time`, value: `${data.avg_folding_time.toFixed(1)} min` },
            { metric: `Avg QA Time`, value: `${data.avg_qa_time.toFixed(1)} min` },
            { metric: `Total Claims`, value: data.total_claims },
            { metric: `Total Compensation`, value: `R ${data.total_compensation.toFixed(2)}` },
            { metric: `% Orders with Stains`, value: `${data.percent_with_stains.toFixed(1)}%` },
            { metric: `% QA Passed`, value: `${data.percent_qa_passed.toFixed(1)}%` },
            { metric: `% QA Failed`, value: `${data.percent_qa_failed.toFixed(1)}%` },
        ];

        statsRows.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${row.metric}</td><td>${row.value}</td>`;
            selectors.aggregatedStatsTableBody.appendChild(tr);
        });
    }

    selectors.timeframeButtons.forEach(button => {
        button.addEventListener('click', async () => {
            selectors.timeframeButtons.forEach(btn => btn.classList.remove('selected'));
            button.classList.add('selected');
            currentAggregatedTimeframe = button.dataset.timeframe;
            await fetchAggregatedStats();
        });
    });

    // --- API & SOCKETS ---
    async function fetchKpisAndActiveOrders() {
        try {
            const [kpis, orders, stations] = await Promise.all([
                fetch('/admin/api/dashboard/kpis').then(res => res.json()),
                fetch('/admin/api/dashboard/orders').then(res => res.json()),
                fetch('/admin/api/dashboard/station-metrics').then(res => res.json())
            ]);
            
            renderKpis(kpis);
            selectors.ordersTableBody.innerHTML = ''; // Clear existing before re-rendering active
            orders.forEach(updateOrInsertOrderRow);
            renderStations(stations);
            
            clearInterval(countdownInterval);
            countdownInterval = setInterval(updateAllTimers, 1000);
            
        } catch (error) {
            console.error("Failed to fetch real-time dashboard data:", error);
        }
    }

    async function fetchAllOrders() {
        try {
            const response = await fetch('/admin/api/dashboard/all-orders');
            allOrdersData = await response.json();
            renderAllOrdersTable(allOrdersData, currentSort.by, currentSort.dir, selectors.allOrdersSearch.value);
        } catch (error) {
            console.error("Failed to fetch all orders:", error);
            selectors.allOrdersTableBody.innerHTML = `<tr><td colspan="15" style="color:red; text-align:center;">Error loading historical orders.</td></tr>`;
        }
    }

    async function fetchAggregatedStats() {
        try {
            const response = await fetch(`/admin/api/dashboard/aggregated-stats?timeframe=${currentAggregatedTimeframe}`);
            const stats = await response.json();
            renderAggregatedStatsTable(stats);
        } catch (error) {
            console.error("Failed to fetch aggregated stats:", error);
            selectors.aggregatedStatsTableBody.innerHTML = `<tr><td colspan="2" style="color:red; text-align:center;">Error loading aggregated statistics.</td></tr>`;
        }
    }

    const socket = io({ transports: ['websocket'] });
    socket.on('connect', () => {
        socket.emit('join', { room: `hub:${HUB_ID}` });
    });
    socket.on('order.updated', (order) => {
        // Update active orders table (real-time)
        updateOrInsertOrderRow(order);
        // Re-fetch historical and aggregated data to reflect changes
        // This can be optimized later if needed to only refresh relevant parts
        fetchAllOrders();
        fetchAggregatedStats();
        fetchKpisAndActiveOrders(); // Also refresh KPIs
    });

    // --- INITIALIZATION ---
    fetchKpisAndActiveOrders(); // Fetch KPIs and active orders initially
    fetchAllOrders(); // Fetch all orders initially
    fetchAggregatedStats(); // Fetch aggregated stats initially
    
    // Set periodic refresh for KPIs and active orders (as socket updates might not cover all KPI changes)
    setInterval(fetchKpisAndActiveOrders, 15000); // More frequent for KPIs
    // Periodic refresh for historical data - less frequent
    setInterval(fetchAllOrders, 60000); 
    setInterval(fetchAggregatedStats, 60000);
});

    const SELLER_STORE_NAME = null;
    let SELLER_TODAY_STR = null;
    let sellerSyncToken = null;
    let sellerRows = Array.from(document.querySelectorAll('.seller-order-row'));
    const sellerOrdersTbody = document.getElementById('sellerOrdersTableBody');
    const sellerOrderDetailsModal = document.getElementById('sellerOrderDetailsModal');
    const sellerPaymentProofModal = document.getElementById('sellerPaymentProofModal');
    const sellerPaginationInfo = document.getElementById('sellerOrdersPaginationInfo');
    const sellerPaginationWrap = document.getElementById('sellerOrdersPagination');
    const sellerOrdersPrevBtn = document.getElementById('sellerOrdersPrevBtn');
    const sellerOrdersNextBtn = document.getElementById('sellerOrdersNextBtn');
    const sellerPanelSub = document.getElementById('sellerOrdersPanelSub');
    const sellerStatCards = Array.from(document.querySelectorAll('.kpi-card[data-filter-type]'));
    let sellerNoRecordsRow = document.getElementById('sellerNoRecordsRow');
    let activePaymentOrderId = null;
    let sellerCurrentPage = 1;
    const sellerRowsPerPage = 10;
    let sellerCardFilter = null;
    let sellerLiveBusy = false;
    let selectedOrderIds = new Set();

    function openModal(modal) {
        if (!modal) return;
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal(modal) {
        if (!modal) return;
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
    }

    function getSellerToken() {
        return localStorage.getItem('jwt_token') || localStorage.getItem('token') || '';
    }

    async function sellerFetch(url, options = {}) {
        return fetch(url, options);
    }

    function showSellerAlert(type, message) {
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
        const mainContent = document.querySelector('.main-content') || document.querySelector('.main-area') || document.body;
        if (mainContent.firstChild) {
            mainContent.insertBefore(alert, mainContent.firstChild);
        } else {
            mainContent.appendChild(alert);
        }
        setTimeout(() => alert.remove(), 5000);
    }

    function titleCaseStatus(value) {
        return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    }

    function formatPaymentCombined(method, status) {
        const methodKey = String(method || '').toLowerCase();
        const statusKey = String(status || '').toLowerCase();
        const methodLabel = methodKey === 'gcash' ? 'GCash'
            : methodKey === 'cod' ? 'COD'
            : titleCaseStatus(method);
        const statusLabel = {
            verified: 'Verified',
            pending_verification: 'Pending',
            pending: 'Pending',
            cod_pending: 'Pending',
            cod_approved: 'Approved',
        }[statusKey] || titleCaseStatus(status);
        return [statusLabel, methodLabel].filter(Boolean).join(' ').trim() || '—';
    }

    function formatAmount(value) {
        return Number(value || 0).toLocaleString('en-PH', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    function escapeAttr(s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function escapeHtml(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function lineItemThumb(url) {
        const u = (url && String(url).trim()) ? String(url).trim() : '';
        if (!u) {
            return '<span class="sdm-line-thumb-ph" aria-hidden="true"><i class="ri-flower-line"></i></span>';
        }
        return `<img class="sdm-line-thumb" src="${escapeAttr(u)}" alt="" width="24" height="24" loading="lazy" decoding="async" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex';"><span class="sdm-line-thumb-ph" style="display:none;" aria-hidden="true"><i class="ri-flower-line"></i></span>`;
    }

    function parseApiDateTime(value) {
        if (!value) return null;
        const raw = String(value).trim();
        if (!raw) return null;
        if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return new Date(`${raw}T00:00:00Z`);
        if (/[zZ]|[+\-]\d{2}:\d{2}$/.test(raw)) return new Date(raw);
        return new Date(`${raw}Z`);
    }

    function formatDateTime(value) {
        if (!value) return 'N/A';
        try {
            const parsed = parseApiDateTime(value);
            if (!parsed || Number.isNaN(parsed.getTime())) return value;
            return new Intl.DateTimeFormat('en-PH', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true,
                timeZone: 'Asia/Manila'
            }).format(parsed);
        } catch (error) {
            return value;
        }
    }

    function formatDate(value) {
        if (!value) return 'N/A';
        try {
            const parsed = parseApiDateTime(value);
            if (!parsed || Number.isNaN(parsed.getTime())) return value;
            return new Intl.DateTimeFormat('en-PH', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                weekday: 'short',
                timeZone: 'Asia/Manila'
            }).format(parsed);
        } catch (error) {
            return value;
        }
    }

    function formatDeliveryTimeSlot(value) {
        if (!value) return 'Not specified';
        const raw = String(value).trim();
        const m = raw.match(/^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/);
        if (!m) return raw;
        const to12h = (h, min) => {
            const hour = Number(h);
            const suffix = hour >= 12 ? 'PM' : 'AM';
            const twelveHour = (hour % 12) || 12;
            return `${twelveHour}:${String(min).padStart(2, '0')} ${suffix}`;
        };
        return `${to12h(m[1], m[2])} - ${to12h(m[3], m[4])}`;
    }

    function getSellerDateRange() {
        return {
            startDate: document.getElementById('sellerStartDate')?.value || '',
            endDate: document.getElementById('sellerEndDate')?.value || ''
        };
    }

    function rowMatchesSellerDateRange(row, startDate, endDate) {
        const rowDate = row.dataset.orderDate || '';
        const matchesDateStart = !startDate || (rowDate && rowDate >= startDate);
        const matchesDateEnd = !endDate || (rowDate && rowDate <= endDate);
        return matchesDateStart && matchesDateEnd;
    }

    function getSellerDateFilteredRows() {
        const { startDate, endDate } = getSellerDateRange();
        return sellerRows.filter(row => rowMatchesSellerDateRange(row, startDate, endDate));
    }

    function setSellerStatValue(key, value) {
        const el = document.querySelector(`[data-stat-value="${key}"]`);
        if (el) el.textContent = value;
    }

    function updateSellerStatCards() {
        const rows = getSellerDateFilteredRows();
        const revenue = rows
            .filter(row => ['delivered', 'completed'].includes(row.dataset.status))
            .reduce((sum, row) => sum + (Number(row.dataset.totalAmount) || 0), 0);

        setSellerStatValue('today', rows.filter(row => row.dataset.isToday === 'true').length);
        setSellerStatValue(
            'payment_review',
            rows.filter(row => row.dataset.paymentStatus === 'pending_verification').length
        );
        setSellerStatValue(
            'preparing',
            rows.filter(row => ['accepted', 'preparing'].includes(row.dataset.status)).length
        );
        setSellerStatValue(
            'on_delivery',
            rows.filter(row => row.dataset.status === 'on_delivery').length
        );
        setSellerStatValue(
            'delivered',
            rows.filter(row => row.dataset.status === 'delivered').length
        );
        setSellerStatValue(
            'completed',
            rows.filter(row => row.dataset.status === 'completed').length
        );
        setSellerStatValue(
            'revenue',
            `Php ${(Number(revenue) || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
        );
    }

    function getFilteredSellerRows() {
        const search = (document.getElementById('sellerOrderSearch').value || '').trim().toLowerCase();
        const status = document.getElementById('sellerStatusSelect').value;
        const payment = document.getElementById('sellerPaymentSelect').value;
        const { startDate, endDate } = getSellerDateRange();

        return sellerRows.filter(row => {
            const matchesSearch = !search || (row.dataset.search || '').includes(search);
            const matchesStatus = status === 'all' || row.dataset.status === status;
            const matchesPayment = payment === 'all' || (row.dataset.paymentMethod || '') === payment;
            const matchesDate = rowMatchesSellerDateRange(row, startDate, endDate);
            let matchesCard = true;

            if (sellerCardFilter?.type === 'status') {
                matchesCard = row.dataset.status === sellerCardFilter.value;
            } else if (sellerCardFilter?.type === 'status-group') {
                matchesCard = sellerCardFilter.values.includes(row.dataset.status);
            } else if (sellerCardFilter?.type === 'payment') {
                matchesCard = row.dataset.paymentStatus === sellerCardFilter.value;
            } else if (sellerCardFilter?.type === 'today') {
                matchesCard = (row.dataset.isToday || '') === 'true';
            }

            return matchesSearch && matchesStatus && matchesPayment && matchesDate && matchesCard;
        });
    }

    function updateSellerPanelSubtitle(totalRows) {
        if (!sellerPanelSub) return;

        const dateFilteredCount = getSellerDateFilteredRows().length;
        const baseText = `${SELLER_STORE_NAME} • ${dateFilteredCount} total orders`;
        if (!sellerCardFilter) {
            sellerPanelSub.innerHTML = baseText;
            return;
        }

        const label = sellerCardFilter.label || 'Filtered';
        sellerPanelSub.innerHTML = `${baseText} • <strong>${label} (${totalRows})</strong>`;
    }

    function updateActiveSellerCard() {
        sellerStatCards.forEach(card => {
            const isActive = sellerCardFilter && card.dataset.filterType === sellerCardFilter.type && card.dataset.filterValue === (sellerCardFilter.rawValue || '');
            const isTodayActive = sellerCardFilter?.type === 'today' && card.dataset.filterType === 'today';
            card.classList.toggle('is-active', !!(isActive || isTodayActive));
        });
    }

    function applySellerFilters(resetPage = false) {
        if (resetPage) sellerCurrentPage = 1;

        const filteredRows = getFilteredSellerRows();
        const totalRows = filteredRows.length;
        const totalPages = Math.max(1, Math.ceil(totalRows / sellerRowsPerPage));
        if (sellerCurrentPage > totalPages) sellerCurrentPage = totalPages;

        const startIndex = totalRows === 0 ? 0 : (sellerCurrentPage - 1) * sellerRowsPerPage;
        const endIndex = Math.min(startIndex + sellerRowsPerPage, totalRows);
        const visibleRows = new Set(filteredRows.slice(startIndex, endIndex));

        sellerRows.forEach(row => {
            row.style.display = visibleRows.has(row) ? '' : 'none';
        });

        if (sellerNoRecordsRow) {
            sellerNoRecordsRow.style.display = totalRows === 0 ? '' : 'none';
        }

        if (sellerPaginationWrap) {
            sellerPaginationWrap.style.display = totalRows > 0 ? 'flex' : 'none';
        }

        if (sellerPaginationInfo) {
            if (totalRows === 0) {
                sellerPaginationInfo.textContent = 'Page 1 of 1';
            } else {
                sellerPaginationInfo.textContent = `Page ${sellerCurrentPage} of ${totalPages}`;
            }
        }

        if (sellerOrdersPrevBtn) {
            sellerOrdersPrevBtn.disabled = sellerCurrentPage <= 1 || totalRows === 0;
        }
        if (sellerOrdersNextBtn) {
            sellerOrdersNextBtn.disabled = sellerCurrentPage >= totalPages || totalRows === 0;
        }

        updateSellerStatCards();
        updateSellerPanelSubtitle(totalRows);
        updateActiveSellerCard();
    }

    function productNamesFromOrder(order) {
        return (order.items || []).map(function (item) { return item.product_name || ''; }).join(' ');
    }

    function buildSellerOrderRow(order, todayStr) {
        const id = order.id;
        const status = order.status || '';
        const payStatus = String(order.payment_status || '').toLowerCase();
        const payMethod = String(order.payment_method || '').toLowerCase();
        const total = Number(order.display_total != null ? order.display_total : (order.total_amount || 0));
        const dateFormatted = order.date_formatted || '';
        const customerName = order.customer_name || 'Customer';
        const contact = order.customer_contact || order.customer_phone || 'No contact';
        const items = order.items || [];
        const itemsCount = Number(order.items_count != null ? order.items_count : items.reduce(function (s, i) { return s + Number(i.quantity || 0); }, 0));
        const search = (
            '#' + id + ' ' + customerName + ' ' + (order.customer_contact || order.customer_phone || '') + ' ' +
            (order.delivery_address || '') + ' ' + productNamesFromOrder(order)
        ).toLowerCase();
        const preview = items.slice(0, 2).map(function (item) {
            const addons = (item.addons || []).map(function (a) {
                const qty = Number(a.quantity || 1);
                return `<div style="font-size:11px;color:var(--muted);margin-top:2px;">+ ${escapeHtml(a.name || '')}${qty > 1 ? ' ×' + qty : ''}</div>`;
            }).join('');
            return `<div class="order-item-mini">${escapeHtml(item.product_name || 'Item')} x${item.quantity || 0}${addons}</div>`;
        }).join('');
        const more = items.length > 2 ? `<div class="order-item-more">+${items.length - 2} more items</div>` : '';
        const needsReview = payStatus === 'pending_verification';
        const proofUrl = order.payment_proof_url || '';
        const canApproveCod = payStatus === 'cod_pending' && (status === 'pending' || status === 'accepted');
        const checkbox = status === 'preparing'
            ? `<input type="checkbox" class="order-checkbox batch-order-checkbox" data-order-id="${id}" value="${id}"${selectedOrderIds.has(Number(id)) ? ' checked' : ''}>`
            : '';
        let receiptBtn = '';
        if (proofUrl) {
            receiptBtn = `<button type="button"
                class="orders-action-btn seller-view-payment ${needsReview ? 'warning' : 'receipt-ok'}"
                data-order-id="${id}"
                data-proof-url="${escapeAttr(proofUrl)}"
                data-customer-name="${escapeAttr(customerName)}"
                data-customer-contact="${escapeAttr(order.customer_contact || '')}"
                data-customer-contact-label="${escapeAttr(order.customer_contact_label || 'Contact')}"
                data-order-total="${total.toFixed(2)}"
                data-payment-method="${escapeAttr(order.payment_method || '')}"
                title="${needsReview ? 'Review receipt' : 'View receipt'}"
                aria-label="${needsReview ? 'Review unverified payment receipt' : 'View verified payment receipt'}">
                <i class="${needsReview ? 'ri-error-warning-line' : 'ri-checkbox-circle-line'}" aria-hidden="true"></i>
                <span class="btn-label">${needsReview ? 'Review' : 'Receipt'}</span>
            </button>`;
        }
        const doneBtn = status === 'preparing'
            ? `<button type="button" class="orders-action-btn success seller-mark-done" data-order-id="${id}" title="Done" aria-label="Mark as done">
                    <i class="ri-checkbox-line"></i><span class="btn-label">Done</span>
               </button>`
            : '';
        const canCancelCod = payMethod === 'cod' && (status === 'pending' || status === 'accepted' || status === 'preparing');
        const cancelCodBtn = canCancelCod
            ? `<button type="button" class="orders-action-btn danger seller-cancel-cod" data-order-id="${id}" title="Cancel COD Order" aria-label="Cancel COD Order" style="background:rgba(220,53,69,0.1);color:#dc3545;border-color:rgba(220,53,69,0.3);">
                    <i class="ri-close-circle-line"></i><span class="btn-label">Cancel COD</span>
               </button>`
            : '';
        const isCustomOrder = (order.order_type === 'custom_chat') || !!order.custom_ticket_id;
        const customBadge = isCustomOrder ? ' <span class="badge" style="background:#b5445a;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:4px;font-weight:600;">CUSTOM</span>' : '';
        return `<tr class="seller-order-row"
            data-order-id="${id}"
            data-status="${escapeAttr(status)}"
            data-payment-status="${escapeAttr(payStatus)}"
            data-payment-method="${escapeAttr(payMethod)}"
            data-order-date="${escapeAttr(dateFormatted)}"
            data-is-today="${dateFormatted === todayStr ? 'true' : 'false'}"
            data-total-amount="${total}"
            data-search="${escapeAttr(search)}">
            <td style="width: 36px; text-align: center;">${checkbox}</td>
            <td data-label="Order">
                <div class="order-code">#${id}</div>
                <div class="order-subline">${escapeHtml(titleCaseStatus(order.order_type || ''))}${customBadge}</div>
                <div class="order-subline">${escapeHtml(order.datetime_formatted || order.created_at || '')}</div>
            </td>
            <td data-label="Customer">
                <div class="order-code" style="font-size:14px;">${escapeHtml(customerName)}</div>
                <div class="order-subline">${escapeHtml(contact)}</div>
            </td>
            <td data-label="Payment Status">
                <span class="payment-pill payment-combined payment-${escapeAttr(payStatus)}">${escapeHtml(formatPaymentCombined(payMethod, payStatus))}</span>
            </td>
            <td data-label="Status">
                <span class="status-pill status-${escapeAttr(status)}">${escapeHtml(titleCaseStatus(status))}</span>
            </td>
            <td data-label="Summary">
                <div class="order-code" style="font-size:15px;">Php ${formatAmount(total)}</div>
                <div class="order-subline">${itemsCount} item${itemsCount !== 1 ? 's' : ''}</div>
                <div class="order-items-preview" style="margin-top:0.45rem;">${preview}${more}</div>
            </td>
            <td class="actions-cell" data-label="Actions">
                <div class="action-row">
                    <button type="button" class="orders-action-btn seller-view-order" data-order-id="${id}" title="View" aria-label="View order details">
                        <i class="ri-eye-line"></i><span class="btn-label">View</span>
                    </button>
                    ${receiptBtn}${doneBtn}${approveBtn}${cancelCodBtn}
                </div>
            </td>
        </tr>`;
    }

    function applySellerOrdersPayload(data, opts) {
        const options = opts || {};
        const prevIds = new Set(sellerRows.map(function (row) { return String(row.dataset.orderId); }));
        if (data.today_str) SELLER_TODAY_STR = data.today_str;
        if (data.sync_token) sellerSyncToken = data.sync_token;
        const orders = data.orders || [];
        const emptyEl = document.getElementById('sellerOrdersEmpty');
        let noRow = document.getElementById('sellerNoRecordsRow');
        if (!noRow) {
            noRow = document.createElement('tr');
            noRow.id = 'sellerNoRecordsRow';
            noRow.style.display = 'none';
            noRow.innerHTML = '<td colspan="7" style="text-align:center;color:var(--muted);padding:1.2rem 0.9rem;font-size:13px;">No records available</td>';
        }
        sellerOrdersTbody.innerHTML = orders.map(function (order) {
            return buildSellerOrderRow(order, SELLER_TODAY_STR);
        }).join('');
        sellerOrdersTbody.appendChild(noRow);
        sellerNoRecordsRow = noRow;
        sellerRows = Array.from(sellerOrdersTbody.querySelectorAll('.seller-order-row'));
        if (emptyEl) emptyEl.style.display = orders.length ? 'none' : '';
        if (options.highlightNew && prevIds.size) {
            sellerRows.forEach(function (row) {
                if (!prevIds.has(String(row.dataset.orderId))) {
                    row.classList.add('is-highlighted');
                    setTimeout(function () { row.classList.remove('is-highlighted'); }, 2800);
                }
            });
        }
        applySellerFilters(false);
        if (typeof window.refreshSellerSidebarBadges === 'function') window.refreshSellerSidebarBadges();
    }

    async function reloadSellerOrdersTable(opts) {
        if (sellerLiveBusy) return;
        sellerLiveBusy = true;
        try {
            const res = await fetch('/api/seller/orders?t=' + Date.now(), {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            if (!res.ok) return;
            const payload = await res.json();
            applySellerOrdersPayload(payload, opts || { highlightNew: true });
        } catch (e) {
        } finally {
            sellerLiveBusy = false;
        }
    }

    async function pollSellerOrdersLive() {
        if (document.hidden || sellerLiveBusy) return;
        if (document.querySelector('.app-confirm-overlay.show')) return;
        try {
            const res = await fetch('/api/seller/orders/sync?t=' + Date.now(), {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            if (!res.ok) return;
            const data = await res.json();
            if (!data.sync_token || data.sync_token === sellerSyncToken) return;
            await reloadSellerOrdersTable({ highlightNew: true });
        } catch (e) {}
    }

    setInterval(pollSellerOrdersLive, 2000);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) pollSellerOrdersLive();
    });
    window.addEventListener('focus', pollSellerOrdersLive);

    document.getElementById('sellerOrderSearch').addEventListener('input', () => applySellerFilters(true));
    document.getElementById('sellerStatusSelect').addEventListener('change', () => applySellerFilters(true));
    document.getElementById('sellerPaymentSelect').addEventListener('change', () => applySellerFilters(true));

    const sellerDateRange = (typeof bindLinkedDatePickers === 'function')
        ? bindLinkedDatePickers('#sellerStartDate', '#sellerEndDate', {
            onChange: () => applySellerFilters(true)
        })
        : null;

    document.getElementById('sellerDateResetBtn').addEventListener('click', () => {
        const start = document.getElementById('sellerStartDate');
        const end = document.getElementById('sellerEndDate');
        start.value = '';
        end.value = '';
        if (sellerDateRange) sellerDateRange.clearLimits();
        else {
            start.removeAttribute('max');
            end.removeAttribute('min');
        }
        applySellerFilters(true);
    });
    sellerOrdersPrevBtn?.addEventListener('click', () => {
        if (sellerCurrentPage > 1) {
            sellerCurrentPage -= 1;
            applySellerFilters();
        }
    });
    sellerOrdersNextBtn?.addEventListener('click', () => {
        const totalRows = getFilteredSellerRows().length;
        const totalPages = Math.max(1, Math.ceil(totalRows / sellerRowsPerPage));
        if (sellerCurrentPage < totalPages) {
            sellerCurrentPage += 1;
            applySellerFilters();
        }
    });
    document.getElementById('refreshOrdersBtn').addEventListener('click', () => {
        reloadSellerOrdersTable({ highlightNew: false });
    });

    sellerStatCards.forEach(card => {
        card.addEventListener('click', () => {
            const type = card.dataset.filterType;
            const rawValue = card.dataset.filterValue || '';
            const label = card.querySelector('.kpi-label')?.textContent?.trim() || 'Filtered';

            const sameFilter = sellerCardFilter &&
                sellerCardFilter.type === type &&
                sellerCardFilter.rawValue === rawValue;

            if (sameFilter) {
                sellerCardFilter = null;
            } else if (type === 'status-group') {
                sellerCardFilter = { type, rawValue, values: rawValue.split(',').map(v => v.trim()), label };
            } else if (type === 'today') {
                sellerCardFilter = { type, rawValue, label };
            } else {
                sellerCardFilter = { type, rawValue, value: rawValue, label };
            }

            applySellerFilters(true);
        });
    });

    if (sellerOrdersTbody) {
    sellerOrdersTbody.addEventListener('click', function (e) {
        const viewBtn = e.target.closest('.seller-view-order');
        if (viewBtn) {
            openSellerOrderDetails(viewBtn.dataset.orderId);
            return;
        }
        const payBtn = e.target.closest('.seller-view-payment');
        if (payBtn) {
            openSellerPaymentProof(payBtn);
            return;
        }
        const doneBtn = e.target.closest('.seller-mark-done');
        if (doneBtn) {
            markTableOrderDonePreparing(doneBtn);
            return;
        }
        const approveBtn = e.target.closest('.seller-approve-cod');
        if (approveBtn) {
            (async function () {
                const orderId = approveBtn.dataset.orderId;
                if (!orderId) return;
                if (!await window.openConfirmModal('Approve this COD order and move it to Preparing?')) return;
                await verifyPayment(orderId);
            })();
            return;
        }
        const cancelCodBtn = e.target.closest('.seller-cancel-cod');
        if (cancelCodBtn) {
            (async function () {
                const orderId = cancelCodBtn.dataset.orderId;
                if (!orderId) return;
                const reason = await window.openPromptModal(
                    'Please enter the reason for cancelling this COD order:',
                    {
                        title: 'Cancel COD Order',
                        defaultValue: 'Customer requested cancellation via chat',
                        placeholder: 'e.g. customer requested in chat',
                        confirmText: 'Cancel Order',
                        cancelText: 'Go Back',
                    }
                );
                if (reason === null) return; // cancelled prompt
                cancelCodBtn.disabled = true;
                try {
                    const response = await fetch(`/api/v1/chat/orders/${orderId}/cancel-cod`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ reason: reason.trim() || 'Cancelled by seller upon customer request' })
                    });
                    const data = await response.json();
                    if (!response.ok || !data.success) {
                        throw new Error(data.error || 'Failed to cancel order');
                    }
                    showSellerAlert('success', data.message || 'COD order cancelled successfully and inventory restored.');
                    await reloadSellerOrdersTable({ highlightNew: false });
                } catch (err) {
                    showSellerAlert('danger', err.message || 'Could not cancel COD order.');
                } finally {
                    cancelCodBtn.disabled = false;
                }
            })();
            return;
        }
    });
    }

    async function openSellerOrderDetails(orderId) {
        if (!orderId) return;
        const body = document.getElementById('sellerOrderDetailsBody');
        const titleEl = document.getElementById('sellerOrderDetailsModalTitle');
        let loadedOrder = null;
        if (titleEl) titleEl.textContent = 'Order';
        body.innerHTML = '<div class="text-center py-4 text-muted">Loading...</div>';
        openModal(sellerOrderDetailsModal);
        try {
            const response = await sellerFetch(`/api/seller/orders/${orderId}`);
            const order = await response.json();
            if (!response.ok) throw new Error(order.error || 'Failed to load order');
            loadedOrder = order;

            const orderItems = order.items || [];
            const itemsSubtotal = orderItems.reduce((sum, item) => {
                const addons = Array.isArray(item.addons) ? item.addons : [];
                const addonsTotal = Number(item.addons_total != null
                    ? item.addons_total
                    : addons.reduce((s, a) => s + Number(a.total != null ? a.total : (Number(a.price || 0) * Number(a.quantity || 1))), 0));
                const lineTotal = Number(item.total != null
                    ? item.total
                    : ((item.quantity || 0) * (item.price || 0)) + addonsTotal);
                return sum + lineTotal;
            }, 0);
            const deliveryFee = Number(order.delivery_fee || 0);
            const displaySubtotal = itemsSubtotal > 0 ? itemsSubtotal : Number(order.subtotal_amount || 0);
            const displayTotal = displaySubtotal + deliveryFee;

            const itemsHtml = (order.items || []).map(item => {
                const addons = Array.isArray(item.addons) ? item.addons : [];
                const addonsTotal = Number(item.addons_total != null
                    ? item.addons_total
                    : addons.reduce((s, a) => s + Number(a.total != null ? a.total : (Number(a.price || 0) * Number(a.quantity || 1))), 0));
                const lineTotal = Number(item.total != null
                    ? item.total
                    : ((item.quantity || 0) * (item.price || 0)) + addonsTotal);
                const addonsHtml = addons.length
                    ? `<div style="margin-top:6px;display:flex;flex-direction:column;gap:4px;">
                        ${addons.map(a => {
                            const aName = a.name || 'Add-on';
                            const aQty = Math.max(1, Number(a.quantity || 1));
                            const aTotal = Number(a.total != null ? a.total : (Number(a.price || 0) * aQty));
                            const aImg = a.image_url
                                ? `<img src="${a.image_url}" alt="${aName}" style="width:22px;height:22px;object-fit:cover;border-radius:5px;border:1px solid var(--border);vertical-align:middle;margin-right:6px;">`
                                : '';
                            return `<div style="font-size:12px;color:var(--muted);">${aImg}+ ${aName}${aQty > 1 ? ` ×${aQty}` : ''} · ₱${formatAmount(aTotal)}</div>`;
                        }).join('')}
                    </div>`
                    : '';
                return `
                <tr>
                    <td class="sdm-line-thumb-cell">${lineItemThumb(item.product_image_url)}</td>
                    <td>
                        ${item.product_name || 'Product'}${item.variant_name ? ` <span style="color:var(--deep-rose)">(${item.variant_name})</span>` : ''}
                        ${addonsHtml}
                    </td>
                    <td>${item.quantity || 0}</td>
                    <td>Php ${formatAmount(item.price || 0)}</td>
                    <td>Php ${formatAmount(lineTotal)}</td>
                </tr>
            `;
            }).join('');
            const proofHtml = [
                { label: 'Finished product', url: order.done_preparing_proof_url },
                { label: 'Rider proof 1', url: order.delivery_proof_url },
                { label: 'Rider proof 2', url: order.delivery_proof_2_url }
            ].filter(p => !!p.url).map(p => `
                <figure class="sdm-proof-fig">
                    <img src="${p.url}" alt="${p.label}" loading="lazy">
                    <figcaption class="sdm-proof-cap">${p.label}</figcaption>
                </figure>
            `).join('');

            const mt = document.getElementById('sellerOrderDetailsModalTitle');
            if (mt) mt.textContent = `Order #${order.id}`;

            const isCancelled = String(order.status || '').toLowerCase() === 'cancelled';
            const cancelReason = (order.cancellation_reason || '').trim();
            const cancelRows = isCancelled ? `
                                    <div class="sdm-row"><span class="sdm-k">Reason</span><span class="sdm-v">${escapeHtml(cancelReason) || 'No reason provided'}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Cancelled</span><span class="sdm-v">${order.cancelled_at ? formatDateTime(order.cancelled_at) : '—'}</span></div>` : '';

            body.innerHTML = `
                    <div class="sdm">
                        <header class="sdm-topbar">
                            <div class="sdm-topbar-left">
                                <span class="sdm-oid">#${order.id}</span>
                                <span class="status-pill status-${order.status}">${titleCaseStatus(order.status)}</span>
                            </div>
                            <span class="sdm-when">${formatDateTime(order.created_at)} · ${titleCaseStatus(order.order_type)}</span>
                        </header>

                        <div class="sdm-grid">
                            <section class="sdm-block">
                                <h4>Customer</h4>
                                <div class="sdm-rows">
                                    <div class="sdm-row"><span class="sdm-k">Name</span><span class="sdm-v">${escapeHtml(order.customer_name) || '—'}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">${escapeHtml(order.customer_contact_label) || 'Contact'}</span><span class="sdm-v">${escapeHtml(order.customer_contact) || '—'}</span></div>
                                </div>
                            </section>
                            <section class="sdm-block">
                                <h4>Payment</h4>
                                <div class="sdm-rows">
                                    <div class="sdm-row"><span class="sdm-k">Payment</span><span class="sdm-v">${escapeHtml(formatPaymentCombined(order.payment_method, order.payment_status))}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Subtotal</span><span class="sdm-v">₱${formatAmount(displaySubtotal)}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Delivery</span><span class="sdm-v">₱${formatAmount(deliveryFee)}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Total</span><span class="sdm-v" style="font-weight:600;color:var(--charcoal);">₱${formatAmount(displayTotal)}</span></div>
                                </div>
                            </section>
                            <section class="sdm-block">
                                <h4>Rider</h4>
                                <div class="sdm-rows">
                                    <div class="sdm-row"><span class="sdm-k">Name</span><span class="sdm-v">${escapeHtml(order.rider_name) || 'Not assigned'}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Vehicle</span><span class="sdm-v">${escapeHtml(order.rider_vehicle) || '—'}</span></div>
                                </div>
                            </section>
                            <section class="sdm-block">
                                <h4>Schedule</h4>
                                <div class="sdm-rows">
                                    <div class="sdm-row"><span class="sdm-k">Distance</span><span class="sdm-v">${order.distance_km ? `${Number(order.distance_km).toFixed(2)} km` : '—'}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Date</span><span class="sdm-v">${order.requested_delivery_date ? formatDate(order.requested_delivery_date) : '—'}</span></div>
                                    <div class="sdm-row"><span class="sdm-k">Time</span><span class="sdm-v">${formatDeliveryTimeSlot(order.requested_delivery_time)}</span></div>
                                </div>
                            </section>
                        </div>

                            <section class="sdm-block sdm-block--full">
                            <h4>Delivery</h4>
                            <div class="sdm-rows">
                                <div class="sdm-row"><span class="sdm-k">Address</span><span class="sdm-v">${escapeHtml(order.delivery_address) || '—'}</span></div>
                                <div class="sdm-row"><span class="sdm-k">Notes</span><span class="sdm-v">${escapeHtml(order.delivery_notes) || '—'}</span></div>
                                ${cancelRows}
                            </div>
                        </section>

                        <section class="sdm-block sdm-block--full">
                            <h4>Line items</h4>
                            <div class="sdm-table-wrap">
                                <table class="sdm-table">
                                    <thead>
                                        <tr>
                                            <th class="sdm-line-thumb-cell" aria-label="Preview"></th>
                                            <th>Product</th>
                                            <th>Qty</th>
                                            <th>Price</th>
                                            <th>Total</th>
                                        </tr>
                                    </thead>
                                    <tbody>${itemsHtml}</tbody>
                                </table>
                            </div>
                        </section>
                        ${proofHtml ? `
                        <section class="sdm-block sdm-block--full">
                            <h4>Proof</h4>
                            <div class="sdm-proofs">${proofHtml}</div>
                        </section>` : ''}
                    </div>
                `;
            } catch (error) {
                if (titleEl) titleEl.textContent = 'Order';
                body.innerHTML = `<div class="text-danger">${error.message || 'Failed to load order.'}</div>`;
            }

            // Update footer with action button
            const footer = document.getElementById('sellerOrderDetailsFooter');
            if (footer) {
                if (loadedOrder && loadedOrder.status === 'preparing') {
                    footer.innerHTML = `
                        <button type="button" class="btn btn-success" id="markDonePreparingBtn"><i class="ri-checkbox-line"></i> Mark as Done Preparing</button>
                    `;
                    document.getElementById('markDonePreparingBtn').addEventListener('click', () => markOrderDonePreparing(loadedOrder.id));
                } else {
                    footer.innerHTML = '';
                }
            }
    }

    // Deep-link from seller notifications: /seller/orders?order_id=123
    (function openOrderFromQuery() {
        try {
            const params = new URLSearchParams(window.location.search);
            const orderId = params.get('order_id');
            if (!orderId) return;
            // Highlight / scroll to the row if present
            const safeId = String(orderId).replace(/"/g, '');
            const row = document.querySelector(`tr[data-order-id="${safeId}"]`);
            if (row && row.scrollIntoView) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                row.classList.add('is-highlighted');
            }
            openSellerOrderDetails(safeId);
            // Clean URL without reload
            params.delete('order_id');
            const clean = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}${window.location.hash || ''}`;
            window.history.replaceState({}, '', clean);
        } catch (e) {
            console.warn('Could not open order from notification link', e);
        }
    })();

    async function markDonePreparingWithProof(orderId) {
        const selectedFile = await pickFinishedProductImage();
        if (!selectedFile) {
            throw new Error('Finished product image is required.');
        }
        const uploadFile = await prepareFinishedProductImage(selectedFile);
        const confirmed = await window.openConfirmModal('Mark this order as Done Preparing?');
        if (!confirmed) return null;

        const formData = new FormData();
        formData.append('status', 'done_preparing');
        formData.append('finished_product_image', uploadFile, uploadFile.name || 'finished-product.jpg');
        return formData;
    }

    async function markOrderDonePreparing(orderId) {
        let formData;
        try {
            formData = await markDonePreparingWithProof(orderId);
            if (!formData) return;
        } catch (error) {
            showSellerAlert('danger', error.message || 'Please upload the finished product image first.');
            return;
        }

        const btn = document.getElementById('markDonePreparingBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-loading-ui"><span class="loading-spin"></span><span class="loading-text">Updating…</span></span>';
        try {
            const response = await sellerFetch(`/api/seller/orders/${orderId}/status`, {
                method: 'PUT',
                body: formData
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Failed to update status');
            closeModal(sellerOrderDetailsModal);
            showSellerAlert('success', 'Order marked as Done Preparing.');
            await reloadSellerOrdersTable({ highlightNew: false });
        } catch (error) {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-checkbox-line"></i> Mark as Done Preparing';
            showSellerAlert('danger', error.message || 'Could not update order status.');
        }
    }

    async function markTableOrderDonePreparing(button) {
        let formData;
        try {
            formData = await markDonePreparingWithProof(button.dataset.orderId);
            if (!formData) return;
        } catch (error) {
            showSellerAlert('danger', error.message || 'Please upload the finished product image first.');
            return;
        }

        const orderId = button.dataset.orderId;
        button.disabled = true;
        button.innerHTML = '<span class="btn-loading-ui"><span class="loading-spin"></span><span class="loading-text">Updating…</span></span>';
        try {
            const response = await sellerFetch(`/api/seller/orders/${orderId}/status`, {
                method: 'PUT',
                body: formData
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Failed to update status');
            showSellerAlert('success', 'Order marked as Done Preparing.');
            await reloadSellerOrdersTable({ highlightNew: false });
        } catch (error) {
            button.disabled = false;
            button.innerHTML = '<i class="ri-checkbox-line"></i> Done';
            showSellerAlert('danger', error.message || 'Could not update order status.');
        }
    }

    async function pickFinishedProductImage() {
        return new Promise(resolve => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/*';
            input.onchange = () => resolve(input.files && input.files[0] ? input.files[0] : null);
            input.click();
        });
    }

    async function prepareFinishedProductImage(file) {
        const MAX_UPLOAD_SIZE = 10 * 1024 * 1024; // 10MB Cloudinary unsigned limit
        if (file.size <= MAX_UPLOAD_SIZE) return file;

        if (!file.type.startsWith('image/')) {
            throw new Error('Please select an image file under 10MB.');
        }

        showSellerAlert('info', 'Selected image is large. Compressing before upload...');
        const compressed = await compressImageToMaxSize(file, MAX_UPLOAD_SIZE);
        if (!compressed || compressed.size > MAX_UPLOAD_SIZE) {
            throw new Error('Image is too large. Please choose a smaller file (max 10MB).');
        }
        return compressed;
    }

    async function compressImageToMaxSize(file, maxBytes) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
                const img = new Image();
                img.onload = async () => {
                    let width = img.width;
                    let height = img.height;
                    const maxDim = 2400;
                    if (width > maxDim || height > maxDim) {
                        const ratio = Math.min(maxDim / width, maxDim / height);
                        width = Math.round(width * ratio);
                        height = Math.round(height * ratio);
                    }

                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);

                    const baseName = (file.name || 'finished-product').replace(/\.[^.]+$/, '');
                    let quality = 0.9;
                    let blob = null;

                    while (quality >= 0.45) {
                        blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', quality));
                        if (blob && blob.size <= maxBytes) break;
                        quality -= 0.1;
                    }

                    if (!blob) {
                        resolve(null);
                        return;
                    }

                    resolve(new File([blob], `${baseName}.jpg`, { type: 'image/jpeg' }));
                };
                img.onerror = () => resolve(null);
                img.src = reader.result;
            };
            reader.onerror = () => resolve(null);
            reader.readAsDataURL(file);
        });
    }

    function openSellerPaymentProof(button) {
        activePaymentOrderId = button.dataset.orderId;
        const proofImage = document.getElementById('sellerPaymentProofImage');
        const proofEmpty = document.getElementById('sellerPaymentProofEmpty');
        const contactLabel = button.dataset.customerContactLabel || 'Contact';
        const contactValue = button.dataset.customerContact || '';
        const combinedLabel = formatPaymentCombined(
            button.dataset.paymentMethod,
            button.closest('tr')?.dataset.paymentStatus
        );
        const methodPill = document.getElementById('sellerPaymentProofMethodPill');

        document.getElementById('sellerPaymentProofOrder').textContent = `#${button.dataset.orderId || '—'}`;
        document.getElementById('sellerPaymentProofCustomer').textContent = button.dataset.customerName || '—';
        document.getElementById('sellerPaymentProofContactLabel').textContent = contactLabel;
        document.getElementById('sellerPaymentProofContact').textContent = contactValue || '—';
        document.getElementById('sellerPaymentProofAmount').textContent = `₱${formatAmount(button.dataset.orderTotal || 0)}`;
        if (methodPill) {
            methodPill.textContent = combinedLabel;
            methodPill.className = 'payment-pill payment-combined';
            const statusKey = String(button.closest('tr')?.dataset.paymentStatus || '').toLowerCase().replace(/\s+/g, '_');
            if (statusKey) methodPill.classList.add(`payment-${statusKey}`);
        }

        proofEmpty.style.display = 'none';
        proofImage.style.display = 'block';
        proofImage.src = button.dataset.proofUrl;
        document.getElementById('sellerVerifyPaymentBtn').style.display =
            button.closest('tr')?.dataset.paymentStatus === 'pending_verification' ? 'inline-flex' : 'none';
        openModal(sellerPaymentProofModal);
    }

    async function verifyPayment(orderId) {
        try {
            const response = await sellerFetch(`/api/seller/orders/${orderId}/verify-payment`, { method: 'PUT' });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Could not verify payment');
            closeModal(sellerPaymentProofModal);
            showSellerAlert('success', 'Payment verified. Order status changed to Preparing.');
            await reloadSellerOrdersTable({ highlightNew: false });
        } catch (error) {
            showSellerAlert('danger', error.message || 'Could not verify payment.');
        }
    }

    document.getElementById('sellerVerifyPaymentBtn').addEventListener('click', () => {
        if (activePaymentOrderId) verifyPayment(activePaymentOrderId);
    });

    const proofImage = document.getElementById('sellerPaymentProofImage');
    const proofEmpty = document.getElementById('sellerPaymentProofEmpty');
    proofImage.addEventListener('load', () => {
        proofEmpty.style.display = 'none';
        proofImage.style.display = 'block';
    });
    proofImage.addEventListener('error', () => {
        proofImage.style.display = 'none';
        proofEmpty.style.display = 'block';
    });

    document.querySelectorAll('[data-close-modal]').forEach(button => {
        button.addEventListener('click', () => {
            closeModal(document.getElementById(button.getAttribute('data-close-modal')));
        });
    });

    // Use event delegation for dynamically added close buttons
    document.addEventListener('click', function(e) {
        if (e.target.hasAttribute('data-close-modal')) {
            closeModal(document.getElementById(e.target.getAttribute('data-close-modal')));
        }
    });

    [sellerOrderDetailsModal, sellerPaymentProofModal].forEach(modal => {
        modal.addEventListener('click', event => {
            if (event.target === modal) closeModal(modal);
        });
    });

    // ===== Batch Selection Feature =====
    const batchActionsToolbar = document.getElementById('batchActionsToolbar');
    const batchSelectedCount = document.getElementById('batchSelectedCount');
    const batchMarkDoneBtn = document.getElementById('batchMarkDoneBtn');
    const batchCancelBtn = document.getElementById('batchCancelBtn');
    const selectAllCheckbox = document.getElementById('selectAllOrders');

    function updateBatchUI() {
        const visiblePreparing = Array.from(document.querySelectorAll('.batch-order-checkbox')).filter(cb => {
            return cb.closest('tr').style.display !== 'none';
        });
        const visibleIds = new Set(visiblePreparing.map(cb => parseInt(cb.dataset.orderId)));
        selectedOrderIds = new Set(Array.from(selectedOrderIds).filter(id => visibleIds.has(id)));
        const hasSelectedVisible = selectedOrderIds.size > 0;

        batchSelectedCount.textContent = selectedOrderIds.size;
        
        if (hasSelectedVisible) {
            batchActionsToolbar.style.display = 'flex';
        } else {
            batchActionsToolbar.style.display = 'none';
        }
        batchMarkDoneBtn.disabled = !hasSelectedVisible;

        // Update select-all checkbox state (only when it exists)
        if (selectAllCheckbox) {
            const hasVisibleCheckable = visiblePreparing.length > 0;
            selectAllCheckbox.style.display = hasVisibleCheckable ? 'inline-block' : 'none';
            selectAllCheckbox.disabled = !hasVisibleCheckable;

            if (visiblePreparing.length > 0) {
                const allChecked = visiblePreparing.every(cb => cb.checked);
                const someChecked = visiblePreparing.some(cb => cb.checked);
                selectAllCheckbox.checked = allChecked;
                selectAllCheckbox.indeterminate = someChecked && !allChecked;
            } else {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = false;
            }
        }
    }

    // Handle individual checkboxes
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('batch-order-checkbox')) {
            const orderId = parseInt(e.target.dataset.orderId);
            if (e.target.checked) {
                selectedOrderIds.add(orderId);
            } else {
                selectedOrderIds.delete(orderId);
            }
            updateBatchUI();
        }
    });

    // Handle select-all checkbox
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.batch-order-checkbox');
            checkboxes.forEach(checkbox => {
                // Only select visible checkboxes
                if (checkbox.closest('tr').style.display !== 'none') {
                    checkbox.checked = this.checked;
                    const orderId = parseInt(checkbox.dataset.orderId);
                    if (this.checked) {
                        selectedOrderIds.add(orderId);
                    } else {
                        selectedOrderIds.delete(orderId);
                    }
                }
            });
            updateBatchUI();
        });
    }

    // Handle batch mark done
    batchMarkDoneBtn.addEventListener('click', async function() {
        if (selectedOrderIds.size === 0 || batchMarkDoneBtn.disabled) return;
        showSellerAlert('danger', 'Batch Done Preparing is disabled because each order now requires a finished-product image upload.');
        return;

        const orderIds = Array.from(selectedOrderIds);
        const confirmMsg = `Mark ${orderIds.length} order(s) as Done Preparing?`;
        const confirmed = await window.openConfirmModal(confirmMsg);
        if (!confirmed) return;

        batchMarkDoneBtn.disabled = true;
        const originalText = batchMarkDoneBtn.innerHTML;
        batchMarkDoneBtn.innerHTML = '<span class="btn-loading-ui"><span class="loading-spin"></span><span class="loading-text">Updating…</span></span>';

        let successCount = 0;
        let failureCount = 0;

        for (const orderId of orderIds) {
            try {
                const response = await fetch(`/api/seller/orders/${orderId}/status`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ status: 'done_preparing' })
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    successCount++;
                    // Remove checkbox and row styling
                    const checkbox = document.querySelector(`.batch-order-checkbox[data-order-id="${orderId}"]`);
                    if (checkbox) {
                        checkbox.closest('tr').remove();
                    }
                    selectedOrderIds.delete(orderId);
                } else {
                    failureCount++;
                }
            } catch (error) {
                failureCount++;
            }
        }

        batchMarkDoneBtn.disabled = false;
        batchMarkDoneBtn.innerHTML = originalText;

        if (successCount > 0) {
            showSellerAlert('success', `${successCount} order(s) marked as Done Preparing.`);
        }
        if (failureCount > 0) {
            showSellerAlert('danger', `Failed to update ${failureCount} order(s).`);
        }

        selectedOrderIds.clear();
        updateBatchUI();
    });

    // Handle batch cancel
    batchCancelBtn.addEventListener('click', function() {
        document.querySelectorAll('.batch-order-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
        selectedOrderIds.clear();
        updateBatchUI();
    });

    // Update batch UI when filters change
    const originalApplySellerFilters = applySellerFilters;
    applySellerFilters = function(resetPage = false) {
        originalApplySellerFilters(resetPage);
        updateBatchUI();
    };

    // Initialize UI
    applySellerFilters(true);

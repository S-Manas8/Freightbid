content = open('frontend/pages/shipper.html', encoding='utf-8').read()

old = """        function openCancelModal(shipmentId, currentStatus, tripAmount) {
            const existing = document.getElementById('cancel-shipment-modal');
            if (existing) existing.remove();

            const isAssigned = currentStatus === 'assigned';

            const warningHtml = isAssigned ? `
                <div id="cancel-fee-preview" style="padding:12px 14px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);
                             border-radius:8px;margin-bottom:16px;">
                    <div style="font-weight:700;font-size:0.85rem;color:#ef4444;margin-bottom:6px;">
                        ⚠️ Driver has been assigned — cancellation fee applies
                    </div>
                    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:10px;">
                        Fee = (km driver already travelled ÷ total route km) × ₹${(tripAmount||0).toLocaleString('en-IN')}
                    </div>
                    <div id="cancel-fee-breakdown" style="font-size:0.78rem;color:var(--muted);">
                        <div class="loading" style="padding:8px 0;">Calculating based on driver GPS...</div>
                    </div>
                </div>` : `
                <div style="padding:10px 14px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);
                             border-radius:8px;margin-bottom:16px;font-size:0.8rem;color:var(--muted);">
                    ℹ️ No driver assigned yet. This cancellation is free.
                </div>`;"""

new = """        function openCancelModal(shipmentId, currentStatus, tripAmount) {
            const existing = document.getElementById('cancel-shipment-modal');
            if (existing) existing.remove();

            const isAssigned  = currentStatus === 'assigned';
            const isInTransit = currentStatus === 'in_transit';
            const needsFee    = isAssigned || isInTransit;

            let feeFormula = '';
            if (isAssigned)  feeFormula = 'Fee = (km driver travelled ÷ total route km) × ₹' + (tripAmount||0).toLocaleString('en-IN');
            if (isInTransit) feeFormula = 'Fee = (stops completed ÷ total stops) × ₹' + (tripAmount||0).toLocaleString('en-IN');

            const warningHtml = needsFee ? `
                <div id="cancel-fee-preview" style="padding:12px 14px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);
                             border-radius:8px;margin-bottom:16px;">
                    <div style="font-weight:700;font-size:0.85rem;color:#ef4444;margin-bottom:6px;">
                        ⚠️ ${isInTransit ? 'Driver is on the road — proportional fee applies' : 'Driver has been assigned — cancellation fee applies'}
                    </div>
                    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:10px;">${feeFormula}</div>
                    <div id="cancel-fee-breakdown" style="font-size:0.78rem;color:var(--muted);">
                        <div class="loading" style="padding:8px 0;">Calculating...</div>
                    </div>
                </div>` : `
                <div style="padding:10px 14px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);
                             border-radius:8px;margin-bottom:16px;font-size:0.8rem;color:var(--muted);">
                    ℹ️ No driver assigned yet. This cancellation is free.
                </div>`;"""

old2 = """            // If assigned, fetch live GPS-based fee preview
            if (isAssigned) {
                fetchCancelPreview(shipmentId, tripAmount);
            }
        }"""

new2 = """            // Fetch live fee preview for assigned or in_transit
            if (needsFee) {
                fetchCancelPreview(shipmentId, tripAmount, currentStatus);
            }
        }"""

if old in content:
    content = content.replace(old, new, 1)
    print("Patched openCancelModal OK")
else:
    print("ERROR: openCancelModal old string not found")

if old2 in content:
    content = content.replace(old2, new2, 1)
    print("Patched needsFee trigger OK")
else:
    print("ERROR: needsFee trigger not found")

open('frontend/pages/shipper.html', 'w', encoding='utf-8').write(content)

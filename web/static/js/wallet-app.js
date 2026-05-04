/**
 * LUXE Wallet Page - Standalone Demo
 * No connection to payment/checkout logic
 */

(function() {
    const APP_TIMEZONE = 'Asia/Jakarta';

    // Dummy transaction data
    const TRANSACTIONS = [
        { id: 1, type: 'in',  label: 'Top Up via Bank Transfer',   amount: 500000,  date: '20 Apr 2026, 14:32', icon: '↑' },
        { id: 2, type: 'out', label: 'Purchase - Aura Pro Headphones', amount: 2499000, date: '19 Apr 2026, 10:15', icon: '🛒' },
        { id: 3, type: 'in',  label: 'Cashback Reward',            amount: 75000,   date: '18 Apr 2026, 22:01', icon: '🎁' },
        { id: 4, type: 'out', label: 'Transfer to @kevin_r',       amount: 150000,  date: '17 Apr 2026, 08:45', icon: '→' },
        { id: 5, type: 'in',  label: 'Top Up via Credit Card',     amount: 1000000, date: '16 Apr 2026, 19:20', icon: '↑' },
        { id: 6, type: 'out', label: 'Purchase - Pulse Mini Speaker', amount: 899000, date: '15 Apr 2026, 13:58', icon: '🛒' },
        { id: 7, type: 'in',  label: 'Refund - Order #28491',      amount: 899000,  date: '14 Apr 2026, 09:10', icon: '↩' },
        { id: 8, type: 'out', label: 'Transfer to @anissa_w',      amount: 200000,  date: '13 Apr 2026, 17:30', icon: '→' },
    ];

    let balance = 2450000;

    function formatRp(n) {
        return n.toLocaleString('id-ID');
    }

    function updateBalanceDisplay() {
        const el = document.getElementById('walletBalance');
        if (el) el.textContent = formatRp(balance);
    }

    // Render transactions
    function renderTransactions() {
        const list = document.getElementById('txList');
        if (!list) return;

        list.innerHTML = TRANSACTIONS.map(tx => `
            <div class="wallet-tx-item">
                <div class="wallet-tx-icon ${tx.type === 'in' ? 'tx-in' : 'tx-out'}">${tx.icon}</div>
                <div class="wallet-tx-details">
                    <div class="wallet-tx-label">${tx.label}</div>
                    <div class="wallet-tx-date">${tx.date}</div>
                </div>
                <div class="wallet-tx-amount ${tx.type === 'in' ? 'tx-in' : 'tx-out'}">
                    ${tx.type === 'in' ? '+' : '−'} Rp ${formatRp(tx.amount)}
                </div>
            </div>
        `).join('');
    }

    // Toggle modals
    function showModal(id) {
        document.querySelectorAll('.wallet-modal').forEach(m => m.style.display = 'none');
        const modal = document.getElementById(id);
        if (modal) {
            modal.style.display = 'block';
            modal.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
    function hideModals() {
        document.querySelectorAll('.wallet-modal').forEach(m => m.style.display = 'none');
    }

    // Top Up
    const topUpBtn = document.getElementById('topUpBtn');
    if (topUpBtn) topUpBtn.addEventListener('click', () => showModal('topUpModal'));

    const cancelTopUp = document.getElementById('cancelTopUp');
    if (cancelTopUp) cancelTopUp.addEventListener('click', hideModals);

    // Chip selection
    let selectedTopUp = 0;
    document.querySelectorAll('.topup-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.topup-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            selectedTopUp = parseInt(chip.dataset.amount);
            const customInput = document.getElementById('customAmount');
            if (customInput) customInput.value = '';
        });
    });

    const confirmTopUp = document.getElementById('confirmTopUp');
    if (confirmTopUp) {
        confirmTopUp.addEventListener('click', () => {
            const customInput = document.getElementById('customAmount');
            const amount = customInput && customInput.value
                ? parseInt(customInput.value.replace(/\D/g, ''))
                : selectedTopUp;

            if (!amount || amount <= 0) {
                showMessage('Please select or enter an amount', 'warning');
                return;
            }

            balance += amount;
            updateBalanceDisplay();

            // Add to transaction list
            TRANSACTIONS.unshift({
                id: Date.now(), type: 'in', label: 'Top Up', icon: '↑',
                amount: amount, date: new Date().toLocaleString('id-ID', { timeZone: APP_TIMEZONE, day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' })
            });
            renderTransactions();
            hideModals();
            showMessage(`Successfully topped up Rp ${formatRp(amount)}`, 'success');

            // Reset
            selectedTopUp = 0;
            document.querySelectorAll('.topup-chip').forEach(c => c.classList.remove('active'));
            if (customInput) customInput.value = '';
        });
    }

    // Transfer
    const transferBtn = document.getElementById('transferBtn');
    if (transferBtn) transferBtn.addEventListener('click', () => showModal('transferModal'));

    const cancelTransfer = document.getElementById('cancelTransfer');
    if (cancelTransfer) cancelTransfer.addEventListener('click', hideModals);

    const confirmTransfer = document.getElementById('confirmTransfer');
    if (confirmTransfer) {
        confirmTransfer.addEventListener('click', () => {
            const recipient = document.getElementById('recipientId')?.value.trim();
            const amountStr = document.getElementById('transferAmount')?.value.trim();
            const note = document.getElementById('transferNote')?.value.trim();

            if (!recipient) { showMessage('Please enter a recipient', 'warning'); return; }
            const amount = parseInt(amountStr?.replace(/\D/g, '') || '0');
            if (!amount || amount <= 0) { showMessage('Please enter an amount', 'warning'); return; }
            if (amount > balance) { showMessage('Insufficient balance', 'error'); return; }

            balance -= amount;
            updateBalanceDisplay();

            TRANSACTIONS.unshift({
                id: Date.now(), type: 'out', label: `Transfer to ${recipient}${note ? ' - ' + note : ''}`, icon: '→',
                amount: amount, date: new Date().toLocaleString('id-ID', { timeZone: APP_TIMEZONE, day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' })
            });
            renderTransactions();
            hideModals();
            showMessage(`Rp ${formatRp(amount)} sent to ${recipient}`, 'success');

            // Reset fields
            if (document.getElementById('recipientId')) document.getElementById('recipientId').value = '';
            if (document.getElementById('transferAmount')) document.getElementById('transferAmount').value = '';
            if (document.getElementById('transferNote')) document.getElementById('transferNote').value = '';
        });
    }

    // Withdraw & History - just show a toast for the demo
    const withdrawBtn = document.getElementById('withdrawBtn');
    if (withdrawBtn) withdrawBtn.addEventListener('click', () => showMessage('Withdraw feature coming soon', 'info'));

    const historyBtn = document.getElementById('historyBtn');
    if (historyBtn) historyBtn.addEventListener('click', () => {
        const section = document.querySelector('.wallet-history');
        if (section) section.scrollIntoView({ behavior: 'smooth' });
    });

    // Init
    renderTransactions();
})();

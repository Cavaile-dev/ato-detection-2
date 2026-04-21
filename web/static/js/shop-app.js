/**
 * LUXE Shop Application
 * E-Commerce frontend with behavior logging integration
 */

// ===== Product Catalog =====
const PRODUCTS = [
    {
        id: 1, name: 'Aura Pro Headphones', category: 'audio',
        description: 'Wireless noise-cancelling headphones with spatial audio and 40hr battery life.',
        price: 2499000, emoji: '🎧',
        gradient: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)'
    },
    {
        id: 2, name: 'Chrono X Smartwatch', category: 'mobile',
        description: 'Advanced health monitoring, AMOLED display, titanium case with 7-day battery.',
        price: 4999000, emoji: '⌚',
        gradient: 'linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #2d1b69 100%)'
    },
    {
        id: 3, name: 'Nova Ultra Laptop 15"', category: 'computing',
        description: '12th Gen processor, 32GB RAM, 1TB SSD, 4K OLED touchscreen display.',
        price: 18999000, emoji: '💻',
        gradient: 'linear-gradient(135deg, #0d0d14 0%, #1c1c2e 50%, #1a2a3a 100%)'
    },
    {
        id: 4, name: 'Phantom X Smartphone', category: 'mobile',
        description: '200MP camera system, 120Hz display, 5000mAh battery, 5G connectivity.',
        price: 12499000, emoji: '📱',
        gradient: 'linear-gradient(135deg, #111118 0%, #1e1e30 50%, #2a1a3e 100%)'
    },
    {
        id: 5, name: 'Vortex MK Keyboard', category: 'accessories',
        description: 'Mechanical RGB keyboard with hot-swappable switches and aluminum frame.',
        price: 1899000, emoji: '⌨️',
        gradient: 'linear-gradient(135deg, #12121e 0%, #1a1a28 50%, #252535 100%)'
    },
    {
        id: 6, name: 'Pulse Mini Speaker', category: 'audio',
        description: 'Portable Bluetooth 5.3 speaker, 360° sound, waterproof IPX7, 18hr playtime.',
        price: 899000, emoji: '🔊',
        gradient: 'linear-gradient(135deg, #0e0e1a 0%, #1b1b2e 50%, #162040 100%)'
    },
    {
        id: 7, name: 'Apex Ergo Mouse', category: 'accessories',
        description: 'Ergonomic wireless mouse with 25K DPI sensor and customizable buttons.',
        price: 1299000, emoji: '🖱️',
        gradient: 'linear-gradient(135deg, #101018 0%, #1a1a28 50%, #202038 100%)'
    },
    {
        id: 8, name: 'Canvas Pro Tablet', category: 'computing',
        description: '12.9" Liquid Retina display, stylus support, 256GB storage, M2 chip.',
        price: 8999000, emoji: '📋',
        gradient: 'linear-gradient(135deg, #0c0c16 0%, #181828 50%, #221a30 100%)'
    }
];

// ===== Helpers =====
function formatPrice(price) {
    return 'Rp ' + price.toLocaleString('id-ID');
}

function showMessage(message, type) {
    const container = document.getElementById('messageContainer');
    if (!container) return;
    const div = document.createElement('div');
    div.className = `alert alert-${type}`;
    div.textContent = message;
    container.appendChild(div);
    setTimeout(() => div.remove(), 3500);
}

// ===== Cart Manager =====
class CartManager {
    constructor() {
        this.items = JSON.parse(sessionStorage.getItem('cart') || '[]');
    }

    save() {
        sessionStorage.setItem('cart', JSON.stringify(this.items));
        this.updateBadge();
    }

    add(productId) {
        const existing = this.items.find(i => i.id === productId);
        if (existing) {
            existing.qty += 1;
        } else {
            this.items.push({ id: productId, qty: 1 });
        }
        this.save();
    }

    remove(productId) {
        this.items = this.items.filter(i => i.id !== productId);
        this.save();
    }

    updateQty(productId, qty) {
        const item = this.items.find(i => i.id === productId);
        if (item) {
            item.qty = Math.max(1, qty);
            this.save();
        }
    }

    getProduct(productId) {
        return PRODUCTS.find(p => p.id === productId);
    }

    getTotal() {
        return this.items.reduce((sum, item) => {
            const product = this.getProduct(item.id);
            return sum + (product ? product.price * item.qty : 0);
        }, 0);
    }

    getTotalItems() {
        return this.items.reduce((sum, item) => sum + item.qty, 0);
    }

    clear() {
        this.items = [];
        this.save();
    }

    updateBadge() {
        const badges = document.querySelectorAll('#cartBadge, .cart-badge');
        const count = this.getTotalItems();
        badges.forEach(badge => {
            badge.textContent = count > 0 ? count : '';
            if (count > 0) {
                badge.style.animation = 'cartBounce 0.3s ease';
                setTimeout(() => badge.style.animation = '', 300);
            }
        });
    }
}

// ===== Shop Application =====
class ShopApp {
    constructor() {
        this.cart = new CartManager();
        this.behaviorLogger = new BehaviorLogger();
        this.sessionId = null;
        this.userId = null;
        this.username = null;
        this.submitInterval = null;
        this.currentFilter = 'all';

        this.init();
    }

    init() {
        // Auth check
        this.sessionId = sessionStorage.getItem('sessionId');
        this.userId = sessionStorage.getItem('userId');
        this.username = sessionStorage.getItem('username');

        if (!this.sessionId || !this.userId) {
            window.location.href = '/';
            return;
        }

        // Update nav
        const navUser = document.getElementById('navUsername');
        if (navUser) navUser.textContent = this.username;

        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) logoutBtn.addEventListener('click', () => this.logout());

        // Update cart badge
        this.cart.updateBadge();

        // Detect page and initialize
        const path = window.location.pathname;
        if (path === '/shop') this.initShop();
        else if (path === '/cart') this.initCart();
        else if (path === '/checkout') this.initCheckout();

        // Start behavior logging
        this.behaviorLogger.start();
        this.startPeriodicSubmission();
        
        // Handle browser close/exit
        this.setupExitHandler();
    }

    setupExitHandler() {
        // Track internal navigation
        document.addEventListener('click', (e) => {
            const a = e.target.closest('a');
            if (a && a.href && a.host === window.location.host) {
                window.isInternalNavigation = true;
            }
        });

        // Form submissions also count as internal navigation
        document.addEventListener('submit', () => {
            window.isInternalNavigation = true;
        });

        window.addEventListener('beforeunload', (e) => {
            if (!window.isInternalNavigation) {
                // Not an internal navigation, meaning user is leaving or closing tab
                this.behaviorLogger.stop();
                const events = this.behaviorLogger.getEvents();
                
                // Use sendBeacon for reliable delivery during page unload
                const payload = JSON.stringify({
                    session_id: this.sessionId,
                    events: events
                });
                navigator.sendBeacon('/api/v1/sessions/beacon_end', payload);
            }
        });
    }

    // ===== SHOP PAGE =====
    initShop() {
        this.renderProducts(PRODUCTS);

        // Category filters
        const filterProducts = () => {
            const searchTerm = (document.getElementById('searchBar')?.value || '').toLowerCase();
            const filtered = PRODUCTS.filter(p => {
                const matchesCategory = this.currentFilter === 'all' || p.category === this.currentFilter;
                const matchesSearch = p.name.toLowerCase().includes(searchTerm) || p.description.toLowerCase().includes(searchTerm);
                return matchesCategory && matchesSearch;
            });
            this.renderProducts(filtered);
        };

        const searchBar = document.getElementById('searchBar');
        if (searchBar) {
            searchBar.addEventListener('input', filterProducts);
        }

        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentFilter = btn.dataset.category;
                filterProducts();
            });
        });
    }

    renderProducts(products) {
        const grid = document.getElementById('productGrid');
        if (!grid) return;

        grid.innerHTML = products.map((p, i) => `
            <div class="product-card" style="animation-delay: ${i * 0.05}s" data-id="${p.id}">
                <div class="product-image-placeholder" style="background: ${p.gradient}">
                    ${p.emoji}
                </div>
                <div class="product-info">
                    <div class="product-category">${p.category}</div>
                    <div class="product-name">${p.name}</div>
                    <div class="product-desc">${p.description}</div>
                    <div class="product-footer">
                        <div class="product-price">
                            <span class="product-price-currency">Rp</span>
                            ${(p.price / 1000).toLocaleString('id-ID')}K
                        </div>
                        <button class="add-to-cart-btn" data-id="${p.id}" title="Add to cart">+</button>
                    </div>
                </div>
            </div>
        `).join('');

        // Add-to-cart handlers
        grid.querySelectorAll('.add-to-cart-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.id);
                this.cart.add(id);
                const product = PRODUCTS.find(p => p.id === id);
                showMessage(`${product.name} added to cart`, 'success');

                btn.classList.add('added');
                btn.textContent = '';
                setTimeout(() => {
                    btn.classList.remove('added');
                    btn.textContent = '+';
                }, 1200);
            });
        });
    }

    // ===== CART PAGE =====
    initCart() {
        this.renderCart();
    }

    renderCart() {
        const container = document.getElementById('cartContent');
        if (!container) return;

        if (this.cart.items.length === 0) {
            container.innerHTML = `
                <div class="cart-empty fade-up">
                    <div class="cart-empty-icon">🛒</div>
                    <h3>Your cart is empty</h3>
                    <p>Browse our collection and add something you like</p>
                    <a href="/shop" class="btn btn-primary">Continue Shopping</a>
                </div>
            `;
            return;
        }

        const itemsHTML = this.cart.items.map(item => {
            const p = this.cart.getProduct(item.id);
            if (!p) return '';
            return `
                <div class="cart-item fade-up" data-id="${p.id}">
                    <div class="cart-item-image-placeholder" style="background: ${p.gradient}; font-size: 36px;">
                        ${p.emoji}
                    </div>
                    <div class="cart-item-details">
                        <div class="cart-item-name">${p.name}</div>
                        <div class="cart-item-price">${formatPrice(p.price)}</div>
                        <div class="cart-item-actions">
                            <div class="quantity-control">
                                <button class="qty-btn" data-action="decrease" data-id="${p.id}">−</button>
                                <span class="qty-value">${item.qty}</span>
                                <button class="qty-btn" data-action="increase" data-id="${p.id}">+</button>
                            </div>
                            <button class="cart-item-remove" data-id="${p.id}">Remove</button>
                        </div>
                    </div>
                    <div class="cart-item-total">${formatPrice(p.price * item.qty)}</div>
                </div>
            `;
        }).join('');

        const subtotal = this.cart.getTotal();
        const shipping = subtotal > 5000000 ? 0 : 50000;
        const total = subtotal + shipping;

        container.innerHTML = `
            <div class="cart-layout fade-up">
                <div>
                    <div class="cart-items">${itemsHTML}</div>
                    <div style="margin-top: 20px;">
                        <a href="/shop" class="btn btn-secondary">← Continue Shopping</a>
                    </div>
                </div>
                <div class="cart-summary">
                    <h3>Order Summary</h3>
                    <div class="summary-row">
                        <span>Subtotal (${this.cart.getTotalItems()} items)</span>
                        <span>${formatPrice(subtotal)}</span>
                    </div>
                    <div class="summary-row">
                        <span>Shipping</span>
                        <span>${shipping === 0 ? 'Free' : formatPrice(shipping)}</span>
                    </div>
                    <div class="summary-row total">
                        <span>Total</span>
                        <span>${formatPrice(total)}</span>
                    </div>
                    <button class="btn btn-primary btn-block btn-lg" style="margin-top: 20px;" onclick="window.location.href='/checkout'">
                        Proceed to Checkout
                    </button>
                </div>
            </div>
        `;

        // Quantity handlers
        container.querySelectorAll('.qty-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const item = this.cart.items.find(i => i.id === id);
                if (!item) return;
                if (btn.dataset.action === 'increase') {
                    this.cart.updateQty(id, item.qty + 1);
                } else {
                    if (item.qty <= 1) {
                        this.cart.remove(id);
                    } else {
                        this.cart.updateQty(id, item.qty - 1);
                    }
                }
                this.renderCart();
            });
        });

        // Remove handlers
        container.querySelectorAll('.cart-item-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const p = this.cart.getProduct(id);
                this.cart.remove(id);
                showMessage(`${p.name} removed from cart`, 'info');
                this.renderCart();
            });
        });
    }

    // ===== CHECKOUT PAGE =====
    initCheckout() {
        if (this.cart.items.length === 0) {
            window.location.href = '/cart';
            return;
        }
        this.renderCheckout();
    }

    renderCheckout() {
        const container = document.getElementById('checkoutContent');
        if (!container) return;

        const subtotal = this.cart.getTotal();
        const shipping = subtotal > 5000000 ? 0 : 50000;
        const total = subtotal + shipping;

        const orderItemsHTML = this.cart.items.map(item => {
            const p = this.cart.getProduct(item.id);
            if (!p) return '';
            return `
                <div class="checkout-item">
                    <div class="checkout-item-img-placeholder" style="background: ${p.gradient}; font-size: 20px;">
                        ${p.emoji}
                    </div>
                    <div class="checkout-item-info">
                        <div class="checkout-item-name">${p.name}</div>
                        <div class="checkout-item-qty">Qty: ${item.qty}</div>
                    </div>
                    <div class="checkout-item-price">${formatPrice(p.price * item.qty)}</div>
                </div>
            `;
        }).join('');

        container.innerHTML = `
            <div>
                <div class="checkout-section">
                    <h3>Shipping Information</h3>
                    <div class="form-group">
                        <label for="fullName">Full Name</label>
                        <input type="text" id="fullName" class="form-control" placeholder="Enter your full name" required>
                    </div>
                    <div class="form-group">
                        <label for="address">Address</label>
                        <input type="text" id="address" class="form-control" placeholder="Street address" required>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="city">City</label>
                            <input type="text" id="city" class="form-control" placeholder="City" required>
                        </div>
                        <div class="form-group">
                            <label for="postalCode">Postal Code</label>
                            <input type="text" id="postalCode" class="form-control" placeholder="10110" required>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="phone">Phone Number</label>
                        <input type="tel" id="phone" class="form-control" placeholder="+62 812 3456 7890" required>
                    </div>
                </div>

                <div class="checkout-section">
                    <h3>Payment Method</h3>
                    <div class="form-group">
                        <label for="cardNumber">Card Number</label>
                        <input type="text" id="cardNumber" class="form-control" placeholder="0000 0000 0000 0000" maxlength="19" required>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="expiry">Expiry Date</label>
                            <input type="text" id="expiry" class="form-control" placeholder="MM/YY" maxlength="5" required>
                        </div>
                        <div class="form-group">
                            <label for="cvv">CVV</label>
                            <input type="text" id="cvv" class="form-control" placeholder="123" maxlength="4" required>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <div class="cart-summary">
                    <h3>Order Summary</h3>
                    ${orderItemsHTML}
                    <div class="summary-row" style="margin-top: 16px;">
                        <span>Subtotal</span>
                        <span>${formatPrice(subtotal)}</span>
                    </div>
                    <div class="summary-row">
                        <span>Shipping</span>
                        <span>${shipping === 0 ? 'Free' : formatPrice(shipping)}</span>
                    </div>
                    <div class="summary-row total">
                        <span>Total</span>
                        <span>${formatPrice(total)}</span>
                    </div>
                    <button id="payBtn" class="btn btn-primary btn-block btn-lg" style="margin-top: 20px;">
                        Pay ${formatPrice(total)}
                    </button>
                    <a href="/cart" class="btn btn-secondary btn-block" style="margin-top: 8px;">← Back to Cart</a>
                </div>
            </div>
        `;

        // Card number formatting
        const cardInput = document.getElementById('cardNumber');
        if (cardInput) {
            cardInput.addEventListener('input', (e) => {
                let val = e.target.value.replace(/\D/g, '').substring(0, 16);
                e.target.value = val.replace(/(\d{4})(?=\d)/g, '$1 ');
            });
        }

        // Expiry formatting
        const expiryInput = document.getElementById('expiry');
        if (expiryInput) {
            expiryInput.addEventListener('input', (e) => {
                let val = e.target.value.replace(/\D/g, '').substring(0, 4);
                if (val.length >= 2) val = val.substring(0, 2) + '/' + val.substring(2);
                e.target.value = val;
            });
        }

        // Pay button
        const payBtn = document.getElementById('payBtn');
        if (payBtn) {
            payBtn.addEventListener('click', () => this.handlePayment());
        }
    }

    async handlePayment() {
        const payBtn = document.getElementById('payBtn');

        // Simple validation
        const fields = ['fullName', 'address', 'city', 'postalCode', 'phone', 'cardNumber', 'expiry', 'cvv'];
        for (const fieldId of fields) {
            const field = document.getElementById(fieldId);
            if (!field || !field.value.trim()) {
                showMessage('Please fill in all fields', 'warning');
                if (field) field.focus();
                return;
            }
        }

        payBtn.textContent = 'Processing...';
        payBtn.disabled = true;

        // Simulate payment processing
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Submit remaining events
        await this.submitEvents();

        // Show success
        const overlay = document.getElementById('successOverlay');
        if (overlay) {
            overlay.innerHTML = `
                <div class="success-overlay">
                    <div class="success-card">
                        <div class="success-icon">✓</div>
                        <h2>Payment Successful!</h2>
                        <p>Thank you for your purchase. Your order has been confirmed and will be shipped shortly.</p>
                        <button class="btn btn-primary btn-lg" onclick="window.location.href='/shop'">Continue Shopping</button>
                    </div>
                </div>
            `;
        }

        // Clear cart
        this.cart.clear();
    }

    // ===== Behavior Logger Integration =====
    async submitEvents() {
        const events = this.behaviorLogger.getEvents();
        if (events.length === 0) return;

        try {
            await fetch('/api/v1/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    events: events
                })
            });
            this.behaviorLogger.clearEvents();
        } catch (error) {
            console.error('Error submitting events:', error);
        }
    }

    startPeriodicSubmission() {
        this.submitInterval = setInterval(() => {
            if (this.behaviorLogger.getEventCount() > 0) {
                this.submitEvents();
            }
        }, 10000);
    }

    async logout() {
        try {
            await this.submitEvents();
            await fetch(`/api/v1/sessions/${this.sessionId}/end`, { method: 'POST' });
        } catch (e) {
            console.error('Logout error:', e);
        }

        this.behaviorLogger.stop();
        clearInterval(this.submitInterval);
        sessionStorage.clear();
        window.location.href = '/';
    }
}

// ===== Initialize =====
document.addEventListener('DOMContentLoaded', () => {
    new ShopApp();
});


    /* ════════════════════════════════
       VARIABLE DECLARATIONS
    ════════════════════════════════ */
   let selectedVariant = null;  // ✅ Will be { id, name, price, stock, image_url }
let currentPrice = null;
let currentStock = null;
let currentImage = null;
let qty = 1;

function updatePriceDisplay(price, specialPrice, discountPct) {
    const priceEl    = document.getElementById('currentPrice');
    const origEl     = document.getElementById('originalPrice');
    const badgeEl    = document.getElementById('discountBadge');
    if (!priceEl) return;
    if (specialPrice && specialPrice > 0 && specialPrice < price) {
        priceEl.textContent = '₱' + Number(specialPrice).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (origEl)  { origEl.textContent = '₱' + Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); origEl.style.display = ''; }
        if (badgeEl) { badgeEl.textContent = discountPct + '% off'; badgeEl.style.display = ''; }
    } else {
        priceEl.textContent = '₱' + Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (origEl)  origEl.style.display = 'none';
        if (badgeEl) badgeEl.style.display = 'none';
    }
}

function updateGalleryStockTag() {
    const galleryStockTag = document.getElementById('galleryStockTag');
    if (!galleryStockTag) return;

    if (!null || currentStock <= 0) {
        galleryStockTag.innerHTML = `
            <span class="gallery-stock-badge is-out">
                <span class="gallery-stock-badge__icon" aria-hidden="true"><i class="ri-close-circle-line"></i></span>
                <span class="gallery-stock-badge__text">Out of stock</span>
            </span>`;
        galleryStockTag.style.display = 'block';
        return;
    }

    if (currentStock <= 10) {
        const critical = currentStock <= 3 ? ' is-critical' : '';
        const label = currentStock === 1
            ? `Only <span class="gallery-stock-badge__count">1</span> left`
            : `Only <span class="gallery-stock-badge__count">${currentStock}</span> left`;
        galleryStockTag.innerHTML = `
            <span class="gallery-stock-badge is-low${critical}">
                <span class="gallery-stock-badge__icon" aria-hidden="true"><i class="ri-flashlight-line"></i></span>
                <span class="gallery-stock-badge__text">${label}</span>
            </span>`;
        galleryStockTag.style.display = 'block';
        return;
    }

    galleryStockTag.innerHTML = '';
    galleryStockTag.style.display = 'none';
}

function syncPurchaseActions() {
    const addToCartBtn = document.getElementById('addToCartBtn');
    const buyNowBtn = document.getElementById('buyNowBtn');
    const stockDisplay = document.getElementById('stockDisplay');
    const isAvailable = null;

    if (stockDisplay) {
        stockDisplay.textContent = currentStock > 0 ? `${currentStock} available` : 'Out of stock';
    }

    // Update button text and state based on stock
    const outOfStockText = '<i class="ri-close-circle-line"></i> Out of Stock';
    const addToBasketText = '<i class="ri-shopping-bag-line"></i> Add to Basket';
    const buyNowText = '<i class="ri-secure-payment-line"></i> Buy Now';
    const closedText = '<i class="ri-close-circle-line"></i> Store Closed';

    function setCtaState(btn, { html, disabled, oos, closed }) {
        if (!btn) return;
        btn.innerHTML = html;
        btn.disabled = !!disabled;
        btn.classList.toggle('is-oos', !!oos);
        btn.classList.toggle('is-closed', !!closed);
        btn.style.opacity = '';
        btn.style.cursor = '';
        btn.setAttribute('aria-disabled', oos || closed ? 'true' : 'false');
    }

    if (!storeIsOpen) {
        setCtaState(addToCartBtn, { html: closedText, disabled: true, closed: true });
        setCtaState(buyNowBtn, { html: closedText, disabled: true, closed: true });
    } else if (currentStock <= 0) {
        // Greyed out but still clickable — handlers show a toast
        setCtaState(addToCartBtn, { html: outOfStockText, disabled: false, oos: true });
        setCtaState(buyNowBtn, { html: outOfStockText, disabled: false, oos: true });
    } else {
        setCtaState(addToCartBtn, { html: addToBasketText, disabled: false });
        setCtaState(buyNowBtn, { html: buyNowText, disabled: false });
    }

    // Only allow quantity adjustment if in stock
    const qtyPlus = document.getElementById('qtyPlus');
    const qtyMinus = document.getElementById('qtyMinus');
    if (qtyPlus) {
        qtyPlus.disabled = currentStock <= 0 || qty >= currentStock;
    }
    if (qtyMinus) {
        qtyMinus.disabled = qty <= 1 || currentStock <= 0;
    }

    updateGalleryStockTag();
}
 
// Store main product data
const mainProduct = {
    id: null,
    name: null,
    price: null,
    special_price: null,
    effective_price: null,
    discount_pct: null,
    stock: null,
    store_id: null,
    store_name: null,
    image_url: "null",
     main_category_id: null,
    main_category_name: null,
    store_category_id: null,
    store_category_name: null,
    category_path: null
};
 
/* Variant data from server */
const variants = [
    
        
        {
            id: null,
            name: null,
            price: null,
            special_price: null,
            effective_price: null,
            discount_pct: null,
            stock: null,
            image_url: null,
            attributes: null
        },
        
    
];

/* Per-variant rating aggregates  (key "main" = standard product) */
const variantRatings = null;
const overallRating = { avg: null, count: null };
let productReviewsCache = null;
 

    /* ════════════════════════════════
       GALLERY
    ════════════════════════════════ */
  const images = [
    
        
            { 
                src: null, 
                alt: null,
                filename: null,
                is_primary: null
            },
        
    
];
 
let currentImageIndex = 0;
let activeImages = [...images];

function updateGalleryControls() {
    const prev = document.getElementById('galleryPrev');
    const next = document.getElementById('galleryNext');
    const hasMultipleImages = activeImages.length > 1;

    if (prev) {
        prev.style.display = hasMultipleImages ? 'flex' : 'none';
        prev.disabled = !hasMultipleImages || currentImageIndex === 0;
    }

    if (next) {
        next.style.display = hasMultipleImages ? 'flex' : 'none';
        next.disabled = !hasMultipleImages || currentImageIndex === activeImages.length - 1;
    }
}

function renderGalleryThumbnails() {
    const thumbs = document.getElementById('galleryThumbs');
    if (!thumbs) return;

    if (!activeImages.length) {
        thumbs.innerHTML = `
            <div class="gallery-thumb active">
                <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:24px;color:rgba(107,76,59,0.15);">
                    <i class="ri-image-line"></i>
                </div>
            </div>
        `;
        return;
    }

    thumbs.innerHTML = activeImages.map((image, index) => `
        <div class="gallery-thumb ${index === currentImageIndex ? 'active' : ''}"
             data-index="${index}"
             onclick="setMainImage(${index})">
            <img src="${image.src}" alt="${image.alt || mainProduct.name}"
                 onerror="this.parentElement.style.background='linear-gradient(145deg,#f5ede6,#ede3d8)'">
        </div>
    `).join('');
}

function setGalleryImages(nextImages) {
    activeImages = nextImages && nextImages.length ? [...nextImages] : [];
    currentImageIndex = 0;
    renderGalleryThumbnails();

    const mainImg = document.getElementById('mainImage');
    if (mainImg && activeImages[0]) {
        mainImg.style.opacity = '0';
        setTimeout(() => {
            mainImg.src = activeImages[0].src;
            mainImg.alt = activeImages[0].alt || mainProduct.name;
            mainImg.style.opacity = '1';
        }, 150);
    }

    updateGalleryControls();
}
 

    function selectVariant(btn) {
    console.group('🔄 SELECT VARIANT');
    
    // Remove active class from all variant buttons
    document.querySelectorAll('.variant-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    const variantId = btn.dataset.variantId;
    const variantPrice = parseFloat(btn.dataset.variantPrice);
    const variantStock = parseInt(btn.dataset.variantStock);
    const variantImage = btn.dataset.variantImage;
    const variantName = btn.dataset.variantName;
    
    console.log('Button clicked:', { variantId, variantName, variantPrice, variantStock });
    
    // ═══════════════════════════════════════════════════════════
    // MAIN PRODUCT SELECTED
    // ═══════════════════════════════════════════════════════════
    if (variantId === 'main') {
        console.log('✅ Main product selected');
        
        selectedVariant = null;  // ✅ CLEAR VARIANT
        currentPrice = mainProduct.effective_price || mainProduct.price;
        currentStock = mainProduct.stock;
        
        // Update price display
        updatePriceDisplay(mainProduct.price, mainProduct.special_price, mainProduct.discount_pct);
        
        // Update rating display for main product
        updateRatingDisplay('main');
        
        // Restore the full product gallery
        setGalleryImages(images);
        
    } else {
        // ═══════════════════════════════════════════════════════════
        // VARIANT SELECTED
        // ═══════════════════════════════════════════════════════════
        console.log('✅ Variant selected:', variantId);
        
        // Find the matching variant to get special_price
        const variantObj = variants.find(v => v.id === parseInt(variantId)) || {};

        // ✅ STORE VARIANT DATA CORRECTLY
        selectedVariant = {
            id: parseInt(variantId),
            name: variantName,
            price: variantPrice,
            special_price: variantObj.special_price || null,
            effective_price: variantObj.effective_price || variantPrice,
            discount_pct: variantObj.discount_pct || null,
            stock: variantStock,
            image_url: variantImage && variantImage !== 'null' ? variantImage : null
        };
        
        console.log('✅ Stored selectedVariant:', selectedVariant);
        
        currentPrice = selectedVariant.effective_price;
        currentStock = variantStock;
        
        // Update rating display for this variant
        updateRatingDisplay(variantId);
        
        // Update price display
        updatePriceDisplay(variantPrice, selectedVariant.special_price, selectedVariant.discount_pct);
        
        const fallbackImage = variantImage && variantImage !== 'null' && variantImage !== ''
            ? variantImage
            : (mainProduct.image_url || (images[0] ? images[0].src : ''));

        setGalleryImages(fallbackImage ? [{
            src: fallbackImage,
            alt: variantName
        }] : []);
    }
    
    // ═══════════════════════════════════════════════════════════
    // UPDATE QUANTITY BASED ON NEW STOCK
    // ═══════════════════════════════════════════════════════════
    const qtyDisplay = document.getElementById('qtyDisplay');
    let currentQty = parseInt(qtyDisplay.textContent);
    if (currentQty > currentStock) {
        qty = Math.max(currentStock, 1);
        qtyDisplay.textContent = qty;
    }
    syncPurchaseActions();
    
    // ═══════════════════════════════════════════════════════════
    // UPDATE TOTAL
    // ═══════════════════════════════════════════════════════════
    updateTotal();
    updateWishlistHeartUI();
    
    console.groupEnd();
}

    /* ════════════════════════════════
       RATING DISPLAY UPDATE
    ════════════════════════════════ */
    function updateRatingDisplay(variantKey) {
        // Standard ("main") = only ratings with variant_id NULL.
        // Variant keys = only that variant's ratings. Never mix.
        const key = String(variantKey);
        const data = variantRatings[key] || { avg: 0, count: 0 };
        const avg = Number(data.avg) || 0;
        const count = Number(data.count) || 0;
        const fullStars = Math.floor(avg);
        const hasHalf = (avg - fullStars) >= 0.3;
        const emptyStars = 5 - fullStars - (hasHalf ? 1 : 0);

        let starsHtml = '';
        for (let i = 0; i < fullStars; i++) starsHtml += '<i class="ri-star-fill"></i>';
        if (hasHalf) starsHtml += '<i class="ri-star-half-fill"></i>';
        for (let i = 0; i < emptyStars; i++) starsHtml += '<i class="ri-star-line"></i>';

        const ratingRow = document.querySelector('.rating-row');
        if (!ratingRow) return;
        ratingRow.querySelector('.stars').innerHTML = starsHtml;
        ratingRow.querySelector('.rating-score').textContent = avg;
        const countEl = ratingRow.querySelector('.rating-count');
        countEl.textContent = '(' + count + ' review' + (count !== 1 ? 's' : '') + ')';
    }

function closeReviewsModal() {
    const modal = document.getElementById('productReviewsModal');
    if (!modal) return;
    modal.classList.remove('active');
    document.body.style.overflow = '';
}

function formatReviewDate(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-PH', { year: 'numeric', month: 'short', day: 'numeric' });
}

function esc(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function buildReviewStars(rating, { allowHalf = false } = {}) {
    const raw = Math.max(0, Math.min(5, Number(rating) || 0));
    const full = allowHalf ? Math.floor(raw) : Math.round(raw);
    const hasHalf = allowHalf && (raw - full) >= 0.3 && full < 5;
    const empty = 5 - full - (hasHalf ? 1 : 0);
    let stars = '';
    for (let i = 0; i < full; i += 1) stars += '<i class="ri-star-fill"></i>';
    if (hasHalf) stars += '<i class="ri-star-half-fill"></i>';
    for (let i = 0; i < empty; i += 1) stars += '<i class="ri-star-line"></i>';
    return stars;
}

function getCurrentVariantFilter() {
    // 'main' = Standard only; number = that variant; null = no filter (legacy)
    if (selectedVariant && selectedVariant.id) return Number(selectedVariant.id);
    return 'main';
}

function buildRatingBreakdown(ratings) {
    const counts = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 };
    ratings.forEach(r => {
        const star = Math.max(1, Math.min(5, Math.round(Number(r.rating) || 0)));
        counts[star] += 1;
    });
    const total = ratings.length || 1;
    return [5, 4, 3, 2, 1].map(star => {
        const pct = Math.round((counts[star] / total) * 100);
        return `
            <div class="ratings-bar-row">
                <span class="ratings-bar-star">${star}</span>
                <div class="ratings-bar-track" aria-hidden="true">
                    <div class="ratings-bar-fill" style="width:${pct}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

function renderReviewsInModal(payload) {
    const body = document.getElementById('reviewsModalBody');
    if (!body) return;
    const activeVariantId = getCurrentVariantFilter();
    const allRatings = Array.isArray(payload?.ratings) ? payload.ratings : [];
    let ratings;
    if (activeVariantId === 'main') {
        ratings = allRatings.filter(r => r.variant_id == null || r.variant_id === '');
    } else if (activeVariantId) {
        ratings = allRatings.filter(r => Number(r.variant_id) === activeVariantId);
    } else {
        ratings = allRatings;
    }

    const count = ratings.length;
    const avg = count
        ? (ratings.reduce((sum, r) => sum + (Number(r.rating) || 0), 0) / count)
        : 0;
    const avgLabel = count ? (Math.round(avg * 10) / 10).toFixed(1).replace(/\.0$/, '') : '0';

    const variantNote = activeVariantId && activeVariantId !== 'main' && selectedVariant
        ? `<p class="reviews-modal-note">Showing reviews for <strong>${esc(selectedVariant.name)}</strong>.</p>`
        : (activeVariantId === 'main'
            ? `<p class="reviews-modal-note">Showing reviews for <strong>Standard</strong>.</p>`
            : '');

    const overview = `
        <div class="ratings-overview">
            <div class="ratings-avg-block">
                <div class="ratings-avg-label">Average user rating</div>
                <div class="ratings-avg-value">${esc(avgLabel)} <span>/ 5</span></div>
                <div class="ratings-avg-stars" aria-label="${esc(avgLabel)} out of 5">
                    ${buildReviewStars(avg, { allowHalf: true })}
                </div>
            </div>
            <div class="ratings-breakdown">
                <div class="ratings-breakdown-label">Rating breakdown</div>
                <div class="ratings-breakdown-rows">
                    ${buildRatingBreakdown(ratings)}
                </div>
            </div>
        </div>
    `;

    if (!ratings.length) {
        body.innerHTML = `${variantNote}${overview}<div class="reviews-empty"><i class="ri-chat-smile-3-line"></i>No reviews yet for this selection.</div>`;
        return;
    }

    const rows = ratings.map(r => {
        const name = r.customer_name || 'Anonymous';
        const comment = (r.comment && String(r.comment).trim())
            ? r.comment
            : 'No written comment.';
        return `
            <article class="review-row">
                <div class="review-stars" aria-label="${esc(String(r.rating || 0))} out of 5 stars">${buildReviewStars(r.rating)}</div>
                <p class="review-comment">${esc(comment)}</p>
                <p class="review-by">— Reviewed by ${esc(name)}</p>
            </article>
        `;
    }).join('');

    body.innerHTML = `${variantNote}${overview}<div class="reviews-list">${rows}</div>`;
}

async function openReviewsModal() {
    const modal = document.getElementById('productReviewsModal');
    const body = document.getElementById('reviewsModalBody');
    if (!modal || !body) return;

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    body.innerHTML = '<div class="reviews-empty"><i class="ri-loader-4-line"></i>Loading reviews...</div>';

    try {
        if (!productReviewsCache) {
            const res = await fetch(`/api/products/${mainProduct.id}/ratings?page=1&per_page=50`);
            productReviewsCache = await res.json();
        }
        renderReviewsInModal(productReviewsCache || {});
    } catch (error) {
        body.innerHTML = '<div class="reviews-empty"><i class="ri-error-warning-line"></i>Unable to load reviews right now.</div>';
    }
}

    /* ════════════════════════════════
       GALLERY FUNCTIONS
    ════════════════════════════════ */
    function setMainImage(index) {    
    if (index < 0 || index >= activeImages.length) return;
    currentImageIndex = index;
 
    const mainImg = document.getElementById('mainImage');
    if (mainImg && activeImages[index]) {
        mainImg.style.opacity = '0';
        setTimeout(() => {
            mainImg.src = activeImages[index].src;
            mainImg.alt = activeImages[index].alt || mainProduct.name;
            mainImg.style.opacity = '1';
        }, 150);
    }
 
    // Update thumbs
    document.querySelectorAll('.gallery-thumb').forEach((t, i) => {
        t.classList.toggle('active', i === index);
    });
 
    updateGalleryControls();
}
 
function shiftImage(dir) {
    setMainImage(currentImageIndex + dir);
}
 
// Keyboard navigation
document.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowLeft') shiftImage(-1);
    if (e.key === 'ArrowRight') shiftImage(1);
});

    /* ════════════════════════════════
       GALLERY ACCORDION
    ════════════════════════════════ */
   function toggleGalleryAccordion(id) {
    const item = document.getElementById(id);
    item.classList.toggle('open');
}
    /* ════════════════════════════════
       QUANTITY
    ════════════════════════════════ */
    function changeQty(delta) {
    const newQty = Math.max(1, Math.min(currentStock, qty + delta));
    if (newQty === qty) return;
    
    qty = newQty;
    document.getElementById('qtyDisplay').textContent = qty;
    syncPurchaseActions();
    updateTotal();
}
 
    /* ════════════════════════════════
       DELIVERY FIELD
    ════════════════════════════════ */
   
function updateDeliveryField() {
    const val = document.getElementById('deliveryInput').value;
    document.getElementById('deliveryClear').style.display = val ? 'flex' : 'none';
    document.getElementById('deliveryField').style.borderColor = val ? 'var(--deep-rose)' : '';
}
 
function clearDelivery() {
    document.getElementById('deliveryInput').value = '';
    document.getElementById('deliveryClear').style.display = 'none';
    document.getElementById('deliveryField').style.borderColor = '';
}
 

    /* ════════════════════════════════
       ADD-ONS / YOU MIGHT ALSO LIKE
    ════════════════════════════════ */
    const selectedAddons = new Map(); // id -> {id, name, price, image_url, quantity, stock}
    // YMAL structured add-on cards — independent from dropdown (quantities can stack)
    const selectedYmalAddonOptions = new Map(); // optionId -> {id, name, price, quantity, stock}
let addonInfoTarget = null;

function getAddonStock(cardOrId) {
    const card = typeof cardOrId === 'object'
        ? cardOrId
        : document.querySelector(`.addon-card[data-id="${cardOrId}"]`);
    if (!card) return 0;
    const stock = parseInt(card.dataset.stock, 10);
    return Number.isFinite(stock) ? Math.max(0, stock) : 0;
}

function toggleAddon(card) {
    if (!card) return;

    const id = parseInt(card.dataset.id, 10);
    const price = parseFloat(card.dataset.price);
    const name = card.dataset.name || 'This item';
    const stock = getAddonStock(card);
    const imageEl = card.querySelector('img');
    const imageUrl = imageEl ? imageEl.src : '';
    const slide = card.closest('.addon-slide');

    if (card.classList.contains('is-oos') || stock <= 0) {
        showToast(`"${name}" is out of stock.`, 'error');
        return;
    }

    if (card.classList.contains('selected')) {
        card.classList.remove('selected');
        if (slide) slide.classList.remove('is-selected');
        selectedAddons.delete(id);
        const qtyEl = document.querySelector(`[data-qty-for="${id}"]`);
        if (qtyEl) qtyEl.textContent = '1';
    } else {
        card.classList.add('selected');
        if (slide) slide.classList.add('is-selected');
        selectedAddons.set(id, { id, name, price, image_url: imageUrl, quantity: 1, stock });
        const qtyEl = document.querySelector(`[data-qty-for="${id}"]`);
        if (qtyEl) qtyEl.textContent = '1';
    }
    updateTotal();
}

function changeAddonQty(addonId, delta) {
    const addon = selectedAddons.get(addonId);
    if (!addon) return;

    const stock = getAddonStock(addonId);
    const current = addon.quantity || 1;
    const next = current + delta;

    if (delta > 0 && next > stock) {
        const name = addon.name || 'This item';
        if (stock <= 0) {
            showToast(`"${name}" is out of stock.`, 'error');
        } else {
            showToast(
                `Only ${stock} available for "${name}". You can't add more than the available stock.`,
                'error'
            );
        }
        // Snap UI back to max available
        addon.quantity = Math.max(1, Math.min(current, stock));
        selectedAddons.set(addonId, addon);
        const qtyEl = document.querySelector(`[data-qty-for="${addonId}"]`);
        if (qtyEl) qtyEl.textContent = String(addon.quantity);
        updateTotal();
        return;
    }

    addon.quantity = Math.max(1, next);
    addon.stock = stock;
    selectedAddons.set(addonId, addon);

    const qtyEl = document.querySelector(`[data-qty-for="${addonId}"]`);
    if (qtyEl) qtyEl.textContent = String(addon.quantity);
    updateTotal();
}

function getActiveYmalTrack() {
    const panel = document.querySelector('.ymal-panel.active');
    if (!panel) {
        return document.getElementById('ymalAddonsGrid')
            || document.getElementById('ymalFlowersGrid')
            || document.getElementById('addonsGrid');
    }
    return panel.querySelector('.addons-grid');
}

function getActiveYmalNav() {
    const panel = document.querySelector('.ymal-panel.active');
    if (!panel) {
        return {
            prev: document.getElementById('addonsPrev'),
            next: document.getElementById('addonsNext'),
        };
    }
    return {
        prev: panel.querySelector('[data-ymal-prev]'),
        next: panel.querySelector('[data-ymal-next]'),
    };
}

function switchYmalTab(tab) {
    const section = document.getElementById('ymalSection');
    if (!section) return;

    section.querySelectorAll('.ymal-tab').forEach(btn => {
        const isActive = (btn.id === 'ymalTabAddons' && tab === 'addons')
            || (btn.id === 'ymalTabFlowers' && tab === 'flowers');
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    section.querySelectorAll('.ymal-panel').forEach(panel => {
        const isActive = panel.dataset.ymalPanel === tab;
        panel.classList.toggle('active', isActive);
        if (isActive) panel.removeAttribute('hidden');
        else panel.setAttribute('hidden', '');
    });

    updateAddonsNavState();
}

function getAddonsScrollStep() {
    const track = getActiveYmalTrack();
    if (!track) return 160;
    const slide = track.querySelector('.addon-slide:not([style*="display: none"])')
        || track.querySelector('.addon-slide');
    if (!slide) return 160;
    const styles = window.getComputedStyle(track);
    const gap = parseFloat(styles.columnGap || styles.gap) || 0;
    return slide.getBoundingClientRect().width + gap;
}

function scrollAddons(direction) {
    const track = getActiveYmalTrack();
    if (!track) return;
    const amount = getAddonsScrollStep();
    track.scrollBy({ left: direction * amount, behavior: 'smooth' });
    setTimeout(updateAddonsNavState, 320);
}

function updateAddonsNavState() {
    const track = getActiveYmalTrack();
    const { prev, next } = getActiveYmalNav();
    if (!track || !prev || !next) return;

    const maxScroll = track.scrollWidth - track.clientWidth;
    const atStart = track.scrollLeft <= 2;
    const atEnd = track.scrollLeft >= maxScroll - 2;
    const noScroll = maxScroll <= 2;
    prev.disabled = atStart || noScroll;
    next.disabled = atEnd || noScroll;
    prev.style.visibility = noScroll ? 'hidden' : '';
    next.style.visibility = noScroll ? 'hidden' : '';
}

function initAddonsCarousel() {
    const tracks = Array.from(document.querySelectorAll('[data-ymal-grid]'));
    if (!tracks.length) {
        const legacy = document.getElementById('addonsGrid');
        if (legacy) tracks.push(legacy);
    }
    if (!tracks.length) return;

    updateAddonsNavState();
    tracks.forEach(track => {
        track.addEventListener('scroll', updateAddonsNavState, { passive: true });
    });
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(updateAddonsNavState, 100);
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAddonsCarousel);
} else {
    initAddonsCarousel();
}

function filterAddons(cat, btn) {
    document.querySelectorAll('.addon-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    document.querySelectorAll('.addon-card').forEach(card => {
        const cardCat = card.dataset.cat || 'other';
        const slide = card.closest('.addon-slide');
        const show = (cat === 'all' || cardCat === cat);
        if (slide) slide.style.display = show ? '' : 'none';
        else card.style.display = show ? '' : 'none';
    });
    updateAddonsNavState();
}
    
    function showAddonInfo(addonId) {
    const card = document.querySelector(`.addon-card[data-id="${addonId}"]`);
    if (!card) return;
    addonInfoTarget = card;
    const stock = getAddonStock(card);
    const isOos = stock <= 0 || card.classList.contains('is-oos');

    document.getElementById('addonInfoTitle').textContent = card.dataset.name;
    document.getElementById('addonInfoBody').innerHTML = `
        <div style="display:flex;gap:1rem;align-items:flex-start;">
            <div style="width:90px;height:90px;border-radius:var(--radius-md);overflow:hidden;flex-shrink:0;background:linear-gradient(145deg,#f5ede6,#ede3d8);position:relative;">
                ${card.querySelector('img') ? `<img src="${card.querySelector('img').src}" style="width:100%;height:100%;object-fit:cover;${isOos ? 'filter:grayscale(0.5);opacity:0.7;' : ''}">` : ''}
            </div>
            <div>
                <div style="font-family:var(--font-display);font-size:20px;margin-bottom:.4rem;">${card.dataset.name}</div>
                <div style="font-family:var(--font-display);font-size:22px;color:var(--deep-rose);font-weight:600;">₱${parseFloat(card.dataset.price).toFixed(2)}</div>
                <div style="font-size:13px;color:var(--muted);margin-top:.5rem;">
                    ${isOos
                        ? '<span style="color:#9b1c1c;font-weight:600;">Out of stock</span>'
                        : `Perfect add-on to complement your order. <span style="color:var(--charcoal);">${stock} available</span>`}
                </div>
            </div>
        </div>`;

    const addBtn = document.getElementById('addonInfoAddBtn');
    if (isOos) {
        addBtn.disabled = true;
        addBtn.style.opacity = '0.5';
        addBtn.style.cursor = 'not-allowed';
        addBtn.innerHTML = '<i class="ri-close-circle-line"></i> Out of Stock';
        addBtn.onclick = null;
    } else {
        addBtn.disabled = false;
        addBtn.style.opacity = '1';
        addBtn.style.cursor = '';
        addBtn.innerHTML = '<i class="ri-shopping-bag-line"></i> Add to Basket';
        addBtn.onclick = async () => {
            if (!addonInfoTarget) return;
            const btn = document.getElementById('addonInfoAddBtn');
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i>';
            btn.disabled = true;

            try {
                await addSingleAddonToCart(addonInfoTarget);
                document.getElementById('addonInfoModal').classList.remove('active');
                document.body.style.overflow = '';
            } catch (error) {
                console.error('❌ Failed to add add-on from modal:', error);
                showToast('Could not add item. Please try again.', 'error');
            } finally {
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        };
    }

    document.getElementById('addonInfoModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}
 

    /* ════════════════════════════════
       DELIVERY DATES & TIMES
    ════════════════════════════════ */
   let selectedDate = null;
   let selectedTime = null;
   let storeIsOpen = true;
   const storeSchedule = null;

   function formatStoreTimeLabel(value) {
       if (!value || typeof value !== 'string' || !value.includes(':')) return value || '';
       const [hRaw, mRaw] = value.split(':');
       let h = parseInt(hRaw, 10);
       const m = String(mRaw || '00').padStart(2, '0');
       if (!Number.isFinite(h)) return value;
       const suffix = h >= 12 ? 'PM' : 'AM';
       h = h % 12 || 12;
       return `${h}:${m} ${suffix}`;
   }

   document.querySelectorAll('[data-store-time]').forEach((el) => {
       el.textContent = formatStoreTimeLabel(el.getAttribute('data-store-time'));
   });
   
   // Get current time in Philippine timezone (UTC+8)
   function getPhilippineTime() {
       const now = new Date();
       const phTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Manila' }));
       return phTime;
   }
   
   // Get today's date in Philippine timezone
   function getPhilippineTodayStr() {
       const phTime = getPhilippineTime();
       return phTime.toISOString().split('T')[0];
   }
   
   // Time slots - will be fetched from store schedule API
   let timeSlots = [];
   let gotCustomTimeSlots = false;
   let lastSlotBlockReason = null;
   
   const STORE_ID = null;
   
   // Fetch time slots from store schedule API for a given date
   async function fetchTimeSlots(dateStr) {
       try {
           const resp = await fetch(`/api/store/${STORE_ID}/time-slots?date=${dateStr}`);
           const data = await resp.json();
           lastSlotBlockReason = data && data.block_reason ? data.block_reason : null;
           if (data.success && data.time_slots && data.time_slots.length > 0) {
               timeSlots = data.time_slots;
               gotCustomTimeSlots = true;
           } else {
               timeSlots = [];
               gotCustomTimeSlots = !!(data && data.has_schedule);
           }
           return data;
       } catch (e) {
           timeSlots = [];
           gotCustomTimeSlots = false;
           lastSlotBlockReason = 'no_schedule';
           return null;
       }
   }
 
function formatDateISO(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, '0');
    const d = String(dateObj.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function isStoreOpenOnDate(dateObj) {
    if (!storeSchedule || !Array.isArray(storeSchedule.schedules) || storeSchedule.schedules.length === 0) {
        return false;
    }
    const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'Asia/Manila' }).toLowerCase();
    return storeSchedule.schedules.some(entry =>
        Array.isArray(entry.days) && entry.days.map(d => String(d).toLowerCase()).includes(dayName)
    );
}

function getDateLimitWindow() {
    const today = getPhilippineTime();
    today.setHours(0, 0, 0, 0);
    const maxDate = new Date(today);
    maxDate.setDate(maxDate.getDate() + 14);
    return { today, maxDate };
}

function initHiddenCalendarPicker() {
    const input = document.getElementById('deliveryDatePicker');
    if (!input || typeof flatpickr !== 'function') return;
    const { today, maxDate } = getDateLimitWindow();

    flatpickr(input, {
        dateFormat: 'Y-m-d',
        minDate: today,
        maxDate: maxDate,
        disable: [
            function(date) {
                return !isStoreOpenOnDate(date);
            }
        ],
        clickOpens: false,
        onChange: function(selectedDates, dateStr) {
            if (!dateStr) return;
            selectDateByString(dateStr, true);
        }
    });
}

function openCalendarPicker() {
    const input = document.getElementById('deliveryDatePicker');
    if (!input || !input._flatpickr) return;
    input._flatpickr.open();
}

function getDefaultOpenDate() {
    const { today, maxDate } = getDateLimitWindow();
    for (let i = 0; i <= 14; i++) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        if (d <= maxDate && isStoreOpenOnDate(d)) return d;
    }
    return null;
}

function updateCalendarBlockLabel(dateStr = null) {
    const cal = document.querySelector('.date-option[data-role="calendar"]');
    if (!cal) return;

    if (!dateStr) {
        cal.innerHTML = `<div class="date-option-cal"><i class="ri-calendar-2-line"></i><span>CALENDAR</span></div>`;
        return;
    }

    const picked = new Date(`${dateStr}T00:00:00`);
    const month = picked.toLocaleDateString('en-US', { month: 'short', timeZone: 'Asia/Manila' }).toUpperCase();
    const day = String(picked.getDate()).padStart(2, '0');
    cal.innerHTML = `
        <div class="date-option-month">${month}</div>
        <div class="date-option-day">${day}</div>
        <div class="date-option-label">PICKED</div>
    `;
}

function selectDateByString(dateStr, fromCalendar = false) {
    const target = document.querySelector(`.date-option[data-date="${dateStr}"]`);
    document.querySelectorAll('.date-option').forEach(d => d.classList.remove('selected'));
    if (target) {
        target.classList.add('selected');
        updateCalendarBlockLabel(null);
    } else if (fromCalendar) {
        const cal = document.querySelector('.date-option[data-role="calendar"]');
        if (cal) cal.classList.add('selected');
        updateCalendarBlockLabel(dateStr);
    }

    selectedDate = dateStr;
    selectedTime = null;
    const container = document.getElementById('timeOptions');
    container.innerHTML = '<p style="color: var(--slate); font-size: 0.9rem;"><i class="ri-loader-4-line ri-spin"></i> Loading time slots...</p>';

    fetchTimeSlots(selectedDate).then(data => {
        if (data && !data.is_open && data.has_schedule) {
            container.innerHTML = '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-close-circle-line"></i> Store is closed on this day</p>';
            storeIsOpen = false;
            syncPurchaseActions();
            return;
        }
        storeIsOpen = true;
        buildTimeOptions();
        saveDeliveryPreferences();
        syncPurchaseActions();
    });
}

function buildDateOptions() {
    const container = document.getElementById('dateOptions');
    if (!container) return;
    const { today } = getDateLimitWindow();
    const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
    const days = ['SUN','MON','TUE','WED','THU','FRI','SAT'];

    container.innerHTML = '';
    for (let i = 0; i < 3; i++) {
        const d = new Date(today);
        d.setDate(today.getDate() + i);
        const dateStr = formatDateISO(d);
        const isOpen = isStoreOpenOnDate(d);
        const div = document.createElement('div');
        div.className = 'date-option';
        div.dataset.date = dateStr;
        div.style.opacity = isOpen ? '1' : '0.45';
        div.style.cursor = isOpen ? 'pointer' : 'not-allowed';
        if (!isOpen) div.style.pointerEvents = 'none';
        const label = i === 0 ? 'TODAY' : i === 1 ? 'TOMORROW' : days[d.getDay()];
        div.innerHTML = `
            <div class="date-option-month">${months[d.getMonth()]}</div>
            <div class="date-option-day">${String(d.getDate()).padStart(2,'0')}</div>
            <div class="date-option-label">${isOpen ? label : 'CLOSED'}</div>`;
        if (isOpen) div.addEventListener('click', () => selectDateByString(dateStr, false));
        container.appendChild(div);
    }

    const calDiv = document.createElement('div');
    calDiv.className = 'date-option';
    calDiv.dataset.role = 'calendar';
    calDiv.innerHTML = `<div class="date-option-cal"><i class="ri-calendar-2-line"></i><span>CALENDAR</span></div>`;
    calDiv.addEventListener('click', openCalendarPicker);
    container.appendChild(calDiv);

    const firstOpen = getDefaultOpenDate();
    if (firstOpen) {
        selectDateByString(formatDateISO(firstOpen), false);
    } else {
        const container = document.getElementById('timeOptions');
        container.innerHTML = '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-close-circle-line"></i> Store has no open delivery days in the next 14 days.</p>';
        storeIsOpen = false;
        syncPurchaseActions();
    }
}

// Build time slot options
function buildTimeOptions() {
    const container = document.getElementById('timeOptions');
    container.innerHTML = '';
    
    if (!selectedDate) {
        container.innerHTML = '<p style="color: var(--slate); font-size: 0.9rem;">Select a date first</p>';
        return;
    }

    function emptySlotMessage(reason) {
        if (reason === 'no_schedule') {
            return '<p style="color: var(--orange); font-size: 0.9rem;"><i class="ri-alert-line"></i> This store has not set delivery hours yet.</p>';
        }
        if (reason === 'order_cutoff') {
            return '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-time-line"></i> Same-day ordering is closed. Please choose another open day.</p>';
        }
        if (reason === 'lead_time') {
            return '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-time-line"></i> Remaining slots are inside the store prep window. Please choose a later slot or another date.</p>';
        }
        if (reason === 'slots_passed') {
            return '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-time-line"></i> All delivery slots for today have passed. Please select another date.</p>';
        }
        if (reason === 'closed') {
            return '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.</p>';
        }
        return '<p style="color: var(--terracotta); font-size: 0.9rem;"><i class="ri-time-line"></i> No delivery slots available for this date.</p>';
    }

    if (!timeSlots.length) {
        container.innerHTML = emptySlotMessage(lastSlotBlockReason);
        selectedTime = null;
        storeIsOpen = lastSlotBlockReason !== 'closed' && lastSlotBlockReason !== 'no_schedule';
        syncPurchaseActions();
        return;
    }

    let firstAvailable = null;
    timeSlots.forEach((slot) => {
        const div = document.createElement('div');
        div.className = 'time-option';
        div.dataset.time = slot.value;
        div.innerHTML = `<i class="ri-time-line"></i> ${slot.label}`;
        if (!firstAvailable) firstAvailable = div;
        div.addEventListener('click', () => selectTime(div));
        container.appendChild(div);
    });

    if (firstAvailable) {
        firstAvailable.classList.add('selected');
        selectedTime = firstAvailable.dataset.time;
        storeIsOpen = true;
        syncPurchaseActions();
    }
}

function selectTime(el) {
    document.querySelectorAll('.time-option').forEach(t => t.classList.remove('selected'));
    el.classList.add('selected');
    selectedTime = el.dataset.time;
    saveDeliveryPreferences();
}

// Save delivery preferences to sessionStorage (survives page navigation)
function saveDeliveryPreferences() {
    const prefs = {
        selectedDate: selectedDate,
        selectedTime: selectedTime,
        savedAt: new Date().toISOString()
    };
    sessionStorage.setItem('deliveryPreferences', JSON.stringify(prefs));
    console.log('✅ Saved delivery preferences:', prefs);
}

    /* ════════════════════════════════
       TOTAL CALCULATION
    ════════════════════════════════ */
    
function updateTotal() {
    let total = currentPrice * qty;
    selectedAddons.forEach(addon => {
        total += addon.price * (addon.quantity || 1);
    });
    total += getStructuredAddonsTotal() * qty;
    document.getElementById('orderTotal').textContent = '₱' + Number(total).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function getDropdownAddonOptionIds() {
    const ids = [];
    document.querySelectorAll('.structured-addon-select').forEach(sel => {
        const val = sel.value;
        if (val) ids.push(parseInt(val, 10));
    });
    return ids.filter(n => !isNaN(n));
}

/** Merge dropdown (+1 each) and YMAL quantities for the same option id. */
function getStructuredAddonSelectionMap() {
    const map = new Map();
    document.querySelectorAll('.structured-addon-select').forEach(sel => {
        const opt = sel.options[sel.selectedIndex];
        if (!opt || !opt.value) return;
        const oid = parseInt(opt.value, 10);
        if (isNaN(oid)) return;
        const price = parseFloat(opt.dataset.price || '0');
        const stock = parseInt(opt.dataset.stock, 10);
        const existing = map.get(oid);
        map.set(oid, {
            id: oid,
            name: opt.dataset.name || (existing && existing.name) || '',
            price: isNaN(price) ? ((existing && existing.price) || 0) : price,
            stock: Number.isFinite(stock) ? stock : (existing ? existing.stock : 0),
            quantity: (existing ? existing.quantity : 0) + 1,
            image_url: opt.dataset.image || (existing && existing.image_url) || '',
            group_name: opt.dataset.groupName || (existing && existing.group_name) || '',
        });
    });
    selectedYmalAddonOptions.forEach((item, oid) => {
        const existing = map.get(oid);
        const qty = Math.max(1, parseInt(item.quantity, 10) || 1);
        map.set(oid, {
            id: oid,
            name: item.name || (existing && existing.name) || '',
            price: existing ? existing.price : (parseFloat(item.price) || 0),
            stock: item.stock != null ? item.stock : (existing ? existing.stock : 0),
            quantity: (existing ? existing.quantity : 0) + qty,
            image_url: item.image_url || (existing && existing.image_url) || '',
            group_name: item.group_name || (existing && existing.group_name) || '',
        });
    });
    return map;
}

function getSelectedAddonOptionIds() {
    return Array.from(getStructuredAddonSelectionMap().values()).map(item => ({
        addon_option_id: item.id,
        quantity: item.quantity,
    }));
}

function getStructuredAddonsForCart() {
    return Array.from(getStructuredAddonSelectionMap().values()).map(item => ({
        id: item.id,
        addon_option_id: item.id,
        name: item.name,
        price: item.price,
        stock: item.stock != null ? item.stock : 0,
        quantity: item.quantity,
        image_url: item.image_url || '',
        group_name: item.group_name || '',
    }));
}

function getStructuredAddonsTotal() {
    let sum = 0;
    getStructuredAddonSelectionMap().forEach(item => {
        sum += (parseFloat(item.price) || 0) * (item.quantity || 1);
    });
    return sum;
}

function openAddonImageZoom(imageUrl, altText) {
    if (!imageUrl) return;
    const modal = document.getElementById('addonImageZoomModal');
    const img = document.getElementById('addonImageZoomImg');
    if (!modal || !img) return;
    img.src = imageUrl;
    img.alt = altText || 'Add-on preview';
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeAddonImageZoom() {
    const modal = document.getElementById('addonImageZoomModal');
    const img = document.getElementById('addonImageZoomImg');
    if (modal) modal.classList.remove('active');
    if (img) {
        img.removeAttribute('src');
        img.alt = '';
    }
    if (!document.getElementById('addonInfoModal')?.classList.contains('active')) {
        document.body.style.overflow = '';
    }
}

function closeAllAddonDropdowns(exceptDd) {
    document.querySelectorAll('.addon-dd.is-open').forEach(dd => {
        if (exceptDd && dd === exceptDd) return;
        dd.classList.remove('is-open');
        const trigger = dd.querySelector('.addon-dd-trigger');
        const menu = dd.querySelector('.addon-dd-menu');
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
        if (menu) menu.hidden = true;
    });
}

function syncAddonDropdownTrigger(dd, selectEl) {
    if (!dd || !selectEl) return;
    const opt = selectEl.options[selectEl.selectedIndex];
    const textEl = dd.querySelector('.addon-dd-trigger-text');
    const label = (!opt || !opt.value)
        ? 'Do not add'
        : ((opt.textContent || '').trim() || (opt.dataset.name || 'Add-on'));
    if (textEl) textEl.textContent = label;

    dd.querySelectorAll('.addon-dd-option').forEach(btn => {
        const selected = (btn.dataset.value || '') === (selectEl.value || '');
        btn.classList.toggle('is-selected', selected);
        btn.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
}

function selectAddonDropdownOption(dd, optionBtn) {
    if (!dd || !optionBtn) return;
    const val = optionBtn.dataset.value || '';
    const stock = parseInt(optionBtn.dataset.stock, 10);
    const safeStock = Number.isFinite(stock) ? Math.max(0, stock) : 0;
    if (val && (optionBtn.disabled || optionBtn.classList.contains('is-oos') || safeStock <= 0)) {
        const name = optionBtn.dataset.name || 'Add-on';
        showToast(`"${name}" is out of stock.`, 'error');
        return;
    }
    const selectEl = dd.querySelector('.structured-addon-select');
    if (!selectEl) return;
    selectEl.value = val;
    syncAddonDropdownTrigger(dd, selectEl);
    closeAllAddonDropdowns();
    onStructuredAddonChange(selectEl);
}

function initAddonDropdowns() {
    document.querySelectorAll('.addon-dd').forEach(dd => {
        const trigger = dd.querySelector('.addon-dd-trigger');
        const menu = dd.querySelector('.addon-dd-menu');
        const selectEl = dd.querySelector('.structured-addon-select');
        if (!trigger || !menu || !selectEl) return;

        syncAddonDropdownTrigger(dd, selectEl);

        trigger.addEventListener('click', () => {
            const willOpen = !dd.classList.contains('is-open');
            closeAllAddonDropdowns(willOpen ? dd : null);
            if (willOpen) {
                dd.classList.add('is-open');
                trigger.setAttribute('aria-expanded', 'true');
                menu.hidden = false;
            } else {
                dd.classList.remove('is-open');
                trigger.setAttribute('aria-expanded', 'false');
                menu.hidden = true;
            }
        });

        menu.querySelectorAll('.addon-dd-option').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const zoomImg = e.target.closest('.addon-dd-opt-thumb.is-zoomable');
                if (zoomImg && zoomImg.dataset.zoomSrc) {
                    e.preventDefault();
                    e.stopPropagation();
                    openAddonImageZoom(zoomImg.dataset.zoomSrc, zoomImg.dataset.zoomName || '');
                    return;
                }
                selectAddonDropdownOption(dd, btn);
            });
        });
    });

    document.querySelectorAll('.structured-addon-preview').forEach(preview => {
        preview.addEventListener('click', () => {
            if (!preview.classList.contains('has-image')) return;
            const img = preview.querySelector('img.addon-preview-photo');
            if (img && img.getAttribute('src')) {
                openAddonImageZoom(img.getAttribute('src'), img.alt || '');
            }
        });
    });
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.addon-dd')) closeAllAddonDropdowns();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAddonImageZoom();
        closeAllAddonDropdowns();
    }
});

function updateStructuredAddonPreview(selectEl) {
    if (!selectEl) return;
    const groupId = selectEl.dataset.groupId;
    const preview = document.getElementById(`addon-preview-${groupId}`);
    const img = document.getElementById(`addon-preview-img-${groupId}`);
    if (!preview || !img) return;

    const opt = selectEl.options[selectEl.selectedIndex];
    const imageUrl = opt && opt.value ? (opt.dataset.image || '') : '';
    if (imageUrl) {
        img.src = imageUrl;
        img.alt = opt.dataset.name || 'Add-on';
        preview.classList.add('has-image');
    } else {
        img.removeAttribute('src');
        img.alt = '';
        preview.classList.remove('has-image');
    }

    const dd = selectEl.closest('.addon-dd');
    if (dd) syncAddonDropdownTrigger(dd, selectEl);
}

function onStructuredAddonChange(selectEl) {
    updateStructuredAddonPreview(selectEl);
    updateTotal();
}

function getYmalAddonCard(optionId) {
    return document.querySelector(`.addon-card[data-ymal-type="addon_option"][data-option-id="${optionId}"]`);
}

function syncYmalAddonQtyDisplay(optionId, quantity) {
    const qtyEl = document.querySelector(`[data-ymal-qty-for="${optionId}"]`);
    if (qtyEl) qtyEl.textContent = String(Math.max(1, quantity || 1));
}

function selectYmalAddonOption(card) {
    if (!card) return;
    const optionId = parseInt(card.dataset.optionId, 10);
    if (isNaN(optionId)) return;

    const name = card.dataset.name || 'Add-on';
    const price = parseFloat(card.dataset.price || '0');
    const stock = parseInt(card.dataset.stock, 10);
    const slide = card.closest('.addon-slide');
    const safeStock = Number.isFinite(stock) ? Math.max(0, stock) : 0;

    if (card.classList.contains('is-oos') || safeStock <= 0) {
        showToast(`"${name}" is out of stock.`, 'error');
        return;
    }

    if (selectedYmalAddonOptions.has(optionId)) {
        selectedYmalAddonOptions.delete(optionId);
        card.classList.remove('selected');
        if (slide) slide.classList.remove('is-selected');
        syncYmalAddonQtyDisplay(optionId, 1);
    } else {
        const dropdownTaken = getDropdownAddonOptionIds().includes(optionId) ? 1 : 0;
        if (dropdownTaken >= safeStock) {
            showToast(`Only ${safeStock} available for "${name}".`, 'error');
            return;
        }
        selectedYmalAddonOptions.set(optionId, {
            id: optionId,
            name,
            price: isNaN(price) ? 0 : price,
            quantity: 1,
            stock: safeStock,
            image_url: (card.querySelector('img') && card.querySelector('img').src) || '',
            group_name: card.dataset.groupName || card.dataset.group || '',
        });
        card.classList.add('selected');
        if (slide) slide.classList.add('is-selected');
        syncYmalAddonQtyDisplay(optionId, 1);
    }
    updateTotal();
}

function changeYmalAddonQty(optionId, delta) {
    const card = getYmalAddonCard(optionId);
    if (!card) return;
    const name = card.dataset.name || 'Add-on';
    const stock = parseInt(card.dataset.stock, 10);
    const safeStock = Number.isFinite(stock) ? Math.max(0, stock) : 0;
    if (card.classList.contains('is-oos') || safeStock <= 0) {
        showToast(`"${name}" is out of stock.`, 'error');
        return;
    }

    let item = selectedYmalAddonOptions.get(optionId);
    if (!item) {
        if (delta > 0) {
            selectYmalAddonOption(card);
            item = selectedYmalAddonOptions.get(optionId);
        }
        if (!item) return;
        if (delta <= 1) {
            updateTotal();
            return;
        }
        // continue to apply remaining delta after selecting
        delta -= 1;
        if (delta === 0) {
            updateTotal();
            return;
        }
    }

    const dropdownTaken = getDropdownAddonOptionIds().includes(optionId) ? 1 : 0;
    const maxYmal = Math.max(0, safeStock - dropdownTaken);
    const current = item.quantity || 1;
    const next = current + delta;

    if (next <= 0) {
        selectedYmalAddonOptions.delete(optionId);
        card.classList.remove('selected');
        const slide = card.closest('.addon-slide');
        if (slide) slide.classList.remove('is-selected');
        syncYmalAddonQtyDisplay(optionId, 1);
        updateTotal();
        return;
    }

    if (next > maxYmal) {
        const name = item.name || 'This add-on';
        if (maxYmal <= 0) {
            showToast(`Only ${safeStock} available for "${name}".`, 'error');
        } else {
            showToast(
                `Only ${safeStock} available for "${name}". You can't add more than the available stock.`,
                'error'
            );
        }
        item.quantity = Math.max(1, Math.min(current, maxYmal));
        selectedYmalAddonOptions.set(optionId, item);
        syncYmalAddonQtyDisplay(optionId, item.quantity);
        updateTotal();
        return;
    }

    item.quantity = next;
    selectedYmalAddonOptions.set(optionId, item);
    card.classList.add('selected');
    const slide = card.closest('.addon-slide');
    if (slide) slide.classList.add('is-selected');
    syncYmalAddonQtyDisplay(optionId, item.quantity);
    updateTotal();
}

function buildAddonCartItem(addon) {
    return {
        id: addon.id,
        name: addon.name,
        price: addon.price,
        store_id: mainProduct.store_id,
        store_name: mainProduct.store_name,
        image_url: addon.image_url || '',
        quantity: addon.quantity || 1
    };
}

async function addSingleAddonToCart(addonCard) {
    if (typeof window.addToCart !== 'function') {
        throw new Error('addToCart function not found');
    }

    const id = parseInt(addonCard.dataset.id, 10);
    const stock = getAddonStock(addonCard);
    if (stock <= 0) {
        showToast('This item is out of stock.', 'error');
        throw new Error('Out of stock');
    }

    const selected = selectedAddons.get(id);
    let quantity = selected ? (selected.quantity || 1) : 1;
    if (quantity > stock) {
        showToast(
            `Only ${stock} available. You can't add more than the available stock.`,
            'error'
        );
        throw new Error('Exceeds stock');
    }

    const addon = {
        id,
        name: addonCard.dataset.name,
        price: parseFloat(addonCard.dataset.price),
        image_url: addonCard.querySelector('img') ? addonCard.querySelector('img').src : '',
        quantity
    };

    const cartItem = buildAddonCartItem(addon);
    await window.addToCart(cartItem);
    showToast(`${addon.name} added to basket`);
}
    /* ════════════════════════════════
       CART FUNCTIONS - MATCHING STORE_DETAIL.HTML
    ════════════════════════════════ */
   

    // In product_details.html, update addToCartWithVariant function:
async function addToCartWithVariant() {
    const button = event.currentTarget;
    if (currentStock <= 0) {
        showToast('This selection is out of stock.', 'error');
        return;
    }
    const originalHtml = button.innerHTML;
    
    button.innerHTML = '<i class="ri-loader-4-line ri-spin"></i>';
    button.disabled = true;
    
    try {
        const structuredAddons = getStructuredAddonsForCart();
        for (const sa of structuredAddons) {
            const safeStock = Number.isFinite(sa.stock) ? sa.stock : 0;
            if (safeStock <= 0) {
                showToast(`Add-on "${sa.name}" is out of stock.`, 'error');
                return;
            }
            if ((sa.quantity || 1) > safeStock) {
                showToast(`Only ${safeStock} available for add-on "${sa.name}".`, 'error');
                return;
            }
        }

        let product;
        
        if (selectedVariant) {
            // Variant selected - send main product ID as id, variant_id separately
            product = {
                id: mainProduct.id,                    // ✅ Main product ID (required)
                variant_id: selectedVariant.id,        // ✅ Variant ID (required)
                name: selectedVariant.name + ' ' + mainProduct.name,  // Combined name for display
                price: selectedVariant.price,          // ✅ Variant price
                store_id: mainProduct.store_id,
                store_name: mainProduct.store_name,
                image_url: selectedVariant.image_url || mainProduct.image_url,
                quantity: qty,
                addon_option_ids: getSelectedAddonOptionIds(),
                addons: getStructuredAddonsForCart(),
            };
            console.log('🔄 Adding VARIANT to cart:', product);
        } else {
            // Main product selected - no variant_id
            product = {
                id: mainProduct.id,                    // ✅ Main product ID only
                name: mainProduct.name,
                price: mainProduct.price,
                store_id: mainProduct.store_id,
                store_name: mainProduct.store_name,
                image_url: mainProduct.image_url,
                quantity: qty,
                addon_option_ids: getSelectedAddonOptionIds(),
                addons: getStructuredAddonsForCart(),
            };
            console.log('🔄 Adding MAIN PRODUCT to cart:', product);
        }
        
        if (typeof window.addToCart !== 'function') {
            console.error('❌ addToCart function not found');
            showToast('Error adding to cart. Please try again.', 'error');
            return;
        }

        const added = await window.addToCart(product);
        if (!added) return;

        if (selectedAddons.size > 0) {
            for (const addon of selectedAddons.values()) {
                const stock = getAddonStock(addon.id);
                const qty = addon.quantity || 1;
                if (stock <= 0) {
                    showToast(`"${addon.name}" is out of stock.`, 'error');
                    return;
                }
                if (qty > stock) {
                    showToast(
                        `Only ${stock} available for "${addon.name}". Please lower the quantity.`,
                        'error'
                    );
                    return;
                }
                const addonItem = buildAddonCartItem(addon);
                const addonAdded = await window.addToCart(addonItem);
                if (!addonAdded) return;
            }
        }
        // Success toast is shown by addToCart itself
    } catch (error) {
        console.error('❌ Error adding to cart:', error);
        if (typeof showCartActionError === 'function') {
            showCartActionError(error.message || error);
        } else {
            showToast('Network error — please try again', 'error');
        }
    } finally {
        setTimeout(() => {
            button.innerHTML = originalHtml;
            button.disabled = false;
        }, 500);
    }
}

    /* ════════════════════════════════
       BUY NOW
    ════════════════════════════════ */
   function buyNow() {
    if (currentStock <= 0) {
        showToast('Please select an in-stock option first.', 'error');
        return;
    }

    const structuredAddons = getStructuredAddonsForCart();
    for (const sa of structuredAddons) {
        const safeStock = Number.isFinite(sa.stock) ? sa.stock : 0;
        if (safeStock <= 0) {
            showToast(`Add-on "${sa.name}" is out of stock.`, 'error');
            return;
        }
        if ((sa.quantity || 1) > safeStock) {
            showToast(`Only ${safeStock} available for add-on "${sa.name}".`, 'error');
            return;
        }
    }

    // Build item data from current selection + You might also like add-ons
    const addons = [];
    for (const addon of selectedAddons.values()) {
        const stock = getAddonStock(addon.id);
        const qty = addon.quantity || 1;
        if (stock <= 0) {
            showToast(`"${addon.name}" is out of stock and was removed from your selection.`, 'error');
            continue;
        }
        if (qty > stock) {
            showToast(
                `Only ${stock} available for "${addon.name}". Please lower the quantity.`,
                'error'
            );
            return;
        }
        addons.push({
            product_id: addon.id,
            quantity: qty,
            price: addon.price,
            name: addon.name,
            image_url: addon.image_url || '',
        });
    }

    const item = {
        product_id: mainProduct.id,
        variant_id: selectedVariant ? selectedVariant.id : null,
        quantity: qty,
        price: currentPrice,
        name: selectedVariant
            ? selectedVariant.name + ' ' + mainProduct.name
            : mainProduct.name,
        store_name: mainProduct.store_name,
        image_url: selectedVariant && selectedVariant.image_url
            ? selectedVariant.image_url
            : mainProduct.image_url,
        addons: addons,
        addon_option_ids: getSelectedAddonOptionIds(),
    };

    console.log('🛍️ Buy Now Item:', item);
    console.log('   - product_id:', item.product_id, typeof item.product_id);
    console.log('   - variant_id:', item.variant_id, typeof item.variant_id);
    console.log('   - quantity:', item.quantity, typeof item.quantity);
    console.log('   - addons:', addons.length);

    // Open checkout modal in buy-now mode (defined in base.html)
    buyNowDirect(item);
}
   /* ════════════════════════════════
   VIEW PRODUCT
════════════════════════════════ */
 
function viewProduct(productId) {
    window.location.href = "null".replace('0', productId);
}

/* ════════════════════════════════
   WISHLIST
════════════════════════════════ */
const WISHLIST_LOGGED_IN = null;
const WISHLIST_LOGIN_URL = null;
/** Set of keys: 'main' or 'v:<id>' currently wishlisted for this product */
const wishlistKeys = new Set();

function currentWishlistKey() {
    return selectedVariant && selectedVariant.id ? `v:${selectedVariant.id}` : 'main';
}

function updateWishlistHeartUI() {
    const btn = document.getElementById('wishlistHeartBtn');
    const icon = document.getElementById('wishlistHeartIcon');
    const tip = document.getElementById('wishlistHeartTip');
    if (!btn || !icon) return;
    const active = wishlistKeys.has(currentWishlistKey());
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-label', active ? 'Remove from wishlist' : 'Add to wishlist');
    icon.className = active ? 'ri-heart-fill' : 'ri-heart-line';
    if (tip) tip.textContent = active ? 'Remove from wishlist' : 'Add to wishlist';
}

async function loadWishlistStateForProduct() {
    if (!WISHLIST_LOGGED_IN) {
        updateWishlistHeartUI();
        return;
    }
    try {
        const r = await fetch(`/api/account/wishlist/product/${mainProduct.id}`);
        if (!r.ok) return;
        const data = await r.json();
        wishlistKeys.clear();
        (data.variant_ids || []).forEach(vid => {
            if (vid === null || vid === undefined) wishlistKeys.add('main');
            else wishlistKeys.add(`v:${vid}`);
        });
        updateWishlistHeartUI();
    } catch (err) {
        console.warn('Wishlist state load failed', err);
    }
}

async function toggleProductWishlist(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!WISHLIST_LOGGED_IN) {
        window.location.href = WISHLIST_LOGIN_URL + '?next=' + encodeURIComponent(window.location.pathname);
        return;
    }
    const btn = document.getElementById('wishlistHeartBtn');
    if (btn) btn.disabled = true;
    try {
        const payload = {
            product_id: mainProduct.id,
            variant_id: selectedVariant ? selectedVariant.id : null,
        };
        const r = await fetch('/api/account/wishlist/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await r.json().catch(() => ({}));
        if (r.status === 401) {
            window.location.href = WISHLIST_LOGIN_URL;
            return;
        }
        if (!r.ok) {
            if (typeof showToast === 'function') showToast(data.error || 'Could not update wishlist', 'error');
            return;
        }
        const key = currentWishlistKey();
        if (data.wished) wishlistKeys.add(key);
        else wishlistKeys.delete(key);
        updateWishlistHeartUI();
        if (typeof showToast === 'function') {
            showToast(data.message || (data.wished ? 'Added to wishlist' : 'Removed from wishlist'));
        }
    } catch (err) {
        console.error(err);
        if (typeof showToast === 'function') showToast('Could not update wishlist', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

/* ════════════════════════════════
   INITIALIZATION
════════════════════════════════ */
 
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Product details page loaded');
    
    initHiddenCalendarPicker();
    buildDateOptions();
    setGalleryImages(images);
    updateTotal();
    updateRatingDisplay('main');  // Show main product rating by default
    
    // Ensure main product button is active
    const mainBtn = document.querySelector('.variant-btn[data-variant-id="main"]');
    if (mainBtn && !mainBtn.classList.contains('active')) {
        mainBtn.classList.add('active');
        selectedVariant = null;
        console.log('✅ Main product button activated');
    }
    
    syncPurchaseActions();
    initAddonDropdowns();
    loadWishlistStateForProduct();
    
    // Verify addToCart exists
    if (typeof window.addToCart !== 'function') {
        console.warn('⚠️ addToCart function not found in global scope');
    }

    const reviewsModal = document.getElementById('productReviewsModal');
    if (reviewsModal) {
        reviewsModal.addEventListener('click', function(e) {
            if (e.target === reviewsModal) closeReviewsModal();
        });
    }
});

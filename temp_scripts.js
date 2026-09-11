
    /* Device capability flags:
       - perf-lite: drop expensive glass blur (never on iPhone/iPad)
       - fx-lite: skip heavy decorative FX on low-end Android only
       Desktop PCs and iPhone always keep stores auto-carousel. */
    (function () {
        try {
            var ua = navigator.userAgent || '';
            var isIOS = /iPhone|iPad|iPod/i.test(ua) ||
                (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
            var isAndroid = /Android/i.test(ua);
            var isMobileUa = /Mobile|Android|webOS|BlackBerry|IEMobile|Opera Mini/i.test(ua);
            // Real computer browsers (Windows/macOS/Linux desktop)
            var isDesktopComputer = !isIOS && !isAndroid && !isMobileUa;
            var c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
            var mem = typeof navigator.deviceMemory === 'number' ? navigator.deviceMemory : null;
            var lowMem = mem !== null && mem <= 4;
            var highMem = mem !== null && mem >= 6;
            var saveData = !!(c && c.saveData);
            var slowNet = !!(c && (c.effectiveType === 'slow-2g' || c.effectiveType === '2g'));
            var reduceMotion = false;
            try {
                reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            } catch (e1) {}

            // Blur degrade for constrained non-Apple clients only
            if (!isIOS && !isDesktopComputer && (lowMem || saveData || slowNet)) {
                document.documentElement.classList.add('perf-lite');
            }

            // Carousel / rich UI: always on for desktop computers + iPhone/iPad
            var richFx = isDesktopComputer || isIOS || (isAndroid && highMem);
            // Decorative petals only (respect OS reduce-motion)
            var decorFx = richFx && !reduceMotion;

            // fx-lite only for low-end / typical Android phones — never desktop/iPhone
            if (!richFx) {
                document.documentElement.classList.add('fx-lite');
            }
            if (reduceMotion) {
                document.documentElement.classList.add('reduce-motion');
            }

            window.__eflowersRichFx = !!richFx;   // stores auto-carousel
            window.__eflowersDecorFx = !!decorFx; // petals / hero florals motion
        } catch (e) {
            window.__eflowersRichFx = true;
            window.__eflowersDecorFx = true;
        }
    })();
    
/* --- SCRIPT BREAK --- */
[{"addon_groups": [], "archived_at": null, "archived_by": null, "avg_rating": 0.0, "can_deliver_to_customer": true, "category_display": "Bouquets", "category_path": "Bouquets", "created_at": "2026-09-08T16:41:35.443704", "delivery_block_reason": null, "description": "Blue Customized Bouquet", "discount_pct": null, "effective_price": 449.98, "has_addons": false, "has_variants": false, "has_ymal_addons": false, "id": 252, "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788885694/e-flowers/products/784717902_1318624534660281_776_885693_58030477.jpg", "images": [{"created_at": "2026-09-08T16:41:35.451321", "filename": "cloudinary_e-flowers/products/784717902_1318624534660281_776_885693_58030477.jpg", "id": 155, "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788885694/e-flowers/products/784717902_1318624534660281_776_885693_58030477.jpg", "is_primary": true, "large_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_limit,f_auto,h_1400,q_auto:good,w_1400/v1/e-flowers/products/784717902_1318624534660281_776_885693_58030477", "medium_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_limit,f_auto,h_600,q_auto:good,w_600/v1/e-flowers/products/784717902_1318624534660281_776_885693_58030477", "product_id": 252, "public_id": "e-flowers/products/784717902_1318624534660281_776_885693_58030477", "sort_order": 0, "thumbnail_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_200,q_auto:good,w_200/v1/e-flowers/products/784717902_1318624534660281_776_885693_58030477"}], "is_archived": false, "is_available": true, "keep_ymal_addons_when_unavailable": false, "main_category": {"id": 3, "name": "Bouquets", "slug": "bouquets"}, "main_category_icon": "ri-gift-line", "main_category_id": 3, "main_category_name": "Bouquets", "main_category_slug": "bouquets", "name": "Blue Bouquet", "overall_avg_rating": 0.0, "overall_review_count": 0, "price": 449.98, "review_count": 0, "special_price": null, "stock_quantity": 10, "store_category_id": null, "store_category_name": null, "store_category_slug": null, "store_id": 15, "store_name": "E-flora", "thumbnail_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_200,q_auto:good,w_200/v1/e-flowers/products/784717902_1318624534660281_776_885693_58030477", "updated_at": "2026-09-09T19:27:36.358998", "variant_ratings": {}, "variants": [], "ymal_addon_options": [{"created_at": "2026-09-05T18:30:21.745034", "group_id": 5, "group_name": "Chocolate", "id": 10, "image_public_id": "e-flowers/addons/images_633020_a9ccc5a0", "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788633021/e-flowers/addons/images_633020_a9ccc5a0.jpg", "is_available": true, "is_oos": false, "name": "Ferrero", "price": 230.0, "show_in_you_may_also_like": true, "sort_order": 0, "source_product_id": 249, "stock_quantity": 15, "ymal_type": "addon_option"}]}, {"addon_groups": [], "archived_at": null, "archived_by": null, "avg_rating": 5.0, "can_deliver_to_customer": true, "category_display": "Bouquets", "category_path": "Bouquets", "created_at": "2026-09-07T20:55:23.441333", "delivery_block_reason": null, "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.", "discount_pct": 10, "effective_price": 900.0, "has_addons": false, "has_variants": false, "has_ymal_addons": false, "id": 251, "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788814522/e-flowers/products/787524234_1325750737280994_311_814521_bf05df39.jpg", "images": [{"created_at": "2026-09-07T20:55:23.467310", "filename": "cloudinary_e-flowers/products/787524234_1325750737280994_311_814521_bf05df39.jpg", "id": 154, "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788814522/e-flowers/products/787524234_1325750737280994_311_814521_bf05df39.jpg", "is_primary": true, "large_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_limit,f_auto,h_1400,q_auto:good,w_1400/v1/e-flowers/products/787524234_1325750737280994_311_814521_bf05df39", "medium_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_limit,f_auto,h_600,q_auto:good,w_600/v1/e-flowers/products/787524234_1325750737280994_311_814521_bf05df39", "product_id": 251, "public_id": "e-flowers/products/787524234_1325750737280994_311_814521_bf05df39", "sort_order": 0, "thumbnail_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_200,q_auto:good,w_200/v1/e-flowers/products/787524234_1325750737280994_311_814521_bf05df39"}], "is_archived": false, "is_available": true, "keep_ymal_addons_when_unavailable": false, "main_category": {"id": 3, "name": "Bouquets", "slug": "bouquets"}, "main_category_icon": "ri-gift-line", "main_category_id": 3, "main_category_name": "Bouquets", "main_category_slug": "bouquets", "name": "Custom Pink Roses", "overall_avg_rating": 5.0, "overall_review_count": 1, "price": 1000.0, "review_count": 1, "special_price": 900.0, "stock_quantity": 9, "store_category_id": null, "store_category_name": null, "store_category_slug": null, "store_id": 15, "store_name": "E-flora", "thumbnail_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_200,q_auto:good,w_200/v1/e-flowers/products/787524234_1325750737280994_311_814521_bf05df39", "updated_at": "2026-09-09T19:28:13.411536", "variant_ratings": {"main": {"avg": 5.0, "count": 1}}, "variants": [], "ymal_addon_options": [{"created_at": "2026-09-05T18:30:21.745034", "group_id": 5, "group_name": "Chocolate", "id": 10, "image_public_id": "e-flowers/addons/images_633020_a9ccc5a0", "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788633021/e-flowers/addons/images_633020_a9ccc5a0.jpg", "is_available": true, "is_oos": false, "name": "Ferrero", "price": 230.0, "show_in_you_may_also_like": true, "sort_order": 0, "source_product_id": 249, "stock_quantity": 15, "ymal_type": "addon_option"}]}, {"addon_groups": [{"id": 5, "is_active": true, "name": "Chocolate", "options": [{"created_at": "2026-09-05T18:30:21.745034", "group_id": 5, "group_name": "Chocolate", "id": 10, "image_public_id": "e-flowers/addons/images_633020_a9ccc5a0", "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788633021/e-flowers/addons/images_633020_a9ccc5a0.jpg", "is_available": true, "is_oos": false, "name": "Ferrero", "price": 230.0, "show_in_you_may_also_like": true, "sort_order": 0, "stock_quantity": 15}], "product_id": 249, "sort_order": 0}], "archived_at": null, "archived_by": null, "avg_rating": 4.7, "can_deliver_to_customer": true, "category_display": "Bouquets", "category_path": "Bouquets", "created_at": "2026-09-05T18:27:11.710710", "delivery_block_reason": null, "description": "new test", "discount_pct": null, "effective_price": 300.0, "has_addons": true, "has_variants": true, "has_ymal_addons": true, "id": 249, "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788632830/e-flowers/products/luci_632829_9b57bef2.jpg", "images": [{"created_at": "2026-09-05T18:27:11.718082", "filename": "cloudinary_e-flowers/products/luci_632829_9b57bef2.jpg", "id": 152, "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788632830/e-flowers/products/luci_632829_9b57bef2.jpg", "is_primary": true, "large_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_limit,f_auto,h_1400,q_auto:good,w_1400/v1/e-flowers/products/luci_632829_9b57bef2", "medium_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_limit,f_auto,h_600,q_auto:good,w_600/v1/e-flowers/products/luci_632829_9b57bef2", "product_id": 249, "public_id": "e-flowers/products/luci_632829_9b57bef2", "sort_order": 0, "thumbnail_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_200,q_auto:good,w_200/v1/e-flowers/products/luci_632829_9b57bef2"}], "is_archived": false, "is_available": true, "keep_ymal_addons_when_unavailable": false, "main_category": {"id": 3, "name": "Bouquets", "slug": "bouquets"}, "main_category_icon": "ri-gift-line", "main_category_id": 3, "main_category_name": "Bouquets", "main_category_slug": "bouquets", "name": "Sunflower Bouquet", "overall_avg_rating": 4.7, "overall_review_count": 14, "price": 300.0, "review_count": 12, "special_price": null, "stock_quantity": 2, "store_category_id": null, "store_category_name": null, "store_category_slug": null, "store_id": 15, "store_name": "E-flora", "thumbnail_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_200,q_auto:good,w_200/v1/e-flowers/products/luci_632829_9b57bef2", "updated_at": "2026-09-09T20:21:03.493606", "variant_ratings": {"72": {"avg": 5.0, "count": 2}, "main": {"avg": 4.7, "count": 12}}, "variants": [{"attributes": {}, "created_at": "2026-09-05T18:30:21.727881", "discount_pct": null, "effective_price": 400.01, "id": 72, "image_public_id": "e-flowers/variants/781487014_1318628617993206_431_633018_efa7626f", "image_thumbnail": "https://res.cloudinary.com/dgyq49vi2/image/upload/c_fill,f_auto,h_100,q_auto:good,w_100/v1/e-flowers/variants/781487014_1318628617993206_431_633018_efa7626f", "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788633019/e-flowers/variants/781487014_1318628617993206_431_633018_efa7626f.jpg", "is_available": true, "name": "large", "price": 400.01, "product_id": 249, "sku": "TEST-PRODU-LARGE", "sort_order": 0, "special_price": null, "stock_quantity": 22, "updated_at": "2026-09-08T16:43:06.251947"}], "ymal_addon_options": [{"created_at": "2026-09-05T18:30:21.745034", "group_id": 5, "group_name": "Chocolate", "id": 10, "image_public_id": "e-flowers/addons/images_633020_a9ccc5a0", "image_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1788633021/e-flowers/addons/images_633020_a9ccc5a0.jpg", "is_available": true, "is_oos": false, "name": "Ferrero", "price": 230.0, "show_in_you_may_also_like": true, "sort_order": 0, "source_product_id": 249, "stock_quantity": 15, "ymal_type": "addon_option"}]}]
/* --- SCRIPT BREAK --- */

// Quick-add: multi-select Standard/variants + add-ons with per-card qty
(function () {
    let qaProductsById = {};
    let qaCurrentProduct = null;
    let qaFocusKey = 'main';
    let qaOptionQty = {}; // option key -> qty
    let qaAddonQty = {};  // addon option id -> qty
    let qaAnchorEl = null;
    let qaRepositionBound = null;
    let qaAdding = false;

    function loadHomeProductsMap() {
        const el = document.getElementById('homeProductsQuickAdd')
            || document.getElementById('quickAddProductsData');
        if (!el) return;
        try {
            const list = JSON.parse(el.textContent || '[]');
            qaProductsById = {};
            (list || []).forEach(function (p) {
                if (p && p.id != null) qaProductsById[String(p.id)] = p;
            });
        } catch (e) {
            console.error('Failed to parse products for quick add', e);
            qaProductsById = {};
        }
    }

    function qaMoney(n) {
        const num = Number(n);
        if (!Number.isFinite(num)) return '₱0.00';
        const formatted = (typeof window.formatMoneyValue === 'function')
            ? window.formatMoneyValue(num)
            : num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return '₱' + formatted;
    }

    function qaEscape(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function qaThumbHtml(url) {
        if (url) {
            return '<img class="qa-option-thumb" src="' + qaEscape(url) + '" alt="" onerror="this.outerHTML=\'<div class=&quot;qa-option-thumb qa-option-thumb-fallback&quot;><i class=&quot;ri-image-line&quot;></i></div>\'">';
        }
        return '<div class="qa-option-thumb qa-option-thumb-fallback"><i class="ri-image-line"></i></div>';
    }

    function qaPriceHtml(effective, regular) {
        const eff = Number(effective);
        const reg = Number(regular);
        if (Number.isFinite(reg) && Number.isFinite(eff) && reg > eff) {
            return '<div class="qa-option-price"><span class="was">' + qaMoney(reg) + '</span>' + qaMoney(eff) + '</div>';
        }
        return '<div class="qa-option-price">' + qaMoney(Number.isFinite(eff) ? eff : reg) + '</div>';
    }

    function qaRatingForKey(product, key) {
        const map = (product && product.variant_ratings) || {};
        let bucket = null;
        if (key === 'main') {
            bucket = map.main;
        } else if (key && String(key).indexOf('v-') === 0) {
            bucket = map[String(key).slice(2)];
        }
        const avg = bucket ? Number(bucket.avg) || 0 : 0;
        const count = bucket ? Number(bucket.count) || 0 : 0;
        return { avg: avg, count: count };
    }

    function qaRatingLabel(avg, count) {
        if (!count) return { avgText: '0', countText: '(0)', empty: true };
        const a = Number(avg) || 0;
        const avgText = (Math.round(a * 10) / 10).toFixed(1);
        return { avgText: avgText, countText: '(' + count + ')', empty: false };
    }

    function syncQuickAddRating(product, key) {
        const el = document.getElementById('qaPickerRating');
        const avgEl = document.getElementById('qaPickerRatingAvg');
        const countEl = document.getElementById('qaPickerRatingCount');
        if (!el || !avgEl || !countEl) return;
        const r = qaRatingForKey(product, key || 'main');
        const label = qaRatingLabel(r.avg, r.count);
        avgEl.textContent = label.avgText;
        countEl.textContent = label.countText;
        el.classList.toggle('is-empty', label.empty);
        el.setAttribute(
            'title',
            label.empty
                ? 'No reviews for this option yet'
                : (label.avgText + ' from ' + r.count + ' review' + (r.count === 1 ? '' : 's'))
        );
    }

    function qaOptionRatingHtml(product, key) {
        const r = qaRatingForKey(product, key);
        const label = qaRatingLabel(r.avg, r.count);
        return (
            '<div class="qa-option-rating' + (label.empty ? ' is-empty' : '') + '">' +
            '<i class="ri-star-fill" aria-hidden="true"></i>' +
            '<span>' + qaEscape(label.avgText) + '</span>' +
            '<span class="qa-option-rating-count">' + qaEscape(label.countText) + '</span>' +
            '</div>'
        );
    }

    function qaItemQtyHtml(kind, id, qty, maxStock) {
        const max = Math.max(0, Number(maxStock) || 0);
        const q = Math.max(0, Number(qty) || 0);
        const plusDisabled = q >= max ? ' disabled' : '';
        const minusDisabled = q <= 0 ? ' disabled' : '';
        const idAttr = qaEscape(String(id));
        return (
            '<div class="qa-item-qty" aria-label="Quantity" onclick="event.stopPropagation()">' +
            '<button type="button" class="qa-item-qty-btn" aria-label="Decrease quantity"' +
            ' onclick="changeQuickAddLineQty(\'' + kind + '\',\'' + idAttr + '\',-1)"' + minusDisabled + '>−</button>' +
            '<span class="qa-item-qty-val">' + q + '</span>' +
            '<button type="button" class="qa-item-qty-btn" aria-label="Increase quantity"' +
            ' onclick="changeQuickAddLineQty(\'' + kind + '\',\'' + idAttr + '\',1)"' + plusDisabled + '>+</button>' +
            '</div>'
        );
    }

    function buildOptions(product) {
        const options = [];
        const mainStock = Number(product.stock_quantity) || 0;
        const mainEff = product.effective_price != null ? product.effective_price : product.price;
        options.push({
            key: 'main',
            variant_id: null,
            name: 'Standard',
            price: mainEff,
            regular_price: product.price,
            stock: mainStock,
            image_url: product.image_url || product.thumbnail_url || '',
            in_stock: product.is_available !== false && mainStock > 0
        });

        (product.variants || []).forEach(function (v) {
            if (!v || v.is_available === false) return;
            const stock = Number(v.stock_quantity) || 0;
            const eff = v.effective_price != null ? v.effective_price : v.price;
            options.push({
                key: 'v-' + v.id,
                variant_id: v.id,
                name: v.name || 'Option',
                price: eff,
                regular_price: v.price,
                stock: stock,
                image_url: v.image_url || product.image_url || '',
                in_stock: stock > 0
            });
        });
        return options;
    }

    function qaCollectProductAddons(product) {
        const out = [];
        (product.addon_groups || []).forEach(function (g) {
            if (!g || g.is_active === false) return;
            (g.options || []).forEach(function (o) {
                if (!o || o.is_available === false) return;
                out.push({
                    id: o.id,
                    name: o.name,
                    price: o.price,
                    stock: Number(o.stock_quantity) || 0,
                    image_url: o.image_url || '',
                    group_name: g.name || 'Add-on',
                    in_stock: (Number(o.stock_quantity) || 0) > 0
                });
            });
        });
        return out;
    }

    function findAddonMeta(product, optionId) {
        const id = String(optionId);
        const fromProduct = qaCollectProductAddons(product).find(function (o) {
            return String(o.id) === id;
        });
        if (fromProduct) return fromProduct;
        const ymal = (product.ymal_addon_options || []).find(function (o) {
            return o && String(o.id) === id;
        });
        if (!ymal) return null;
        return {
            id: ymal.id,
            name: ymal.name,
            price: ymal.price,
            stock: Number(ymal.stock_quantity) || 0,
            image_url: ymal.image_url || '',
            group_name: ymal.group_name || 'Add-on',
            in_stock: (Number(ymal.stock_quantity) || 0) > 0
        };
    }

    function calcQuickAddTotals() {
        if (!qaCurrentProduct) {
            return { itemCount: 0, unitCount: 0, total: 0, hasSelection: false };
        }
        const options = buildOptions(qaCurrentProduct);
        let itemCount = 0;
        let unitCount = 0;
        let total = 0;

        options.forEach(function (opt) {
            const qty = Number(qaOptionQty[opt.key]) || 0;
            if (qty <= 0) return;
            itemCount += 1;
            unitCount += qty;
            total += qty * (Number(opt.price) || 0);
        });

        Object.keys(qaAddonQty).forEach(function (id) {
            const qty = Number(qaAddonQty[id]) || 0;
            if (qty <= 0) return;
            const meta = findAddonMeta(qaCurrentProduct, id);
            if (!meta) return;
            itemCount += 1;
            unitCount += qty;
            total += qty * (Number(meta.price) || 0);
        });

        return {
            itemCount: itemCount,
            unitCount: unitCount,
            total: total,
            hasSelection: unitCount > 0
        };
    }

    function updateQuickAddConfirmBtn() {
        const totals = calcQuickAddTotals();
        const confirmBtn = document.getElementById('qaConfirmBtn');
        const footMeta = document.getElementById('qaFootTotal');
        const footSummary = document.getElementById('qaFootSummary');
        const footAmount = document.getElementById('qaFootAmount');

        if (footMeta) footMeta.classList.toggle('is-empty', !totals.hasSelection);
        if (footSummary) {
            footSummary.textContent = totals.unitCount === 1
                ? '1 item'
                : (totals.unitCount + ' items');
        }
        if (footAmount) footAmount.textContent = qaMoney(totals.total);

        if (confirmBtn && !qaAdding) {
            confirmBtn.disabled = !totals.hasSelection;
            confirmBtn.innerHTML =
                '<i class="ri-shopping-bag-line" aria-hidden="true"></i>' +
                '<span id="qaConfirmLabel">Add to basket</span>';
        }
    }

    function renderOptionCards(product) {
        const listEl = document.getElementById('qaOptionList');
        if (!listEl) return;
        const options = buildOptions(product);

        listEl.innerHTML = options.map(function (opt) {
            const qty = Number(qaOptionQty[opt.key]) || 0;
            const selected = qty > 0 ? ' is-selected' : '';
            const disabled = opt.in_stock ? '' : ' is-disabled';
            const stockText = opt.in_stock
                ? (opt.stock + ' available')
                : 'Out of stock';
            const stockClass = opt.in_stock ? '' : ' out';
            return (
                '<div class="qa-option-card' + selected + disabled + '" data-key="' + qaEscape(opt.key) + '">' +
                '<div class="qa-option-row">' +
                '<button type="button" class="qa-option-hit' + (opt.in_stock ? '' : ' is-disabled') + '"' +
                ' onclick="toggleQuickAddOption(\'' + qaEscape(opt.key) + '\')">' +
                qaThumbHtml(opt.image_url) +
                '<div class="qa-option-info">' +
                '<div class="qa-option-name">' + qaEscape(opt.name) + '</div>' +
                '<div class="qa-option-stock' + stockClass + '">' + stockText + '</div>' +
                qaOptionRatingHtml(product, opt.key) +
                '</div>' +
                '</button>' +
                '<div class="qa-option-side">' +
                qaPriceHtml(opt.price, opt.regular_price) +
                qaItemQtyHtml('option', opt.key, qty, opt.stock) +
                '</div>' +
                '</div>' +
                '</div>'
            );
        }).join('');
    }

    function renderQuickAddExtras(product) {
        const mount = document.getElementById('qaExtrasMount');
        if (!mount) return;
        const productAddons = qaCollectProductAddons(product);
        const productAddonIds = {};
        productAddons.forEach(function (o) {
            if (o && o.id != null) productAddonIds[String(o.id)] = true;
        });
        // Skip YMAL entries already listed under this product's Add-ons
        const ymal = (product.ymal_addon_options || []).filter(function (o) {
            if (!o || o.is_available === false) return false;
            return !productAddonIds[String(o.id)];
        });

        function rowHtml(o, section) {
            const id = String(o.id);
            const qty = Number(qaAddonQty[id]) || 0;
            const stock = Number(o.stock != null ? o.stock : o.stock_quantity) || 0;
            const ok = stock > 0;
            const selected = qty > 0 ? ' is-selected' : '';
            const disabled = ok ? '' : ' is-disabled';
            return (
                '<div class="qa-option-card' + selected + disabled + '" data-addon-id="' + qaEscape(id) + '">' +
                '<button type="button" class="qa-option-row' + (ok ? '' : ' is-disabled') + '"' +
                ' onclick="toggleQuickAddAddon(' + o.id + ',' + stock + ')">' +
                qaThumbHtml(o.image_url) +
                '<div class="qa-option-info">' +
                '<div class="qa-option-name">' + qaEscape(o.name) + '</div>' +
                '<div class="qa-option-stock' + (ok ? '' : ' out') + '">' +
                (ok ? (stock + ' left') : 'Out of stock') +
                '</div></div>' +
                qaPriceHtml(o.price, o.price) +
                '</button>' +
                qaItemQtyHtml('addon', id, qty, stock) +
                '</div>'
            );
        }

        let html = '';
        if (productAddons.length) {
            html += '<span class="qa-picker-label" style="margin-top:0.85rem;">Add-ons</span>';
            html += '<div class="qa-extras-list">' + productAddons.map(function (o) {
                return rowHtml(o, 'Add-on');
            }).join('') + '</div>';
        }
        if (ymal.length) {
            html += '<span class="qa-picker-label" style="margin-top:0.85rem;">You may also like</span>';
            html += '<div class="qa-extras-list">' + ymal.map(function (o) {
                return rowHtml({
                    id: o.id,
                    name: o.name,
                    price: o.price,
                    stock: o.stock_quantity,
                    image_url: o.image_url,
                    group_name: o.group_name || 'Add-on'
                }, 'YMAL');
            }).join('') + '</div>';
        }
        mount.innerHTML = html;
    }

    function refreshQuickAddLists() {
        if (!qaCurrentProduct) return;
        renderOptionCards(qaCurrentProduct);
        renderQuickAddExtras(qaCurrentProduct);
        syncQuickAddRating(qaCurrentProduct, qaFocusKey);
        updateQuickAddConfirmBtn();
        if (qaAnchorEl) {
            requestAnimationFrame(function () { positionPicker(qaAnchorEl); });
        }
    }

    function renderPicker(product) {
        const storeEl = document.getElementById('qaPickerStore');
        const titleEl = document.getElementById('qaPickerTitle');
        const imgWrap = document.getElementById('qaPickerImgWrap');

        storeEl.textContent = product.store_name || 'Flower Shop';
        titleEl.textContent = product.name || 'Product';

        if (product.image_url) {
            imgWrap.className = 'qa-picker-img';
            imgWrap.innerHTML = '<img class="qa-picker-img" src="' + qaEscape(product.image_url) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:14px;" onerror="this.parentElement.className=\'qa-picker-img qa-picker-img-fallback\';this.parentElement.innerHTML=\'<i class=\\\'ri-image-line\\\'></i>\';">';
        } else {
            imgWrap.className = 'qa-picker-img qa-picker-img-fallback';
            imgWrap.innerHTML = '<i class="ri-image-line"></i>';
        }

        qaOptionQty = {};
        qaAddonQty = {};
        const options = buildOptions(product);
        const firstInStock = options.find(function (o) { return o.in_stock; });
        qaFocusKey = firstInStock ? firstInStock.key : 'main';
        // Start with nothing selected so multi-pick is intentional
        refreshQuickAddLists();
    }

    window.toggleQuickAddOption = function (key) {
        if (!qaCurrentProduct || qaAdding) return;
        const opt = buildOptions(qaCurrentProduct).find(function (o) {
            return o.key === key;
        });
        if (!opt) return;
        if (!opt.in_stock) {
            if (typeof showToast === 'function') {
                showToast(`"${opt.name}" is out of stock.`, 'error');
            } else if (typeof showCartActionError === 'function') {
                showCartActionError(`"${opt.name}" is out of stock.`);
            }
            return;
        }
        qaFocusKey = key;
        const cur = Number(qaOptionQty[key]) || 0;
        if (cur > 0) delete qaOptionQty[key];
        else qaOptionQty[key] = 1;
        refreshQuickAddLists();
    };

    window.toggleQuickAddAddon = function (optionId, maxStock) {
        if (qaAdding) return;
        const id = String(optionId);
        const stock = Math.max(0, Number(maxStock) || 0);
        if (stock <= 0) {
            const meta = qaCurrentProduct ? findAddonMeta(qaCurrentProduct, id) : null;
            const name = meta ? meta.name : 'This add-on';
            if (typeof showToast === 'function') {
                showToast(`"${name}" is out of stock.`, 'error');
            } else if (typeof showCartActionError === 'function') {
                showCartActionError(`"${name}" is out of stock.`);
            }
            return;
        }
        if (qaAddonQty[id]) delete qaAddonQty[id];
        else qaAddonQty[id] = 1;
        refreshQuickAddLists();
    };

    window.changeQuickAddLineQty = function (kind, id, delta) {
        if (qaAdding) return;
        const key = String(id);
        const d = Number(delta) || 0;
        if (kind === 'option') {
            if (!qaCurrentProduct) return;
            const opt = buildOptions(qaCurrentProduct).find(function (o) {
                return o.key === key;
            });
            if (!opt || !opt.in_stock) return;
            qaFocusKey = key;
            const max = Math.max(0, Number(opt.stock) || 0);
            const next = Math.max(0, Math.min(max, (Number(qaOptionQty[key]) || 0) + d));
            if (next <= 0) delete qaOptionQty[key];
            else qaOptionQty[key] = next;
        } else if (kind === 'addon') {
            const meta = qaCurrentProduct ? findAddonMeta(qaCurrentProduct, key) : null;
            const max = meta ? Math.max(0, Number(meta.stock) || 0) : 0;
            const next = Math.max(0, Math.min(max, (Number(qaAddonQty[key]) || 0) + d));
            if (next <= 0) delete qaAddonQty[key];
            else qaAddonQty[key] = next;
        }
        refreshQuickAddLists();
    };

    function positionPicker(anchor) {
        const picker = document.getElementById('qaPicker');
        if (!picker || !anchor) return;

        picker.style.opacity = '';
        picker.style.visibility = '';
        picker.style.transform = '';

        if (window.matchMedia('(max-width: 640px)').matches) {
            picker.style.left = '';
            picker.style.top = '';
            picker.style.right = '';
            picker.style.bottom = '';
            picker.style.width = '';
            return;
        }

        const rect = anchor.getBoundingClientRect();
        const margin = 10;
        const width = Math.min(420, window.innerWidth - 24);
        picker.style.width = width + 'px';

        let left = rect.right - width;
        left = Math.max(12, Math.min(left, window.innerWidth - width - 12));
        picker.style.left = left + 'px';
        picker.style.right = 'auto';
        picker.style.bottom = 'auto';

        const height = Math.min(picker.offsetHeight || 360, window.innerHeight - 24);
        let top = rect.bottom + margin;
        if (top + height > window.innerHeight - 12) {
            top = rect.top - height - margin;
        }
        if (top < 12) top = 12;
        picker.style.top = top + 'px';
    }

    window.openQuickAddPicker = function (anchorEl, productId) {
        if (!Object.keys(qaProductsById).length) loadHomeProductsMap();
        const product = qaProductsById[String(productId)];
        if (!product) {
            if (typeof showToast === 'function') showToast('Product unavailable');
            return;
        }

        qaCurrentProduct = product;
        qaAnchorEl = anchorEl || null;
        renderPicker(product);

        const header = document.querySelector('.main-header');
        if (header) {
            header.style.setProperty('--header-hide-offset', header.offsetHeight + 'px');
            header.classList.remove('header-hidden');
        }
        document.body.classList.add('qa-picker-open');

        const overlay = document.getElementById('qaOverlay');
        const picker = document.getElementById('qaPicker');
        overlay.classList.add('open');
        overlay.setAttribute('aria-hidden', 'false');
        picker.hidden = false;
        picker.style.opacity = '';
        picker.style.visibility = '';
        picker.classList.add('open');
        if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();

        if (qaAnchorEl) {
            requestAnimationFrame(function () {
                positionPicker(qaAnchorEl);
            });
        } else {
            picker.style.left = '50%';
            picker.style.top = '50%';
            picker.style.transform = 'translate(-50%, -50%)';
        }

        if (!qaRepositionBound) {
            qaRepositionBound = function () {
                if (!qaAnchorEl) return;
                const p = document.getElementById('qaPicker');
                if (p && p.classList.contains('open')) positionPicker(qaAnchorEl);
            };
            window.addEventListener('resize', qaRepositionBound);
            window.addEventListener('scroll', qaRepositionBound, true);
        }

        document.addEventListener('keydown', qaOnKeydown);
    };

    function qaOnKeydown(e) {
        if (e.key === 'Escape') closeQuickAddPicker();
    }

    window.closeQuickAddPicker = function () {
        const overlay = document.getElementById('qaOverlay');
        const picker = document.getElementById('qaPicker');
        const confirmBtn = document.getElementById('qaConfirmBtn');
        if (overlay) {
            overlay.classList.remove('open');
            overlay.setAttribute('aria-hidden', 'true');
        }
        if (picker) {
            picker.classList.remove('open');
            picker.hidden = true;
            picker.style.left = '';
            picker.style.top = '';
            picker.style.right = '';
            picker.style.bottom = '';
            picker.style.width = '';
            picker.style.transform = '';
            picker.style.opacity = '';
            picker.style.visibility = '';
        }
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML =
                '<i class="ri-shopping-bag-line" aria-hidden="true"></i>' +
                '<span id="qaConfirmLabel">Add to basket</span>';
        }
        const footMeta = document.getElementById('qaFootTotal');
        const footSummary = document.getElementById('qaFootSummary');
        const footAmount = document.getElementById('qaFootAmount');
        if (footMeta) footMeta.classList.add('is-empty');
        if (footSummary) footSummary.textContent = '0 items';
        if (footAmount) footAmount.textContent = '₱0.00';
        qaCurrentProduct = null;
        qaFocusKey = 'main';
        qaOptionQty = {};
        qaAddonQty = {};
        qaAnchorEl = null;
        qaAdding = false;
        document.body.classList.remove('qa-picker-open');
        const header = document.querySelector('.main-header');
        if (header) header.classList.remove('header-hidden');

        document.removeEventListener('keydown', qaOnKeydown);
        if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();
    };

    async function qaAddToCart(payload) {
        
        if (typeof window.addToCartLocalStorage === 'function') {
            window.addToCartLocalStorage(payload);
        } else if (typeof window.addToCart === 'function') {
            window.addToCart(payload);
        } else {
            throw new Error('Cart is unavailable');
        }
        try {
            if (typeof window.updateCartCount === 'function') window.updateCartCount();
        } catch (e) {
            console.warn('Cart count refresh failed after add', e);
        }
        return true;
        
    }

    window.confirmQuickAdd = async function () {
        if (!qaCurrentProduct || qaAdding) return;
        const options = buildOptions(qaCurrentProduct);
        const selectedOptions = options.filter(function (o) {
            return (Number(qaOptionQty[o.key]) || 0) > 0 && o.in_stock;
        });
        const addonIds = Object.keys(qaAddonQty).map(function (id) {
            return { addon_option_id: parseInt(id, 10), quantity: qaAddonQty[id] };
        }).filter(function (row) { return row.quantity > 0; });

        if (!selectedOptions.length && !addonIds.length) {
            if (typeof showToast === 'function') showToast('Please select at least one option');
            return;
        }
        if (!selectedOptions.length && addonIds.length) {
            if (typeof showToast === 'function') {
                showToast('Select a Standard or variant to attach add-ons');
            }
            return;
        }

        for (let j = 0; j < addonIds.length; j++) {
            const row = addonIds[j];
            const meta = findAddonMeta(qaCurrentProduct, row.addon_option_id);
            const stock = meta ? Math.max(0, Number(meta.stock != null ? meta.stock : meta.stock_quantity) || 0) : 0;
            const name = meta ? meta.name : 'Add-on';
            if (stock <= 0) {
                if (typeof showToast === 'function') {
                    showToast(`"${name}" is out of stock.`, 'error');
                } else if (typeof showCartActionError === 'function') {
                    showCartActionError(`"${name}" is out of stock.`);
                }
                return;
            }
            if (row.quantity > stock) {
                if (typeof showToast === 'function') {
                    showToast(`Only ${stock} available for "${name}".`, 'error');
                } else if (typeof showCartActionError === 'function') {
                    showCartActionError(`Only ${stock} available for "${name}".`);
                }
                return;
            }
        }

        const totals = calcQuickAddTotals();
        const confirmBtn = document.getElementById('qaConfirmBtn');
        const idleBtnHtml =
            '<i class="ri-shopping-bag-line" aria-hidden="true"></i>' +
            '<span id="qaConfirmLabel">Add to basket</span>';
        qaAdding = true;
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i><span>Adding…</span>';
        }

        try {
            for (let i = 0; i < selectedOptions.length; i++) {
                const selected = selectedOptions[i];
                const quantity = Math.min(
                    Math.max(1, Number(qaOptionQty[selected.key]) || 1),
                    Math.max(1, Number(selected.stock) || 1)
                );
                const displayName = selected.variant_id
                    ? (qaCurrentProduct.name + ' — ' + selected.name)
                    : qaCurrentProduct.name;
                const payload = {
                    id: qaCurrentProduct.id,
                    name: displayName,
                    price: selected.price,
                    effective_price: selected.price,
                    store_id: qaCurrentProduct.store_id || null,
                    store_name: qaCurrentProduct.store_name || 'Flower Shop',
                    image_url: selected.image_url || qaCurrentProduct.image_url || '',
                    quantity: quantity
                };
                if (selected.variant_id) payload.variant_id = selected.variant_id;
                // Attach add-ons once to the first product line only
                if (i === 0 && addonIds.length) {
                    payload.addon_option_ids = addonIds;
                    payload.addons = addonIds.map(function (row) {
                        const meta = findAddonMeta(qaCurrentProduct, row.addon_option_id);
                        return {
                            id: row.addon_option_id,
                            addon_option_id: row.addon_option_id,
                            quantity: row.quantity,
                            name: meta ? meta.name : 'Add-on',
                            price: meta ? Number(meta.price) || 0 : 0,
                            image_url: meta ? (meta.image_url || '') : '',
                            group_name: meta ? (meta.group_name || '') : ''
                        };
                    });
                }
                await qaAddToCart(payload);
            }

            if (typeof showToast === 'function') {
                showToast(totals.unitCount > 1
                    ? (totals.unitCount + ' items added to basket')
                    : ((selectedOptions[0]
                        ? (selectedOptions[0].variant_id
                            ? (qaCurrentProduct.name + ' — ' + selectedOptions[0].name)
                            : qaCurrentProduct.name)
                        : 'Item') + ' added to basket'));
            }
            closeQuickAddPicker();
        } catch (err) {
            console.error('Quick add failed', err);
            const msg = (err && err.name === 'AbortError')
                ? 'Request timed out — please try again'
                : ((err && err.message) ? err.message : 'Could not add to cart');
            if (typeof showToast === 'function') showToast(msg, 'error');
            if (confirmBtn) {
                confirmBtn.innerHTML = idleBtnHtml;
                confirmBtn.disabled = false;
            }
            updateQuickAddConfirmBtn();
        } finally {
            qaAdding = false;
        }
    };

    // Legacy helpers
    window.selectQuickAddOption = function (btn) {
        if (!btn) return;
        const key = btn.getAttribute('data-key') || 'main';
        toggleQuickAddOption(key);
    };
    window.changeQuickAddQty = function () { /* footer qty removed */ };
    window.changeQuickAddAddonQty = function (optionId, delta) {
        changeQuickAddLineQty('addon', String(optionId), delta);
    };
    window.quickAdd = function (productId) {
        openQuickAddPicker(null, productId);
    };

    document.addEventListener('DOMContentLoaded', function () {
        // Never leave the sticky header unclickable after a bad quick-add state.
        document.body.classList.remove('qa-picker-open');
        const overlay = document.getElementById('qaOverlay');
        const picker = document.getElementById('qaPicker');
        if (overlay) {
            overlay.classList.remove('open');
            overlay.setAttribute('aria-hidden', 'true');
        }
        if (picker) {
            picker.classList.remove('open');
            picker.hidden = true;
        }
        loadHomeProductsMap();
    });
})();

/* --- SCRIPT BREAK --- */

const SHOPPING_DISABLED = false;
const DEBUG = {
    enabled: true,
    log: function(step, data) {
        if (!this.enabled) return;
        console.log(`%c🔍 CART DEBUG - ${step}`, 'background: #b5445a; color: white; padding: 2px 5px; border-radius: 3px;');
        if (data !== undefined && data !== null) {
            try {
                console.log('Data:', JSON.parse(JSON.stringify(data)));
            } catch (e) {
                console.log('Data:', data);
            }
        } else {
            console.log('Data: undefined/null');
        }
    },
    table: function(data) {
        if (!this.enabled) return;
        if (data && Array.isArray(data)) {
            console.table(data);
        } else {
            console.log('Table data: not an array or empty');
        }
    },    
    group: function(name) {
        if (!this.enabled) return;
        console.group(`%c📦 ${name}`, 'color: #b5445a; font-weight: bold;');
    },
    groupEnd: function() {
        if (!this.enabled) return;
        console.groupEnd();
    }
};

// ===== AUTO-HIDE HEADER ON SCROLL =====
(function autoHideHeader() {
    const header = document.querySelector('.main-header');
    if (!header) return;

    let lastY = window.scrollY;
    let ticking = false;

    function measure() {
        // Full sticky block: logo/search/actions + category nav
        header.style.setProperty('--header-hide-offset', `${header.offsetHeight}px`);
    }

    function update() {
        ticking = false;
        const y = Math.max(window.scrollY, 0);
        const delta = y - lastY;

        // Ignore rubber-banding and jitter so the header doesn't flicker
        if (Math.abs(delta) < 6) return;

        const pastHeader = y > header.offsetHeight + 40;
        if (document.body.classList.contains('qa-picker-open')) {
            lastY = y;
            return;
        }
        if (delta > 0 && pastHeader) {
            header.classList.add('header-hidden');
        } else if (delta < 0) {
            header.classList.remove('header-hidden');
        }

        lastY = y;
    }

    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(update);
    }, { passive: true });

    // Never leave the header hidden while a menu or drawer needs it
    window.addEventListener('focusin', e => {
        if (header.contains(e.target)) header.classList.remove('header-hidden');
    });
})();

let cart = [];
let cartQtyTimers = {};
let cartQtyPending = {};
const HAS_SERVER_CART = false;
let isLoadingCart = false;
let checkoutStep = 1;
let checkoutOrders = [];
let uploadedProofs = {};
let uploadedProofData = {};
let selectedPaymentMethods = {};
let currentOrderIndex = 0;
let checkoutAddresses = [];
let selectedCheckoutAddressId = null;
/** addressId -> { canDeliver: bool, issues: [{store_name, reason, distance_km}] } */
let checkoutAddressDeliveryMap = {};
let currentCheckoutSession = null;
let checkoutModalCloseHandler = null;
let isCreatingOrders = false;  // ADDED: Prevents duplicate order creation
let buyNowMode = false;  // True when using Buy Now (skip cart)
let buyNowItem = null;   // { product_id, variant_id, quantity, price, name, store_name, image_url, addons? }

// ===== CHECKOUT SESSION MANAGEMENT =====
function startCheckoutSession() {
    currentCheckoutSession = 'checkout_' + Date.now() + '_' + Math.random().toString(36).substr(2, 8);
    sessionStorage.setItem('active_checkout', currentCheckoutSession);
    
    const tempProofs = JSON.parse(sessionStorage.getItem(`${currentCheckoutSession}_proofs`) || '{}');
    for (const [tempId, data] of Object.entries(tempProofs)) {
        if (data.public_id) {
            fetch('/api/v1/checkout/delete-temp-proof', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ public_id: data.public_id })
            }).catch(console.error);
        }
    }
    
    sessionStorage.removeItem(`${currentCheckoutSession}_proofs`);
}

// Phase 1: Per-store delivery date/time preferences
let storeDeliveryPreferences = {};

function getStoreDeliveryPreferences() {
    const prefs = JSON.parse(sessionStorage.getItem('deliveryPreferences') || '{}');
    return storeDeliveryPreferences || { selectedDate: prefs.selectedDate, selectedTime: prefs.selectedTime };
}

function setStoreDeliveryPreference(tempId, date, time) {
    if (!storeDeliveryPreferences) {
        storeDeliveryPreferences = {};
    }
    storeDeliveryPreferences[tempId] = { selectedDate: date, selectedTime: time };
    console.log(`✅ Saved delivery preferences for ${tempId}:`, storeDeliveryPreferences[tempId]);
}

function getStoreDeliveryDate(tempId) {
    if (storeDeliveryPreferences[tempId]?.selectedDate) {
        return storeDeliveryPreferences[tempId].selectedDate;
    }
    const prefs = JSON.parse(sessionStorage.getItem('deliveryPreferences') || '{}');
    return prefs.selectedDate || getPhilippineTodayStr();
}

function getStoreDeliveryTime(tempId) {
    if (storeDeliveryPreferences[tempId]?.selectedTime) {
        return storeDeliveryPreferences[tempId].selectedTime;
    }
    const prefs = JSON.parse(sessionStorage.getItem('deliveryPreferences') || '{}');
    return prefs.selectedTime || '';
}

function getTodayDateString() {
    return getPhilippineTodayStr();
}

// Get current time in Philippine timezone (UTC+8)
function getPhilippineTime() {
    const now = new Date();
    return new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Manila' }));
}

function formatDateISOLocal(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, '0');
    const d = String(dateObj.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

// Get today's date in Philippine timezone
function getPhilippineTodayStr() {
    return formatDateISOLocal(getPhilippineTime());
}

function getCheckoutDateLimitWindow() {
    // Build stable local midnights from PH calendar date strings so they
    // compare cleanly with flatpickr day cells.
    const todayStr = getPhilippineTodayStr();
    const [ty, tm, td] = todayStr.split('-').map(Number);
    const today = new Date(ty, tm - 1, td);
    const maxDate = new Date(ty, tm - 1, td + 14);
    return { today, maxDate, todayStr };
}

function getCalendarWeekdayName(dateObj) {
    const names = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    return names[dateObj.getDay()];
}

function extractOpenDaysFromSchedule(schedule) {
    if (!schedule || !Array.isArray(schedule.schedules)) return [];
    const days = new Set();
    schedule.schedules.forEach(entry => {
        (entry.days || []).forEach(day => {
            if (day) days.add(String(day).toLowerCase());
        });
    });
    return Array.from(days);
}

function isCheckoutStoreOpenOnDate(scheduleOrOpenDays, dateObj) {
    let openDays = [];
    if (Array.isArray(scheduleOrOpenDays)) {
        openDays = scheduleOrOpenDays.map(d => String(d).toLowerCase());
    } else {
        openDays = extractOpenDaysFromSchedule(scheduleOrOpenDays);
    }
    if (!openDays.length) return false;
    return openDays.includes(getCalendarWeekdayName(dateObj));
}

function buildCheckoutEnabledDates(openDays, hasSchedule, today, maxDate) {
    const enabled = [];
    const cursor = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const end = new Date(maxDate.getFullYear(), maxDate.getMonth(), maxDate.getDate());
    const openSet = new Set((openDays || []).map(d => String(d).toLowerCase()));

    while (cursor <= end) {
        const weekday = getCalendarWeekdayName(cursor);
        const isOpen = hasSchedule && openSet.has(weekday);
        if (isOpen) {
            enabled.push(new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()));
        }
        cursor.setDate(cursor.getDate() + 1);
    }
    return enabled;
}

function getFirstOpenCheckoutDate(scheduleOrOpenDays, preferredDateStr = null) {
    const { today, maxDate } = getCheckoutDateLimitWindow();

    if (preferredDateStr) {
        const preferred = new Date(preferredDateStr + 'T00:00:00');
        preferred.setHours(0, 0, 0, 0);
        if (preferred >= today && preferred <= maxDate && isCheckoutStoreOpenOnDate(scheduleOrOpenDays, preferred)) {
            return preferredDateStr;
        }
    }

    for (let i = 0; i <= 14; i++) {
        const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
        if (d <= maxDate && isCheckoutStoreOpenOnDate(scheduleOrOpenDays, d)) {
            return formatDateISOLocal(d);
        }
    }
    return null;
}

async function fetchStoreOpenDays(storeId, scheduleHint = null) {
    const fromOrder = extractOpenDaysFromSchedule(scheduleHint);
    if (fromOrder.length) {
        return { openDays: fromOrder, hasSchedule: true };
    }

    try {
        const resp = await fetch('/api/store/' + storeId + '/time-slots?date=' + getPhilippineTodayStr());
        const data = await resp.json();
        if (data && data.success && Array.isArray(data.open_days) && data.open_days.length) {
            return {
                openDays: data.open_days.map(d => String(d).toLowerCase()),
                hasSchedule: true,
            };
        }
        if (data && data.success && data.has_schedule === false) {
            return { openDays: [], hasSchedule: false };
        }
    } catch (e) {
        console.warn('Could not fetch store open days summary:', e);
    }

    const { today } = getCheckoutDateLimitWindow();
    const found = new Set();
    let sawSchedule = false;
    await Promise.all(Array.from({ length: 7 }, async (_, i) => {
        const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
        const dateStr = formatDateISOLocal(d);
        try {
            const resp = await fetch('/api/store/' + storeId + '/time-slots?date=' + dateStr);
            const data = await resp.json();
            if (!data || !data.success) return;
            if (data.has_schedule) sawSchedule = true;
            if (Array.isArray(data.open_days) && data.open_days.length) {
                data.open_days.forEach(day => found.add(String(day).toLowerCase()));
            }
            if (data.is_open && Array.isArray(data.time_slots) && data.time_slots.length) {
                found.add(getCalendarWeekdayName(d));
            }
        } catch (_) { /* ignore */ }
    }));

    return {
        openDays: Array.from(found),
        hasSchedule: sawSchedule || found.size > 0,
    };
}

function ensureFlatpickr() {
    if (typeof flatpickr === 'function') return Promise.resolve();
    if (window.__flatpickrLoading) return window.__flatpickrLoading;
    window.__flatpickrLoading = new Promise(function (resolve, reject) {
        var cssReady = new Promise(function (done) {
            var css = document.createElement('link');
            css.rel = 'stylesheet';
            css.href = 'https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css';
            css.onload = done;
            css.onerror = done;
            document.head.appendChild(css);
        });
        var script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/flatpickr';
        // Wait for CSS too so the first open doesn't measure an unstyled calendar
        script.onload = function () { cssReady.then(resolve); };
        script.onerror = reject;
        document.head.appendChild(script);
    });
    return window.__flatpickrLoading;
}

async function initCheckoutDeliveryDatePicker(order, initialDateStr) {
    try { await ensureFlatpickr(); } catch (e) {}
    const input = document.getElementById('storeDeliveryDate_' + order.temp_id);
    if (!input) return initialDateStr;

    const fetched = await fetchStoreOpenDays(order.store_id, order.store_schedule || null);
    const openDays = fetched.openDays;
    const hasSchedule = fetched.hasSchedule;
    order._openDays = openDays;
    order._hasSchedule = hasSchedule;

    const scheduleKey = hasSchedule ? openDays : (order.store_schedule || openDays);
    const resolvedDate = getFirstOpenCheckoutDate(scheduleKey, initialDateStr) || getPhilippineTodayStr();
    const { today, maxDate } = getCheckoutDateLimitWindow();
    const enabledDates = buildCheckoutEnabledDates(openDays, hasSchedule, today, maxDate);

    console.log('Checkout calendar open days:', {
        storeId: order.store_id,
        hasSchedule: hasSchedule,
        openDays: openDays,
        enabledCount: enabledDates.length,
        resolvedDate: resolvedDate,
    });

    if (input._flatpickr) {
        input._flatpickr.destroy();
    }

    if (typeof flatpickr !== 'function') {
        console.warn('flatpickr missing; date picker fallback active');
        input.removeAttribute('readonly');
        input.setAttribute('type', 'date');
        input.setAttribute('min', formatDateISOLocal(today));
        input.setAttribute('max', formatDateISOLocal(maxDate));
        input.value = resolvedDate;
        input.onchange = (e) => {
            const dateStr = e.target.value;
            if (hasSchedule && !isCheckoutStoreOpenOnDate(openDays, new Date(dateStr + 'T00:00:00'))) {
                showToast('Store is closed on this day. Please pick another date.', 'error');
                const fallback = getFirstOpenCheckoutDate(openDays);
                if (fallback) {
                    e.target.value = fallback;
                    setStoreDeliveryPreference(order.temp_id, fallback, '');
                    fetchCheckoutTimeSlots(order.store_id, order.temp_id, fallback);
                }
                return;
            }
            setStoreDeliveryPreference(order.temp_id, dateStr, '');
            fetchCheckoutTimeSlots(order.store_id, order.temp_id, dateStr);
        };
        setStoreDeliveryPreference(order.temp_id, resolvedDate, storeDeliveryPreferences[order.temp_id]?.selectedTime || '');
        return resolvedDate;
    }

    // Use enable so ONLY open days are selectable. All other days are
    // automatically disabled and greyed by flatpickr.
    const fpConfig = {
        dateFormat: 'Y-m-d',
        defaultDate: resolvedDate,
        minDate: today,
        maxDate: maxDate,
        allowInput: false,
        // Render next to the input so nested modal scroll can't fling the
        // calendar to the top of the viewport.
        static: true,
        position: 'below',
        onOpen: function(selectedDates, dateStr, fp) {
            const card = input.closest('.checkout-delivery-card');
            if (card) card.classList.add('checkout-calendar-open');

            if (!fp.calendarContainer) return;
            requestAnimationFrame(() => {
                const container = getCheckoutScrollContainer(input);
                if (!container) return;
                const containerRect = container.getBoundingClientRect();
                const calRect = fp.calendarContainer.getBoundingClientRect();
                const maxTop = container.scrollHeight - container.clientHeight;
                let desiredTop = null;
                if (calRect.bottom > containerRect.bottom) {
                    desiredTop = container.scrollTop + (calRect.bottom - containerRect.bottom) + 12;
                } else if (calRect.top < containerRect.top) {
                    desiredTop = container.scrollTop + (calRect.top - containerRect.top) - 12;
                }
                if (desiredTop !== null) {
                    container.scrollTo({
                        top: Math.max(0, Math.min(maxTop, desiredTop)),
                        behavior: 'smooth'
                    });
                }
            });
        },
        onClose: function() {
            const card = input.closest('.checkout-delivery-card');
            if (card) card.classList.remove('checkout-calendar-open');
        },
        onDayCreate: function(dObj, dStr, fp, dayElem) {
            const isDisabled = dayElem.classList.contains('flatpickr-disabled')
                || dayElem.classList.contains('notAllowed');
            if (isDisabled) {
                dayElem.classList.add('checkout-day-closed');
                dayElem.title = 'Store closed / unavailable';
                dayElem.setAttribute('aria-disabled', 'true');
                dayElem.style.setProperty('color', '#a89a90', 'important');
                dayElem.style.setProperty('background', '#e8e0d8', 'important');
                dayElem.style.setProperty('text-decoration', 'line-through', 'important');
                dayElem.style.setProperty('opacity', '0.55', 'important');
                dayElem.style.setProperty('cursor', 'not-allowed', 'important');
                dayElem.style.setProperty('pointer-events', 'none', 'important');
            }
        },
        onChange: function(selectedDates, dateStr) {
            if (!dateStr) return;
            const picked = new Date(dateStr + 'T00:00:00');
            if (hasSchedule && openDays.length && !isCheckoutStoreOpenOnDate(openDays, picked)) {
                showToast('Store is closed on this day. Please pick another date.', 'error');
                const fallback = getFirstOpenCheckoutDate(openDays);
                if (fallback && input._flatpickr) {
                    input._flatpickr.setDate(fallback, false);
                    setStoreDeliveryPreference(order.temp_id, fallback, '');
                    fetchCheckoutTimeSlots(order.store_id, order.temp_id, fallback);
                }
                return;
            }
            setStoreDeliveryPreference(order.temp_id, dateStr, '');
            fetchCheckoutTimeSlots(order.store_id, order.temp_id, dateStr);
        }
    };

    if (hasSchedule && openDays.length) {
        fpConfig.enable = enabledDates.length ? enabledDates : [];
    } else {
        fpConfig.disable = [
            function(date) {
                const candidate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
                return candidate < today;
            }
        ];
    }

    flatpickr(input, fpConfig);

    setStoreDeliveryPreference(order.temp_id, resolvedDate, storeDeliveryPreferences[order.temp_id]?.selectedTime || '');
    return resolvedDate;
}

// The checkout modal and its body are both scrollable, so find whichever one
// is actually carrying the overflow before trying to scroll.
function getCheckoutScrollContainer(el) {
    let node = el && el.parentElement;
    while (node && node !== document.body) {
        const overflowY = window.getComputedStyle(node).overflowY;
        const scrolls = (overflowY === 'auto' || overflowY === 'scroll')
            && node.scrollHeight > node.clientHeight + 1;
        if (scrolls) return node;
        node = node.parentElement;
    }
    return null;
}

function scrollCheckoutTargetIntoView(scrollTarget, smooth = true) {
    if (!scrollTarget) return;

    const container = getCheckoutScrollContainer(scrollTarget);
    if (!container) {
        scrollTarget.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'center' });
        return;
    }

    const containerRect = container.getBoundingClientRect();
    const targetRect = scrollTarget.getBoundingClientRect();
    // Keep the warning lower in view so the date/time controls stay visible
    const topGap = Math.min(220, Math.max(72, containerRect.height * 0.4));
    const maxTop = container.scrollHeight - container.clientHeight;
    const desiredTop = container.scrollTop + (targetRect.top - containerRect.top) - topGap;
    container.scrollTo({
        top: Math.max(0, Math.min(maxTop, desiredTop)),
        behavior: smooth ? 'smooth' : 'auto'
    });
}

// Scroll the checkout modal to the delivery warning instead of toasting
function focusCheckoutDeliveryIssue(tempId, messageHtml = null) {
    const closedMsg = document.getElementById(`storeClosedMsg_${tempId}`);
    const dateInput = document.getElementById(`storeDeliveryDate_${tempId}`);
    const deliveryCard = (closedMsg && closedMsg.closest('.checkout-delivery-card'))
        || (dateInput && dateInput.closest('.checkout-delivery-card'));

    if (closedMsg) {
        if (messageHtml) {
            closedMsg.innerHTML = messageHtml;
        }
        closedMsg.style.display = 'block';
    }

    const scrollTarget = closedMsg || deliveryCard || dateInput;

    if (dateInput) {
        try { dateInput.focus({ preventScroll: true }); } catch (e) {}
    }

    // Showing the message reflows the payment step (tall on GCash), so measure
    // on the next frame and re-check once the smooth scroll has settled.
    requestAnimationFrame(() => {
        scrollCheckoutTargetIntoView(scrollTarget, true);

        window.clearTimeout(window.__checkoutIssueScrollTimer);
        window.__checkoutIssueScrollTimer = window.setTimeout(() => {
            const container = getCheckoutScrollContainer(scrollTarget);
            if (!container || !scrollTarget) return;
            const containerRect = container.getBoundingClientRect();
            const targetRect = scrollTarget.getBoundingClientRect();
            const isVisible = targetRect.top >= containerRect.top
                && targetRect.bottom <= containerRect.bottom;
            if (!isVisible) {
                scrollCheckoutTargetIntoView(scrollTarget, false);
            }
        }, 450);
    });

    if (deliveryCard) {
        deliveryCard.classList.add('checkout-delivery-attention');
        window.clearTimeout(deliveryCard._attentionTimer);
        deliveryCard._attentionTimer = window.setTimeout(() => {
            deliveryCard.classList.remove('checkout-delivery-attention');
        }, 1800);
    }
}

// Fetch time slots from store schedule API for checkout modal
async function fetchCheckoutTimeSlots(storeId, tempId, dateStr) {
    const timeSelect = document.getElementById(`storeDeliveryTime_${tempId}`);
    const closedMsg = document.getElementById(`storeClosedMsg_${tempId}`);
    const dateInput = document.getElementById(`storeDeliveryDate_${tempId}`);
    if (!timeSelect) return;
    
    // Show loading state
    timeSelect.innerHTML = '<option value="">Loading...</option>';
    timeSelect.disabled = true;
    if (closedMsg) {
        closedMsg.style.display = 'none';
        closedMsg.innerHTML = '<i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.';
    }
    
    // Get the preferred time from product_details.html (sessionStorage) for pre-selection
    const savedPrefs = JSON.parse(sessionStorage.getItem('deliveryPreferences') || '{}');
    const preferredTime = storeDeliveryPreferences[tempId]?.selectedTime || savedPrefs.selectedTime || '';
    const order = (checkoutOrders || []).find(o => o.temp_id === tempId) || null;
    const openDaysOrSchedule = (order && Array.isArray(order._openDays) && order._openDays.length)
        ? order._openDays
        : (order ? (order.store_schedule || null) : null);

    // Hard-lock past / closed days before calling the API
    const selectedDateObj = new Date(`${dateStr}T00:00:00`);
    selectedDateObj.setHours(0, 0, 0, 0);
    const { today } = getCheckoutDateLimitWindow();
    const knownOpenDays = Array.isArray(openDaysOrSchedule)
        ? openDaysOrSchedule
        : extractOpenDaysFromSchedule(openDaysOrSchedule);
    if (selectedDateObj < today || (knownOpenDays.length && !isCheckoutStoreOpenOnDate(knownOpenDays, selectedDateObj))) {
        const fallback = getFirstOpenCheckoutDate(openDaysOrSchedule);
        timeSelect.innerHTML = '<option value="">— Closed —</option>';
        timeSelect.disabled = true;
        if (closedMsg) {
            closedMsg.style.display = 'block';
            closedMsg.innerHTML = selectedDateObj < today
                ? '<i class="ri-calendar-close-line"></i> Past dates are locked. Please choose today or a future open day.'
                : '<i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.';
        }
        if (fallback && fallback !== dateStr) {
            if (dateInput && dateInput._flatpickr) {
                dateInput._flatpickr.setDate(fallback, true);
            } else if (dateInput) {
                dateInput.value = fallback;
                setStoreDeliveryPreference(tempId, fallback, '');
                return fetchCheckoutTimeSlots(storeId, tempId, fallback);
            }
        }
        return;
    }
    
    try {
        const resp = await fetch(`/api/store/${storeId}/time-slots?date=${dateStr}`);
        const data = await resp.json();
        
        if (data.success) {
            const reason = data.block_reason || null;
            const reasonMessage = (code) => {
                if (code === 'no_schedule') return '<i class="ri-alert-line"></i> This store has not set delivery hours yet.';
                if (code === 'order_cutoff') return '<i class="ri-time-line"></i> Same-day ordering is closed. Please choose another open day.';
                if (code === 'lead_time') return '<i class="ri-time-line"></i> Remaining slots are inside the prep window. Please choose a later slot or another date.';
                if (code === 'slots_passed') return '<i class="ri-time-line"></i> All delivery slots for today have passed. Please select another open day.';
                return '<i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.';
            };

            if (!data.has_schedule) {
                timeSelect.innerHTML = '<option value="">Hours not set</option>';
                timeSelect.disabled = true;
                if (closedMsg) {
                    closedMsg.style.display = 'block';
                    closedMsg.innerHTML = reasonMessage('no_schedule');
                }
                setStoreDeliveryPreference(tempId, dateStr, '');
                return;
            }

            if (data.time_slots && data.time_slots.length > 0) {
                timeSelect.innerHTML = '';
                let foundPreferred = false;
                data.time_slots.forEach(slot => {
                    const opt = document.createElement('option');
                    opt.value = slot.value;
                    opt.textContent = slot.label;
                    if (slot.value === preferredTime) {
                        opt.selected = true;
                        foundPreferred = true;
                    }
                    timeSelect.appendChild(opt);
                });
                if (!foundPreferred) {
                    const firstAvail = [...timeSelect.options].find(o => o.value);
                    if (firstAvail) firstAvail.selected = true;
                }
                timeSelect.disabled = false;
                if (closedMsg) closedMsg.style.display = 'none';
                setStoreDeliveryPreference(tempId, dateStr, timeSelect.value);
                return;
            }

            timeSelect.innerHTML = '<option value="">No slots</option>';
            timeSelect.disabled = true;
            if (closedMsg) {
                closedMsg.style.display = 'block';
                closedMsg.innerHTML = reasonMessage(reason);
            }
            setStoreDeliveryPreference(tempId, dateStr, '');
            return;
        }
    } catch (e) {
        console.warn('Could not fetch store time slots:', e);
    }

    timeSelect.innerHTML = '<option value="">Hours not set</option>';
    timeSelect.disabled = true;
    if (closedMsg) {
        closedMsg.style.display = 'block';
        closedMsg.innerHTML = '<i class="ri-alert-line"></i> Could not load delivery hours. Please try again.';
    }
    setStoreDeliveryPreference(tempId, dateStr, '');
}

function cancelCheckout(showWarning = false) {
    const sessionId = sessionStorage.getItem('active_checkout');
    if (sessionId) {
        const proofs = JSON.parse(sessionStorage.getItem(`${sessionId}_proofs`) || '{}');
        for (const [tempId, data] of Object.entries(proofs)) {
            if (data.public_id) {
                fetch('/api/v1/checkout/delete-temp-proof', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ public_id: data.public_id })
                }).catch(console.error);
                console.log(`🗑️ Deleted orphaned proof: ${data.public_id}`);
            }
        }
        sessionStorage.removeItem(`${sessionId}_proofs`);
        sessionStorage.removeItem('active_checkout');
    }
    
    if (showWarning) {
        showToast('Checkout cancelled');
    }
    currentCheckoutSession = null;
}

function finalizeCheckoutSession() {
    const sessionId = sessionStorage.getItem('active_checkout');
    if (sessionId) {
        sessionStorage.removeItem(`${sessionId}_proofs`);
        sessionStorage.removeItem('active_checkout');
    }

    Object.keys(uploadedProofData || {}).forEach(tempId => {
        localStorage.removeItem(`checkout_proof_${tempId}`);
    });

    currentCheckoutSession = null;
    uploadedProofs = {};
    uploadedProofData = {};
}

function updateProgressIndicator(step) {
    const steps = document.querySelectorAll('.progress-step');
    const lines = document.querySelectorAll('.progress-line');
    
    steps.forEach((stepEl, idx) => {
        const stepNum = idx + 1;
        stepEl.classList.remove('active', 'completed');
        if (stepNum === step) {
            stepEl.classList.add('active');
        } else if (stepNum < step) {
            stepEl.classList.add('completed');
        }
        lines.forEach((line, lineIdx) => {
            if (lineIdx < step - 1) {
                line.classList.add('active');
            } else {
                line.classList.remove('active');
            }
        });
    });
}

// ===== PERSISTENCE FUNCTIONS FOR UPLOADED PROOFS =====
function saveProofData(tempId, proofData) {
    uploadedProofs[tempId] = proofData.url;
    uploadedProofData[tempId] = {
        url: proofData.url,
        preview: proofData.preview,
        public_id: proofData.public_id,
        timestamp: Date.now()
    };
    localStorage.setItem(`checkout_proof_${tempId}`, JSON.stringify(uploadedProofData[tempId]));
}

function loadProofData(tempId) {
    const saved = localStorage.getItem(`checkout_proof_${tempId}`);
    if (saved) {
        try {
            const data = JSON.parse(saved);
            uploadedProofData[tempId] = data;
            uploadedProofs[tempId] = data.url;
            return data;
        } catch (e) {
            console.error('Error loading proof data:', e);
        }
    }
    return null;
}

function clearProofData(tempId) {
    delete uploadedProofs[tempId];
    delete uploadedProofData[tempId];
    localStorage.removeItem(`checkout_proof_${tempId}`);
}

function getProofState(tempId) {
    let uploaded = null;

    if (uploadedProofs[tempId]) {
        uploaded = uploadedProofData[tempId] || { url: uploadedProofs[tempId] };
    } else {
        uploaded = loadProofData(tempId);
    }

    const pending = uploadedProofData[tempId]?.file ? uploadedProofData[tempId] : null;

    return {
        uploaded,
        pending,
        hasUploaded: !!uploaded?.url,
        hasPending: !!pending?.file,
        previewSrc: pending?.preview || uploaded?.preview || uploaded?.url || ''
    };
}

function getOrderPaymentMethod(order) {
    if (!order || !order.temp_id) return 'gcash';
    const selected = selectedPaymentMethods[order.temp_id];
    const gcashEnabled = order.allow_gcash !== false;
    const codEnabled = order.allow_cod === true;
    if (selected === 'cod' && codEnabled) return 'cod';
    if (selected === 'gcash' && gcashEnabled) return 'gcash';
    if (gcashEnabled) return 'gcash';
    if (codEnabled) return 'cod';
    return 'gcash';
}

function setOrderPaymentMethod(tempId, method) {
    if (!tempId) return;
    selectedPaymentMethods[tempId] = (method === 'cod') ? 'cod' : 'gcash';
}

function updateCheckoutPaymentAction() {
    const nextBtn = document.getElementById('checkoutNextBtn');
    const order = checkoutOrders[currentOrderIndex];
    if (!nextBtn || !order) return;

    const paymentMethod = getOrderPaymentMethod(order);
    if (paymentMethod === 'cod') {
        nextBtn.textContent = currentOrderIndex < checkoutOrders.length - 1 ? 'Next Order' : 'Complete';
        nextBtn.disabled = false;
        return;
    }

    const proofState = getProofState(order.temp_id);

    if (proofState.hasUploaded) {
        nextBtn.textContent = currentOrderIndex < checkoutOrders.length - 1 ? 'Next Order' : 'Complete';
        nextBtn.disabled = false;
        return;
    }

    if (proofState.hasPending) {
        nextBtn.textContent = currentOrderIndex < checkoutOrders.length - 1 ? 'Upload & Next Order' : 'Upload & Complete';
        nextBtn.disabled = false;
        return;
    }

    nextBtn.textContent = 'Waiting for upload';
    nextBtn.disabled = true;
}

// Initialize cart on page load
document.addEventListener('DOMContentLoaded', function() {
    loadCart();

    
});

function persistLocalCart() {
    // localStorage is only the guest cart store. Never mirror the server cart there.
    if (HAS_SERVER_CART) return;
    try {
        localStorage.setItem('cart', JSON.stringify(Array.isArray(cart) ? cart : []));
    } catch (e) {
        console.warn('Could not save guest cart', e);
    }
}

function guestLineAddonTotal(item) {
    return (Array.isArray(item && item.addons) ? item.addons : []).reduce(function (s, a) {
        const units = Math.max(1, Number(a.quantity || a.units || 1));
        return s + Number(a.price || 0) * units;
    }, 0);
}

function normalizeGuestAddons(product) {
    const fromObjects = Array.isArray(product && product.addons) ? product.addons : [];
    const fromIds = Array.isArray(product && product.addon_option_ids) ? product.addon_option_ids : [];
    const byId = {};
    const order = [];
    function upsert(raw) {
        if (raw == null) return;
        let oid;
        let qty = 1;
        let name = '';
        let price = 0;
        let image = '';
        let group = '';
        if (typeof raw === 'object') {
            oid = Number(raw.addon_option_id != null ? raw.addon_option_id : raw.id);
            qty = Math.max(1, Number(raw.quantity || raw.units || 1) || 1);
            name = raw.name || '';
            price = Number(raw.price || 0) || 0;
            image = raw.image_url || '';
            group = raw.group_name || '';
        } else {
            oid = Number(raw);
        }
        if (!Number.isFinite(oid) || oid <= 0) return;
        if (!byId[oid]) {
            order.push(oid);
            byId[oid] = {
                id: oid,
                addon_option_id: oid,
                name: name || 'Add-on',
                price: price,
                quantity: 0,
                image_url: image || null,
                group_name: group || ''
            };
        }
        byId[oid].quantity += qty;
        if (name) byId[oid].name = name;
        if (price) byId[oid].price = price;
        if (image) byId[oid].image_url = image;
        if (group) byId[oid].group_name = group;
    }
    fromObjects.forEach(upsert);
    // addon_option_ids is the same selection as `addons` when both are present.
    // Only use ids as a fallback so guest badge/qty is not doubled.
    if (!fromObjects.length) {
        fromIds.forEach(upsert);
    }
    return order.map(function (id) { return byId[id]; });
}

function mergeGuestAddonLists(existing, incoming) {
    return normalizeGuestAddons({
        addons: (existing || []).concat(incoming || [])
    });
}

function guestAddonPayload(addons) {
    return (addons || []).map(function (a) {
        return {
            addon_option_id: a.addon_option_id != null ? a.addon_option_id : a.id,
            quantity: Math.max(1, Number(a.quantity || a.units || 1) || 1)
        };
    }).filter(function (row) {
        return Number.isFinite(Number(row.addon_option_id)) && Number(row.addon_option_id) > 0;
    });
}

function showCartSyncModal(guestCart) {
    const modal = document.getElementById('cartSyncModal');
    const preview = document.getElementById('cartPreview');
    
    const total = guestCart.reduce((sum, item) => {
        return sum + (Number(item.price || 0) * Number(item.quantity || 0)) + guestLineAddonTotal(item);
    }, 0);
    
    let previewHTML = '';
    guestCart.forEach(item => {
        const addons = Array.isArray(item.addons) ? item.addons : [];
        const addonMeta = addons.length
            ? addons.map(function (a) {
                const units = Math.max(1, Number(a.quantity || a.units || 1) || 1);
                return (a.name || 'Add-on') + (units > 1 ? (' ×' + units) : '');
            }).join(', ')
            : '';
        const lineTotal = (Number(item.price || 0) * Number(item.quantity || 0)) + guestLineAddonTotal(item);
        previewHTML += `
            <div class="cart-preview-item">
                <div class="cart-preview-item-image">
                    ${item.image_url ? `<img src="${item.image_url}" alt="${item.name}">` : '<i class="ri-image-line"></i>'}
                </div>
                <div class="cart-preview-item-details">
                    <div class="cart-preview-item-name">${item.name}</div>
                    <div class="cart-preview-item-meta">Qty: ${item.quantity} • ${item.store_name || 'Flower Shop'}${addonMeta ? `<br>+ ${addonMeta}` : ''}</div>
                </div>
                <div class="cart-preview-item-price">₱${lineTotal.toFixed(2)}</div>
            </div>
        `;
    });
    
    previewHTML += `
        <div class="cart-preview-total">
            <span class="cart-preview-total-label">Total:</span>
            <span class="cart-preview-total-value">₱${total.toFixed(2)}</span>
        </div>
    `;
    
    preview.innerHTML = previewHTML;
    modal.classList.add('active');
}

function declineCartSync() {
    localStorage.removeItem('cart');
    document.getElementById('cartSyncModal').classList.remove('active');
    showToast('Guest cart cleared. Start shopping with your account!');
}

function loadCart() {
    
    loadCartFromLocal();
    
}

function cartBadgeCount(items) {
    return (Array.isArray(items) ? items : []).reduce(function (s, i) {
        const qty = Number(i.quantity || 0) || 0;
        const addonUnits = (Array.isArray(i.addons) ? i.addons : []).reduce(function (as, a) {
            return as + Math.max(1, Number(a.quantity || a.units || 1) || 1);
        }, 0);
        return s + qty + addonUnits;
    }, 0);
}

function updateCartCount() {
    let source = Array.isArray(cart) ? cart : [];
    if (!HAS_SERVER_CART) {
        try {
            const parsed = JSON.parse(localStorage.getItem('cart') || '[]');
            if (Array.isArray(parsed)) source = parsed;
        } catch (e) {}
    }
    const total = cartBadgeCount(source);
    const badge = document.getElementById('cartCount');
    if (!badge) return;
    badge.textContent = total > 99 ? '99+' : String(total);
    const empty = total <= 0;
    badge.classList.toggle('is-empty', empty);
    badge.setAttribute('aria-hidden', empty ? 'true' : 'false');
}
window.updateCartCount = updateCartCount;

function updateChatFabVisibility() {
    const chatFab = document.getElementById('chat-fab');
    if (!chatFab) return;

    const cartOpen = !!document.getElementById('cartSidebar')?.classList.contains('active');
    const modalOpen = !!document.querySelector(
        '.modal-overlay.active, .sync-modal-overlay.active, .qa-overlay.open, .app-confirm-overlay.show, .orders-status-sheet-overlay.active'
    );
    chatFab.classList.toggle('cart-open-hidden', cartOpen || modalOpen);
}

function updateCartDisplay() {
    const cartItems = document.getElementById('cartItems');
    const cartTotal = document.getElementById('cartTotal');
    const cartSubtotal = document.getElementById('cartSubtotal');
    if (!cartItems) {
        if (typeof updateCartCount === 'function') updateCartCount();
        return;
    }

    if (!cart.length) {
        cartItems.innerHTML = `
            <div class="empty-state">
                <i class="ri-shopping-bag-line empty-state-icon"></i>
                <p>Your basket is empty</p>
                <p style="font-size:13px;margin-top:0.25rem;font-family:var(--font-sans);">Add some blooms to get started</p>
            </div>`;
        cartTotal.textContent = '₱0.00';
        if (cartSubtotal) cartSubtotal.textContent = '₱0.00';
        return;
    }

    const storesMap = {};
    cart.forEach((item, index) => {
        const store = item.store_name || 'Unknown Store';
        if (!storesMap[store]) storesMap[store] = [];
        storesMap[store].push({ ...item, cartIndex: index });
    });

    let html = '';
    let total = 0;

    Object.entries(storesMap).forEach(([storeName, storeItems]) => {
        const storeTotal = storeItems.reduce((sum, item) => {
            if (!item.is_selected) return sum;
            const unitAddons = (Array.isArray(item.addons) ? item.addons : [])
                .reduce((s, a) => {
                    const units = Math.max(1, Number(a.quantity || a.units || 1));
                    return s + Number(a.price || 0) * units;
                }, 0);
            return sum + (item.price * item.quantity) + unitAddons;
        }, 0);
        total += storeTotal;

        const storeItemCount = storeItems.reduce((n, item) => {
            // Count the product line plus each attached add-on row
            const addonRows = Array.isArray(item.addons) ? item.addons.length : 0;
            return n + 1 + addonRows;
        }, 0);

        html += `
            <div class="cart-store-group">
                <div class="cart-store-group__header">
                    <input type="checkbox" class="store-checkbox" data-store="${storeName}" onclick="toggleStore('${storeName}')" ${isStoreFullySelected(storeName, storeItems) ? 'checked' : ''} style="cursor: pointer;">
                    <div style="flex: 1; min-width: 0;">
                        <div class="cart-store-group__name">${storeName}</div>
                        <div class="cart-store-group__count">${storeItemCount} item${storeItemCount !== 1 ? 's' : ''}</div>
                    </div>
                    <div class="cart-store-group__total">₱${storeTotal.toFixed(2)}</div>
                </div>
                <div class="cart-store-group__body">
        `;

        storeItems.forEach((item, idx) => {
            const isVariant = !!item.variant_id;
            const maxStock = Number.isFinite(Number(item.stock_quantity))
                ? Number(item.stock_quantity)
                : null;
            const atMax = maxStock != null && item.quantity >= maxStock;
            const minusDisabled = item.quantity <= 1 ? 'disabled' : '';
            const plusDisabled = atMax ? 'disabled' : '';
            const addons = Array.isArray(item.addons) ? item.addons : [];
            const unitAddons = addons.reduce((s, a) => {
                const units = Math.max(1, Number(a.quantity || a.units || 1));
                return s + Number(a.price || 0) * units;
            }, 0);
            // Add-on prices stay fixed; +/- only changes flower/variant qty
            const addonsTotal = unitAddons;
            const lineTotal = (item.price * item.quantity) + addonsTotal;
            const addonsHtml = addons.length
                ? `<div class="cart-item-addons">
                    ${addons.map(a => {
                        const aName = a.name || 'Add-on';
                        const aPrice = Number(a.price || 0);
                        const aUnits = Math.max(1, Number(a.quantity || a.units || 1));
                        const aGroup = a.group_name ? `${a.group_name}: ` : '';
                        const optionId = a.addon_option_id != null ? a.addon_option_id : a.id;
                        const aImg = a.image_url
                            ? `<img src="${a.image_url}" alt="${aName}" style="width:22px;height:22px;object-fit:cover;border-radius:5px;border:1px solid var(--border);flex-shrink:0;">`
                            : `<div style="width:22px;height:22px;border-radius:5px;border:1px solid var(--border);background:var(--cream);flex-shrink:0;display:flex;align-items:center;justify-content:center;"><i class="ri-gift-line" style="font-size:11px;color:var(--muted);"></i></div>`;
                        return `<div class="cart-addon-row">
                            ${aImg}
                            <span class="cart-addon-row__name">+ ${aGroup}${aName}${aUnits > 1 ? ` ×${aUnits}` : ''}</span>
                            <span class="cart-addon-row__price">₱${(aPrice * aUnits).toFixed(2)}</span>
                            <button type="button" class="cart-addon-remove" title="Remove add-on" aria-label="Remove ${aName}"
                                onclick="event.stopPropagation(); removeCartAddon(${item.cartIndex}, ${Number(optionId)})">
                                <i class="ri-close-line"></i>
                            </button>
                        </div>`;
                    }).join('')}
                </div>`
                : '';
            html += `
                <div class="cart-item" data-index="${item.cartIndex}" data-product-id="${item.id}" data-variant-id="${item.variant_id || ''}">
                    <input type="checkbox" class="item-checkbox" data-index="${item.cartIndex}" onchange="toggleItem(${item.cartIndex})" ${item.is_selected ? 'checked' : ''} style="cursor: pointer; margin-top: 22px; flex-shrink: 0;">
                    <div class="cart-item-image">
                        ${item.image_url ? `<img src="${item.image_url}" alt="${item.name}">` : '<i class="ri-image-line" style="font-size: 24px; display: flex; align-items: center; justify-content: center; height: 100%; color: var(--muted);"></i>'}
                    </div>
                    <div class="cart-item-info">
                        <div class="cart-item-name">${item.name}</div>
                        ${isVariant ? '<div class="cart-item-variant-tag">Variant</div>' : ''}
                        <div class="cart-item-price-meta">
                            <span class="cart-item-price-current">₱${item.price.toFixed(2)} each</span>
                            ${item.original_price ? `<span class="cart-item-price-original">₱${item.original_price.toFixed(2)}</span>` : ''}
                            ${item.discount_pct ? `<span class="cart-item-discount-chip">${item.discount_pct}% off</span>` : ''}
                        </div>
                        <div class="cart-qty-control" aria-label="Product quantity">
                            <button type="button" class="quantity-btn" onclick="updateQuantity(${item.cartIndex},-1)" aria-label="Decrease product quantity" ${minusDisabled}>−</button>
                            <span class="cart-qty-value" aria-live="polite">${item.quantity}</span>
                            <button type="button" class="quantity-btn" onclick="updateQuantity(${item.cartIndex},1)" aria-label="Increase product quantity" ${plusDisabled}>+</button>
                        </div>
                        ${addonsHtml}
                    </div>
                    <div class="cart-item-side">
                        <div class="cart-item-line-total">₱${lineTotal.toFixed(2)}</div>
                        <button type="button" class="cart-item-remove" onclick="removeFromCart(${item.cartIndex})" aria-label="Remove item"><i class="ri-delete-bin-line"></i></button>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    cartItems.innerHTML = html;
    cartTotal.textContent = `₱${total.toFixed(2)}`;
    if (cartSubtotal) cartSubtotal.textContent = `₱${total.toFixed(2)}`;
}

function isStoreFullySelected(storeName, storeItems) {
    return storeItems.length > 0 && storeItems.every(item => item.is_selected);
}

async function toggleStore(storeName) {
    const storeCheckbox = document.querySelector(`input.store-checkbox[data-store="${storeName}"]`);
    const isChecked = storeCheckbox.checked;

    cart.forEach(item => {
        if (item.store_name === storeName) {
            item.is_selected = isChecked;
        }
    });
    updateCartDisplay();

    try {
        const token = await getAuthToken();
        const storeItem = cart.find(item => item.store_name === storeName);
        if (!storeItem || !storeItem.store_id) return;

        const response = await fetch(`/api/v1/checkout/cart/store/${storeItem.store_id}/toggle`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({ selected: isChecked })
        });

        if (!response.ok) {
            throw new Error('Failed to update store selection');
        }
    } catch (error) {
        console.error('Store selection error:', error);
        showToast('Could not update selected items');
        loadCart();
    }
}

async function toggleItem(index) {
    const item = cart[index];
    if (!item) return;

    const checkbox = document.querySelector(`input.item-checkbox[data-index="${index}"]`);
    item.is_selected = checkbox ? checkbox.checked : !item.is_selected;
    updateCartDisplay();

    try {
        const token = await getAuthToken();
        const response = await fetch(`/api/v1/checkout/cart/items/${item.cart_item_id}/toggle`, {
            method: 'PUT',
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        if (!response.ok) {
            throw new Error('Failed to update item selection');
        }
    } catch (error) {
        console.error('Item selection error:', error);
        showToast('Could not update selected item');
        loadCart();
    }
}

function inspectCart() {
    console.log('Current cart:', cart);
    return cart;
}
window.inspectCart = inspectCart;

function addToCart(product) {
    if (SHOPPING_DISABLED) {
        showToast('Cart and checkout are disabled for seller/admin accounts', 'error');
        return Promise.resolve(false);
    }
    if (!product || !product.id) {
        showToast('Error: Invalid product', 'error');
        return Promise.resolve(false);
    }

    // Normalise price to always use the effective (sale) price
    if (product.effective_price != null && product.effective_price < product.price) {
        product = Object.assign({}, product, { price: product.effective_price });
    }

    const displayName = product.name || 'Product';

    if (Array.isArray(product.addons)) {
        for (let i = 0; i < product.addons.length; i++) {
            const a = product.addons[i];
            if (a && a.stock !== undefined && a.stock !== null) {
                const s = Number(a.stock);
                if (s <= 0) {
                    const msg = `Add-on "${a.name || 'item'}" is out of stock.`;
                    if (typeof showCartActionError === 'function') {
                        showCartActionError(msg);
                    } else {
                        showToast(msg, 'error');
                    }
                    return Promise.resolve(false);
                }
            }
        }
    }
    
    
    addToCartLocalStorage(product);
    showToast(`Added to basket — ${displayName}`);
    return Promise.resolve(true);
    
}

function addToCartLocalStorage(product) {
    try {
        const parsed = JSON.parse(localStorage.getItem('cart') || '[]');
        cart = Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        cart = [];
    }

    // Use effective_price when set (sale price), otherwise regular price
    const effectivePrice = product.effective_price ?? product.price;
    const originalPrice  = (product.special_price && product.special_price < product.price)
        ? product.price : null;
    const discountPct    = originalPrice
        ? Math.round((1 - effectivePrice / originalPrice) * 100) : null;

    const addons = normalizeGuestAddons(product);
    const cartItem = {
        id: product.id,
        variant_id: product.variant_id || null,
        name: product.name,
        quantity: product.quantity || 1,
        price: effectivePrice,
        original_price: originalPrice,
        discount_pct: discountPct,
        store_id: product.store_id,
        store_name: product.store_name || 'Flower Shop',
        image_url: product.image_url || null,
        is_selected: true,
        addons: addons,
        addon_option_ids: guestAddonPayload(addons),
        addons_total: addons.reduce(function (s, a) {
            return s + Number(a.price || 0) * Math.max(1, Number(a.quantity || 1));
        }, 0)
    };
    
    let existingIndex = -1;
    for (let i = 0; i < cart.length; i++) {
        const item = cart[i];
        if (!cartItem.variant_id && !item.variant_id && item.id === cartItem.id) {
            existingIndex = i;
            break;
        } else if (cartItem.variant_id && item.variant_id && item.id === cartItem.id && item.variant_id === cartItem.variant_id) {
            existingIndex = i;
            break;
        }
    }
    
            if (existingIndex > -1) {
        cart[existingIndex].quantity += cartItem.quantity;
        const incomingAddons = cartItem.addons || [];
        if (incomingAddons.length) {
            const existingAddons = Array.isArray(cart[existingIndex].addons)
                ? cart[existingIndex].addons
                : [];
            const mergedAddons = existingAddons.length
                ? mergeGuestAddonLists(existingAddons, incomingAddons)
                : incomingAddons;
            cart[existingIndex].addons = mergedAddons;
            cart[existingIndex].addon_option_ids = guestAddonPayload(mergedAddons);
            cart[existingIndex].addons_total = mergedAddons.reduce(function (s, a) {
                return s + Number(a.price || 0) * Math.max(1, Number(a.quantity || 1));
            }, 0);
        }
    } else {
        cart.push(cartItem);
    }
    
    persistLocalCart();
    updateCartCount();
    updateCartDisplay();
}

function loadCartFromLocal() {
    try {
        const parsed = JSON.parse(localStorage.getItem('cart') || '[]');
        cart = Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        cart = [];
    }
    cart = cart.map(item => ({
        ...item,
        variant_id: item.variant_id || null,
        addons: Array.isArray(item.addons) ? item.addons : [],
        addon_option_ids: Array.isArray(item.addon_option_ids)
            ? item.addon_option_ids
            : guestAddonPayload(item.addons)
    }));
    updateCartCount();
    updateCartDisplay();
}

function updateQuantity(index, change) {
    const item = cart[index];
    if (!item) return;

    const newQuantity = item.quantity + change;
    if (newQuantity <= 0) {
        removeFromCart(index);
        return;
    }

    const maxStock = Number.isFinite(Number(item.stock_quantity))
        ? Number(item.stock_quantity)
        : null;
    if (maxStock != null && newQuantity > maxStock) {
        if (typeof showToast === 'function') {
            showToast('Only ' + maxStock + ' available for this item', 'error');
        }
        return;
    }

    // Instant local update so users can tap +/- quickly
    item.quantity = newQuantity;
    if (Array.isArray(item.addons) && item.addons.length) {
        const unitAddons = item.addons.reduce((s, a) => {
            const units = Math.max(1, Number(a.quantity || a.units || 1));
            return s + Number(a.price || 0) * units;
        }, 0);
        item.addons_total = unitAddons;
    }
    persistLocalCart();
    updateCartCount();
    updateCartDisplay();

    
}

function scheduleCartQtySync(cartItemId, quantity) {
    const key = String(cartItemId);
    cartQtyPending[key] = quantity;
    if (cartQtyTimers[key]) clearTimeout(cartQtyTimers[key]);
    cartQtyTimers[key] = setTimeout(function () {
        flushCartQtySync(key);
    }, 400);
}

function flushCartQtySync(key) {
    const quantity = cartQtyPending[key];
    delete cartQtyPending[key];
    delete cartQtyTimers[key];
    if (quantity == null) return;

    fetch(`/api/cart/items/${key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity: quantity })
    })
    .then(function (response) { return response.json(); })
    .then(function (data) {
        // A newer pending edit exists — ignore this stale response
        if (cartQtyPending[key] != null || cartQtyTimers[key]) return;
        if (!data.success) {
            if (typeof showToast === 'function') {
                showToast(data.error || data.message || 'Could not update quantity', 'error');
            }
            loadCart();
        }
    })
    .catch(function () {
        if (cartQtyPending[key] != null || cartQtyTimers[key]) return;
        if (typeof showToast === 'function') {
            showToast('Could not update quantity', 'error');
        }
        loadCart();
    });
}

function updateQuantityLocal(index, change) {
    cart[index].quantity += change;
    if (cart[index].quantity <= 0) cart.splice(index, 1);
    persistLocalCart();
    updateCartCount();
    updateCartDisplay();
}

function removeFromCart(index) {
    const item = cart[index];
    if (!item) return;

    
    removeFromCartLocal(index);
}

function removeFromCartLocal(index) {
    const removedItem = cart[index];
    cart.splice(index, 1);
    persistLocalCart();
    updateCartCount();
    updateCartDisplay();
    showToast(`Removed from basket — ${removedItem.name}`);
}

function removeCartAddon(cartIndex, addonOptionId) {
    const item = cart[cartIndex];
    if (!item || !Array.isArray(item.addons) || !item.addons.length) return;

    const optionId = Number(addonOptionId);
    const removed = item.addons.find(function (a) {
        const id = a.addon_option_id != null ? a.addon_option_id : a.id;
        return Number(id) === optionId;
    });
    if (!removed) return;

    item.addons = item.addons.filter(function (a) {
        const id = a.addon_option_id != null ? a.addon_option_id : a.id;
        return Number(id) !== optionId;
    });
    const unitAddons = item.addons.reduce(function (s, a) {
        const units = Math.max(1, Number(a.quantity || a.units || 1));
        return s + Number(a.price || 0) * units;
    }, 0);
    item.addons_total = unitAddons;

    persistLocalCart();
    updateCartCount();
    updateCartDisplay();
    showToast('Removed add-on — ' + (removed.name || 'Add-on'));

    
}

async function clearCart() {
    if (!await window.openConfirmModal('Clear your entire basket?')) return;
    
    
    clearCartLocal();
    
}

function clearCartLocal() {
    cart = [];
    persistLocalCart();
    updateCartCount();
    updateCartDisplay();
    showToast('Basket cleared');
}

function closeCart() {
    const sidebar = document.getElementById('cartSidebar');
    const overlay = document.getElementById('cartOverlay');
    if (sidebar) sidebar.classList.remove('active');
    if (overlay) overlay.classList.remove('active');
    if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();
}

function showCheckoutModal() {
    closeCart();
    document.getElementById('checkoutModal')?.classList.add('active');
}

function toggleCart() {
    if (SHOPPING_DISABLED) {
        showToast('Cart is disabled for seller/admin accounts', 'error');
        return;
    }
    // If quick-add left the header disabled, restore clicks first.
    if (document.body.classList.contains('qa-picker-open') && typeof closeQuickAddPicker === 'function') {
        closeQuickAddPicker();
    }
    const sidebar = document.getElementById('cartSidebar');
    const overlay = document.getElementById('cartOverlay');
    if (!sidebar || !overlay) return;
    sidebar.classList.toggle('active');
    overlay.classList.toggle('active');
    updateChatFabVisibility();
    if (sidebar.classList.contains('active')) updateCartDisplay();
}

document.getElementById('closeCart')?.addEventListener('click', toggleCart);

function toggleUserMenu(event) {
    if (event) event.stopPropagation();
    if (document.body.classList.contains('qa-picker-open') && typeof closeQuickAddPicker === 'function') {
        closeQuickAddPicker();
    }
    const userMenu = document.getElementById('userMenu');
    if (!userMenu) return;
    userMenu.classList.toggle('show');
}

const SELLER_NAV_DEBUG = (() => {
    try {
        const q = new URLSearchParams(window.location.search).get('seller_nav_debug');
        if (q === '1') localStorage.setItem('seller_nav_debug', '1');
        if (q === '0') localStorage.removeItem('seller_nav_debug');
        return q === '1' || localStorage.getItem('seller_nav_debug') === '1';
    } catch (_) {
        return false;
    }
})();

function sellerNavDebug(step, data) {
    if (!SELLER_NAV_DEBUG) return;
    try {
        console.log(`🧭 SELLER NAV DEBUG: ${step}`, data || {});
    } catch (_) {
        console.log(`🧭 SELLER NAV DEBUG: ${step}`);
    }
}

function goToSellerSignup(event, href) {
    sellerNavDebug('goToSellerSignup invoked', {
        href,
        currentPath: window.location.pathname + window.location.search,
        role: 'guest',
        defaultPrevented: !!event?.defaultPrevented,
    });
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!href) {
        sellerNavDebug('missing href; abort');
        return false;
    }
    sellerNavDebug('navigating with location.assign', { href });
    window.location.assign(href);
    return false;
}

document.addEventListener('click', function(event) {
    const a = event.target && event.target.closest ? event.target.closest('a[href*="/seller/signup"]') : null;
    if (!a) return;
    sellerNavDebug('anchor click captured', {
        href: a.href,
        text: (a.textContent || '').trim(),
        defaultPrevented: event.defaultPrevented,
    });
}, true);

// Close user menu when clicking outside
document.addEventListener('click', function(event) {
    const userMenu = document.getElementById('userMenu');
    const userBtn = document.getElementById('userAvatarBtn');
    if (userBtn && userMenu && !userBtn.contains(event.target) && !userMenu.contains(event.target)) {
        userMenu.classList.remove('show');
    }
});

async function fetchCheckoutAddresses() {
    const response = await fetch('/api/account/addresses');
    const result = await response.json();

    if (!response.ok || !result.success) {
        throw new Error(result.error || 'Failed to load addresses');
    }

    return Array.isArray(result.addresses) ? result.addresses : [];
}

async function fetchCheckoutActiveOrderLimit() {
    const headers = { 'Authorization': 'Bearer ' + (await getAuthToken()) };
    const response = await fetch('/api/v1/checkout/active-order-limit', {
        headers,
        credentials: 'same-origin',
    });
    const result = await response.json().catch(function () { return {}; });
    if (result && (result.blocked || result.code === 'active_order_limit')) {
        return result;
    }
    if (!response.ok) {
        throw new Error(result.error || 'Could not verify active order limit');
    }
    return result;
}

function isActiveOrderLimitPayload(data) {
    if (!data) return false;
    if (data.blocked === true || data.code === 'active_order_limit') return true;
    const msg = String(data.error || data.message || '');
    return /active orders/i.test(msg) && /maximum/i.test(msg);
}

function closeActiveOrderLimitModal() {
    const overlay = document.getElementById('activeOrderLimitModal');
    if (!overlay) return;
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
}

function showActiveOrderLimitModal(data) {
    const overlay = document.getElementById('activeOrderLimitModal');
    if (!overlay) {
        showToast((data && (data.message || data.error)) || 'You already have the maximum number of active orders.', 'error');
        return true;
    }
    const count = Math.max(0, Number(data && data.active_order_count) || 5);
    const limit = Math.max(1, Number(data && data.limit) || 5);
    const lead = document.getElementById('aolLead');
    if (lead) {
        lead.textContent = `You already have ${limit} active orders — the most you can have at once.`;
    }
    const slots = document.getElementById('aolSlots');
    if (slots) {
        slots.innerHTML = '';
        for (let i = 1; i <= limit; i++) {
            const dot = document.createElement('span');
            dot.className = 'aol-slot' + (i <= Math.min(count, limit) ? ' is-filled' : '');
            dot.textContent = String(i);
            slots.appendChild(dot);
        }
    }
    overlay.removeAttribute('hidden');
    overlay.setAttribute('aria-hidden', 'false');
    overlay.classList.add('is-open');
    if (overlay.parentElement !== document.body) {
        document.body.appendChild(overlay);
    }
    const closeBtn = document.getElementById('aolCloseBtn');
    if (closeBtn) {
        closeBtn.onclick = closeActiveOrderLimitModal;
        closeBtn.focus();
    }
    overlay.onclick = function (e) {
        if (e.target === overlay) closeActiveOrderLimitModal();
    };
    return true;
}

function renderCheckoutActiveOrderLimit(data) {
    const nextBtn = document.getElementById('checkoutNextBtn');
    if (isActiveOrderLimitPayload(data)) {
        showActiveOrderLimitModal(data);
        if (nextBtn) nextBtn.disabled = true;
        return true;
    }
    if (nextBtn) nextBtn.disabled = false;
    return false;
}

function clearCheckoutActiveOrderLimit() {
    renderCheckoutActiveOrderLimit({ blocked: false });
}

async function ensureCheckoutActiveOrderAllowed() {
    try {
        const data = await fetchCheckoutActiveOrderLimit();
        return !renderCheckoutActiveOrderLimit(data);
    } catch (error) {
        console.error('Active order limit check failed:', error);
        clearCheckoutActiveOrderLimit();
        return true;
    }
}

function closeStockIssueModal() {
    const modal = document.getElementById('stockIssueModal');
    if (modal) modal.classList.remove('active');
}

function showStockIssueModal(issues, introText) {
    const modal = document.getElementById('stockIssueModal');
    const list = document.getElementById('stockIssueList');
    const intro = document.getElementById('stockIssueIntro');
    if (!modal || !list) {
        const first = (issues && issues[0] && issues[0].message) || 'Some items are unavailable.';
        showToast(first, 'error');
        return;
    }

    if (intro) {
        intro.textContent = introText || 'Some items in your selection can’t be checked out right now. Update your basket quantities, then try again.';
    }

    list.innerHTML = (issues || []).map(function (issue) {
        const available = Number(issue.available) || 0;
        const requested = Number(issue.requested) || 0;
        const badge = available <= 0
            ? '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;background:rgba(192,57,43,0.12);color:#9b1c1c;font-size:11px;font-weight:700;">Out of stock</span>'
            : '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;background:rgba(240,180,41,0.18);color:#8a5a00;font-size:11px;font-weight:700;">Only ' + available + ' left</span>';
        const img = issue.image_url
            ? '<img src="' + String(issue.image_url).replace(/"/g, '&quot;') + '" alt="" style="width:48px;height:48px;border-radius:10px;object-fit:cover;background:#f5ede6;flex-shrink:0;" onerror="this.style.display=\'none\'">'
            : '<div style="width:48px;height:48px;border-radius:10px;background:linear-gradient(145deg,#f5ede6,#ede3d8);display:flex;align-items:center;justify-content:center;color:rgba(107,76,59,0.3);flex-shrink:0;"><i class="ri-flower-line"></i></div>';
        return (
            '<div style="display:flex;gap:0.75rem;align-items:flex-start;padding:0.75rem;border:1px solid rgba(107,76,59,0.12);border-radius:14px;background:#fffdf9;">' +
            img +
            '<div style="min-width:0;flex:1;">' +
            '<div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:flex-start;margin-bottom:0.25rem;">' +
            '<div style="font-weight:600;font-size:13.5px;color:var(--charcoal);line-height:1.3;">' + String(issue.name || 'Item').replace(/</g, '&lt;') + '</div>' +
            badge +
            '</div>' +
            '<div style="font-size:12.5px;color:var(--muted);line-height:1.45;">' +
            String(issue.message || '').replace(/</g, '&lt;') +
            '</div>' +
            (requested > 0
                ? '<div style="margin-top:0.35rem;font-size:12px;color:var(--charcoal);">Requested: <strong>' + requested + '</strong> · Available: <strong>' + available + '</strong></div>'
                : '') +
            '</div></div>'
        );
    }).join('');

    modal.classList.add('active');
}

async function ensureCheckoutStockAvailable(payload) {
    try {
        const response = await fetch('/api/v1/checkout/validate-stock', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + (await getAuthToken())
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload || {})
        });
        const result = await response.json().catch(function () { return {}; });
        if (isActiveOrderLimitPayload(result)) {
            showActiveOrderLimitModal(result);
            return false;
        }
        if (response.ok && result.success) return true;

        const issues = result.stock_issues || [];
        if (issues.length) {
            showStockIssueModal(issues);
            return false;
        }

        showToast(result.error || 'Could not verify item stock right now', 'error');
        return false;
    } catch (err) {
        console.error('Stock precheck failed', err);
        showToast('Could not verify item stock right now', 'error');
        return false;
    }
}

async function buyNowDirect(item) {
    if (SHOPPING_DISABLED) {
        showToast('Checkout is disabled for seller/admin accounts', 'error');
        return;
    }
    // item = { product_id, variant_id, quantity, price, name, store_name, image_url }
    
    showToast('Please sign in to buy');
    localStorage.setItem('redirectAfterLogin', window.location.href);
    setTimeout(() => {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.href);
    }, 1200);
    
}

async function checkout() {
    if (SHOPPING_DISABLED) {
        showToast('Checkout is disabled for seller/admin accounts', 'error');
        return;
    }
    const selectedItems = cart.filter(item => item.is_selected);
    if (!selectedItems.length) { 
        showToast('Please select at least one item to checkout'); 
        return; 
    }
    
    showToast('Please sign in to checkout');
    localStorage.setItem('redirectAfterLogin', window.location.href);
    setTimeout(() => {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.href);
    }, 1200);
    
}

function hasAnyUploadedCheckoutProofs() {
    if (Object.values(uploadedProofs || {}).some(url => !!url)) return true;
    if (Object.values(uploadedProofData || {}).some(data => !!(data && data.url))) return true;

    const sessionId = sessionStorage.getItem('active_checkout');
    if (!sessionId) return false;

    try {
        const proofs = JSON.parse(sessionStorage.getItem(`${sessionId}_proofs`) || '{}');
        return Object.values(proofs).some(data => !!(data && (data.public_id || data.url)));
    } catch (e) {
        return false;
    }
}

async function closeCheckout() {
    if (checkoutStep > 1) {
        const hasProofs = hasAnyUploadedCheckoutProofs();
        const confirmMessage = hasProofs
            ? 'You have uploaded payment proofs. Are you sure you want to cancel checkout? Unused uploads will be deleted.'
            : 'Are you sure you want to cancel checkout?';

        if (!(await window.openConfirmModal(confirmMessage))) {
            return;
        }

        cancelCheckout(true);
        isCreatingOrders = false;
    }
    document.getElementById('checkoutModal').classList.remove('active');
    cancelCheckout();
    buyNowMode = false;
    buyNowItem = null;
    clearCheckoutActiveOrderLimit();
}

function goBackCheckout() {
    if (checkoutStep === 3) {
        checkoutStep = 2;
        updateProgressIndicator(2);
        document.getElementById('checkoutStep3').style.display = 'none';
        document.getElementById('checkoutStep2').style.display = 'block';
        document.getElementById('checkoutBackBtn').style.display = 'inline-block';
        document.getElementById('checkoutBackBtn').textContent = 'Back';
        document.getElementById('checkoutNextBtn').disabled = false;
        document.getElementById('checkoutNextBtn').textContent = '→ Proceed to Payment';
        return;
    }

    if (checkoutStep === 2) {
        checkoutStep = 1;
        updateProgressIndicator(1);
        document.getElementById('checkoutStep2').style.display = 'none';
        document.getElementById('checkoutStep1').style.display = 'block';
        document.getElementById('checkoutBackBtn').style.display = 'none';
        document.getElementById('checkoutNextBtn').disabled = false;
        document.getElementById('checkoutNextBtn').textContent = '→ Continue';
        return;
    }
    
    closeCheckout();
}

function isCheckoutAddressDeliverable(addressId) {
    const status = checkoutAddressDeliveryMap[addressId];
    if (!status) return true;
    return status.canDeliver !== false;
}

function getCheckoutAddressDeliveryIssues(addressId) {
    const status = checkoutAddressDeliveryMap[addressId];
    return (status && Array.isArray(status.issues)) ? status.issues : [];
}

function markCheckoutAddressUndeliverable(addressId, issues) {
    checkoutAddressDeliveryMap[addressId] = {
        canDeliver: false,
        issues: Array.isArray(issues) ? issues : [],
    };
}

function pickDeliverableCheckoutAddress(preferredId = null) {
    const deliverable = checkoutAddresses.filter(address => isCheckoutAddressDeliverable(address.id));
    if (!deliverable.length) return null;
    if (preferredId && deliverable.some(address => address.id === preferredId)) {
        return preferredId;
    }
    const defaultAddress = deliverable.find(address => address.is_default);
    return (defaultAddress || deliverable[0]).id;
}

async function probeCheckoutAddressDelivery(addressId) {
    try {
        let response;

        if (buyNowMode && buyNowItem) {
            response = await fetch('/api/v1/checkout/buy-now/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + (await getAuthToken())
                },
                body: JSON.stringify({
                    product_id: buyNowItem.product_id,
                    variant_id: buyNowItem.variant_id || null,
                    quantity: buyNowItem.quantity || 1,
                    delivery_address_id: addressId,
                    addons: Array.isArray(buyNowItem.addons) ? buyNowItem.addons : [],
                    addon_option_ids: Array.isArray(buyNowItem.addon_option_ids) ? buyNowItem.addon_option_ids : [],
                })
            });
        } else {
            const selectedItems = cart.filter(item => item.is_selected);
            if (!selectedItems.length) {
                return { canDeliver: true, issues: [] };
            }
            response = await fetch('/api/v1/checkout/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + (await getAuthToken())
                },
                body: JSON.stringify({
                    delivery_address_id: addressId,
                    delivery_notes: '',
                    items: selectedItems.map(item => ({
                        item_id: item.cart_item_id,
                        quantity: item.quantity
                    }))
                })
            });
        }

        const result = await response.json();
        if (result.success) {
            return { canDeliver: true, issues: [] };
        }

        if (result.code === 'active_order_limit') {
            renderCheckoutActiveOrderLimit(result);
            return { canDeliver: false, issues: [], activeOrderLimit: true };
        }

        const issues = result.undeliverable_stores || [];
        if (issues.length) {
            return { canDeliver: false, issues };
        }

        // Non-delivery validation errors should not permanently grey the address.
        return { canDeliver: true, issues: [] };
    } catch (error) {
        console.error('Address delivery probe failed:', addressId, error);
        return { canDeliver: true, issues: [] };
    }
}

async function evaluateCheckoutAddressCoverage() {
    checkoutAddressDeliveryMap = {};
    if (!checkoutAddresses.length) return;

    const results = await Promise.all(
        checkoutAddresses.map(async (address) => {
            const status = await probeCheckoutAddressDelivery(address.id);
            return [address.id, status];
        })
    );

    results.forEach(([addressId, status]) => {
        checkoutAddressDeliveryMap[addressId] = status;
    });
}

async function loadCheckoutAddresses() {
    const listEl = document.getElementById('checkoutAddressList');
    const emptyEl = document.getElementById('checkoutAddressEmpty');
    const issuesEl = document.getElementById('checkoutDeliveryIssues');

    if (!listEl) return;

    listEl.innerHTML = '<div style="padding:12px; border:1px solid var(--border); border-radius: var(--radius-md); color: var(--muted);">Loading addresses...</div>';
    emptyEl.style.display = 'none';
    issuesEl.style.display = 'none';
    issuesEl.innerHTML = '';
    checkoutAddressDeliveryMap = {};

    try {
        const limitData = await fetchCheckoutActiveOrderLimit();
        if (renderCheckoutActiveOrderLimit(limitData)) {
            listEl.innerHTML = '';
            emptyEl.style.display = 'none';
            return;
        }

        checkoutAddresses = await fetchCheckoutAddresses();
        if (!checkoutAddresses.length) {
            selectedCheckoutAddressId = null;
            renderCheckoutAddresses();
            return;
        }

        listEl.innerHTML = '<div style="padding:12px; border:1px solid var(--border); border-radius: var(--radius-md); color: var(--muted);">Checking delivery coverage for your addresses...</div>';
        await evaluateCheckoutAddressCoverage();

        const preferred = checkoutAddresses.find(address => address.is_default) || checkoutAddresses[0];
        selectedCheckoutAddressId = pickDeliverableCheckoutAddress(preferred ? preferred.id : null);
        renderCheckoutAddresses();

        const undeliverableCount = checkoutAddresses.filter(address => !isCheckoutAddressDeliverable(address.id)).length;
        if (!selectedCheckoutAddressId && undeliverableCount) {
            const firstBlocked = checkoutAddresses.find(address => !isCheckoutAddressDeliverable(address.id));
            renderCheckoutDeliveryIssues(getCheckoutAddressDeliveryIssues(firstBlocked.id));
        } else {
            renderCheckoutDeliveryIssues([]);
        }
    } catch (error) {
        console.error('Checkout address load error:', error);
        listEl.innerHTML = '<div style="padding:12px; border:1px solid #e0b4b4; background:#fff5f5; color:#8b3a3a; border-radius: var(--radius-md);">Could not load saved addresses.</div>';
    }
}

function renderCheckoutAddresses() {
    const listEl = document.getElementById('checkoutAddressList');
    const emptyEl = document.getElementById('checkoutAddressEmpty');
    if (!listEl || !emptyEl) return;

    if (!checkoutAddresses.length) {
        listEl.innerHTML = '';
        emptyEl.style.display = 'block';
        return;
    }

    emptyEl.style.display = 'none';
    listEl.innerHTML = checkoutAddresses.map(address => {
        const isSelected = selectedCheckoutAddressId === address.id;
        const canDeliver = isCheckoutAddressDeliverable(address.id);

        if (!canDeliver) {
            return `
                <div style="display:block; border:1px solid #d9d9d9; background:#f3f3f3; border-radius: var(--radius-md); padding: 12px; margin-bottom: 10px; cursor:not-allowed; opacity:0.72; color:#7a7a7a;" aria-disabled="true" title="Outside delivery area">
                    <div style="display:flex; gap:10px; align-items:flex-start;">
                        <input type="radio" name="checkoutAddress" value="${address.id}" disabled style="margin-top:4px; cursor:not-allowed;">
                        <div style="flex:1;">
                            <div style="font-weight:600; margin-bottom:4px;">
                                ${address.address_label || 'Address'}
                                ${address.is_default ? '<span style="font-size:11px; color:#9a6a6a; margin-left:6px;">Default</span>' : ''}
                            </div>
                            <div style="font-size:13px;">${address.address_line}</div>
                            <div style="font-size:12px; margin-top:4px;">${address.municipality}, ${address.barangay}</div>
                            <div style="font-size:12px; margin-top:6px; color:#8b3a3a;">Outside delivery area</div>
                        </div>
                    </div>
                </div>
            `;
        }

        return `
            <label style="display:block; border:1px solid ${isSelected ? 'var(--deep-rose)' : 'var(--border)'}; background:${isSelected ? 'rgba(176,74,98,0.06)' : 'white'}; border-radius: var(--radius-md); padding: 12px; margin-bottom: 10px; cursor:pointer;">
                <div style="display:flex; gap:10px; align-items:flex-start;">
                    <input type="radio" name="checkoutAddress" value="${address.id}" ${isSelected ? 'checked' : ''} onchange="selectCheckoutAddress(${address.id})" style="margin-top:4px;">
                    <div style="flex:1;">
                        <div style="font-weight:600; margin-bottom:4px;">
                            ${address.address_label || 'Address'}
                            ${address.is_default ? '<span style="font-size:11px; color: var(--deep-rose); margin-left:6px;">Default</span>' : ''}
                        </div>
                        <div style="font-size:13px; color: var(--charcoal);">${address.address_line}</div>
                        <div style="font-size:12px; color: var(--muted); margin-top:4px;">${address.municipality}, ${address.barangay}</div>
                    </div>
                </div>
            </label>
        `;
    }).join('');
}

function selectCheckoutAddress(addressId) {
    if (!isCheckoutAddressDeliverable(addressId)) {
        showDeliveryUnavailableModal({
            reason: 'Outside delivery area',
            tip: 'Choose a different saved address that falls within this shop’s delivery coverage.',
        });
        return;
    }
    selectedCheckoutAddressId = addressId;
    renderCheckoutDeliveryIssues([]);
    renderCheckoutAddresses();
}

function renderCheckoutDeliveryIssues(issues) {
    const issuesEl = document.getElementById('checkoutDeliveryIssues');
    if (!issuesEl) return;

    if (!issues || !issues.length) {
        issuesEl.style.display = 'none';
        issuesEl.innerHTML = '';
        return;
    }

    issuesEl.style.display = 'block';
    const storeNames = [...new Set(issues.map(i => i.store_name).filter(Boolean))];
    const detail = storeNames.length
        ? ` — ${storeNames.slice(0, 2).join(', ')}${storeNames.length > 2 ? ` +${storeNames.length - 2}` : ''}`
        : '';

    issuesEl.innerHTML = `
        <div style="padding:10px 12px; border:1px solid #e0b4b4; background:#fff5f5; color:#8b3a3a; border-radius: var(--radius-md); font-size:13px;">
            Outside delivery area${detail}
        </div>
    `;
}


async function proceedCheckout() {
    if (checkoutStep === 1) {
        if (!selectedCheckoutAddressId) {
            showToast('Select a deliverable address');
            return;
        }
        if (!isCheckoutAddressDeliverable(selectedCheckoutAddressId)) {
            showDeliveryUnavailableModal({
                reason: 'Outside delivery area',
                tip: 'Choose a different saved address that falls within this shop’s delivery coverage.',
            });
            selectedCheckoutAddressId = pickDeliverableCheckoutAddress();
            renderCheckoutAddresses();
            renderCheckoutDeliveryIssues(getCheckoutAddressDeliveryIssues(
                checkoutAddresses.find(address => !isCheckoutAddressDeliverable(address.id))?.id
            ));
            return;
        }

        try {
            renderCheckoutDeliveryIssues([]);
            let response, result;

            if (buyNowMode && buyNowItem) {
                // Buy Now mode: validate directly with product data
                const requestBody = {
                    product_id: buyNowItem.product_id,
                    variant_id: buyNowItem.variant_id || null,
                    quantity: buyNowItem.quantity || 1,
                    delivery_address_id: selectedCheckoutAddressId,
                    addons: Array.isArray(buyNowItem.addons) ? buyNowItem.addons : [],
                    addon_option_ids: Array.isArray(buyNowItem.addon_option_ids) ? buyNowItem.addon_option_ids : [],
                };
                console.log('📤 Buy Now Validate Request:', requestBody);
                
                response = await fetch('/api/v1/checkout/buy-now/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + (await getAuthToken())
                    },
                    body: JSON.stringify(requestBody)
                });
                console.log('📥 Buy Now Validate Response Status:', response.status);
            } else {
                // Normal cart checkout
                const selectedItems = cart.filter(item => item.is_selected);
                if (!selectedItems.length) {
                    showToast('Please select at least one item to checkout');
                    return;
                }
                response = await fetch('/api/v1/checkout/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + (await getAuthToken())
                    },
                    body: JSON.stringify({
                        delivery_address_id: selectedCheckoutAddressId,
                        delivery_notes: document.getElementById('deliveryNotes').value,
                        items: selectedItems.map(item => ({
                            item_id: item.cart_item_id,
                            quantity: item.quantity
                        }))
                    })
                });
            }

            result = await response.json();
            console.log('📋 Validation Response:', result);
            
            if (result.success && result.orders) {
                checkoutOrders = result.orders;
                uploadedProofs = {};
                uploadedProofData = {};
                selectedPaymentMethods = {};
                checkoutOrders.forEach(order => {
                    selectedPaymentMethods[order.temp_id] = 'gcash';
                });
                displayOrderSummary();
                
                checkoutStep = 2;
                updateProgressIndicator(2);
                document.getElementById('checkoutStep1').style.display = 'none';
                document.getElementById('checkoutStep2').style.display = 'block';
                document.getElementById('checkoutBackBtn').style.display = 'inline-block';
                document.getElementById('checkoutNextBtn').textContent = '→ Proceed to Payment';
            } else {
                console.error('❌ Validation failed:', result.error || 'Unknown error');
                const blockedAddressId = selectedCheckoutAddressId;
                if (blockedAddressId && result.undeliverable_stores && result.undeliverable_stores.length > 0) {
                    markCheckoutAddressUndeliverable(blockedAddressId, result.undeliverable_stores);
                    selectedCheckoutAddressId = pickDeliverableCheckoutAddress();
                    renderCheckoutAddresses();
                }
                renderCheckoutDeliveryIssues(result.undeliverable_stores || []);

                // Show more helpful error message
                if (result.code === 'active_order_limit') {
                    renderCheckoutActiveOrderLimit(result);
                } else if (result.undeliverable_stores && result.undeliverable_stores.length > 0) {
                    const issue = result.undeliverable_stores[0];
                    showDeliveryUnavailableModal({
                        title: 'Cannot deliver here',
                        reason: issue.reason || `${issue.store_name || 'This shop'} can’t deliver to your selected address.`,
                        tip: 'Deselect those items, or choose a different delivery address that falls within each shop’s coverage area.',
                    });
                } else if (isDeliveryUnavailableError(result.error)) {
                    showDeliveryUnavailableModal({ reason: result.error });
                } else {
                    showToast(result.error || 'Failed to validate delivery', 'error');
                }
            }
        } catch (error) {
            console.error('Checkout error:', error);
            showCartActionError(error.message || error);
        }
    }
    else if (checkoutStep === 2) {
        // Proceed to payment (per-store date/time will be validated there)
        checkoutStep = 3;
        currentOrderIndex = 0;
        updateProgressIndicator(3);
        document.getElementById('checkoutStep2').style.display = 'none';
        document.getElementById('checkoutStep3').style.display = 'block';
        document.getElementById('checkoutBackBtn').textContent = 'Back';
        displayGCashPayment();
    }
    else if (checkoutStep === 3) {
        const nextBtn = document.getElementById('checkoutNextBtn');
        const currentOrder = checkoutOrders[currentOrderIndex];
        const paymentMethod = getOrderPaymentMethod(currentOrder);
        const proofState = getProofState(currentOrder.temp_id);

        // Validate delivery date/time against store open days/hours
        const dateInput = document.getElementById(`storeDeliveryDate_${currentOrder.temp_id}`);
        const timeSelect = document.getElementById(`storeDeliveryTime_${currentOrder.temp_id}`);
        const closedMsg = document.getElementById(`storeClosedMsg_${currentOrder.temp_id}`);
        const selectedDate = (dateInput && dateInput.value) || getStoreDeliveryDate(currentOrder.temp_id);
        const selectedDateObj = new Date(`${selectedDate}T00:00:00`);
        selectedDateObj.setHours(0, 0, 0, 0);
        const { today, maxDate } = getCheckoutDateLimitWindow();

        if (selectedDateObj < today) {
            focusCheckoutDeliveryIssue(
                currentOrder.temp_id,
                '<i class="ri-calendar-close-line"></i> Past dates are locked. Please choose today or a future open day.'
            );
            return;
        }
        if (selectedDateObj > maxDate) {
            focusCheckoutDeliveryIssue(
                currentOrder.temp_id,
                '<i class="ri-calendar-close-line"></i> Please choose a delivery date within the next 14 days.'
            );
            return;
        }
        if (!isCheckoutStoreOpenOnDate(
            (Array.isArray(currentOrder._openDays) && currentOrder._openDays.length)
                ? currentOrder._openDays
                : (currentOrder.store_schedule || null),
            selectedDateObj
        )) {
            focusCheckoutDeliveryIssue(
                currentOrder.temp_id,
                '<i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.'
            );
            return;
        }
        if (closedMsg && closedMsg.style.display !== 'none') {
            // Keep the existing in-modal message (e.g. all slots passed) and jump to it
            focusCheckoutDeliveryIssue(currentOrder.temp_id);
            return;
        }
        if (timeSelect) {
            const selectedOption = timeSelect.options[timeSelect.selectedIndex];
            if (!timeSelect.value || timeSelect.disabled || (selectedOption && selectedOption.disabled)) {
                const optionText = ((timeSelect.options[0] && timeSelect.options[0].textContent) || '').toLowerCase();
                if (timeSelect.disabled || optionText.includes('passed') || optionText.includes('closed')) {
                    focusCheckoutDeliveryIssue(
                        currentOrder.temp_id,
                        optionText.includes('passed')
                            ? '<i class="ri-time-line"></i> All delivery slots for today have passed. Please select another open day.'
                            : '<i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.'
                    );
                    return;
                }
                focusCheckoutDeliveryIssue(
                    currentOrder.temp_id,
                    '<i class="ri-time-line"></i> Please select a valid open delivery time slot.'
                );
                return;
            }
        } else {
            focusCheckoutDeliveryIssue(
                currentOrder.temp_id,
                '<i class="ri-time-line"></i> Please select a valid delivery time slot.'
            );
            return;
        }

        if (paymentMethod === 'gcash' && !proofState.hasUploaded) {
            if (!proofState.hasPending) {
                showToast('Please choose a payment proof for this order first', 'error');
                return;
            }

            const uploaded = await uploadProof(currentOrder.temp_id);
            if (!uploaded) {
                return;
            }
        }
        
        if (currentOrderIndex < checkoutOrders.length - 1) {
            currentOrderIndex++;
            displayGCashPayment();
        } else {
            // Prevent double click
            if (nextBtn.disabled) return;
            
            nextBtn.disabled = true;
            nextBtn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Processing...';
            
            await createOrders();
        }
    }
}

async function createOrders() {
    // Prevent multiple submissions
    if (isCreatingOrders) {
        console.log('⚠️ Order creation already in progress, ignoring duplicate click');
        return;
    }
    
    const nextBtn = document.getElementById('checkoutNextBtn');
    const originalText = nextBtn.textContent;
    
    nextBtn.disabled = true;
    nextBtn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Processing...';
    
    isCreatingOrders = true;
    
    showToast('Creating orders...', 'info');
    
    try {
        const token = await getAuthToken();
        const addressId = selectedCheckoutAddressId;
        const deliveryNotes = document.getElementById('deliveryNotes').value;
        
        if (!addressId) {
            showToast('Error: No delivery address selected', 'error');
            nextBtn.disabled = false;
            nextBtn.textContent = originalText;
            isCreatingOrders = false;
            return;
        }
        
        // Phase 1: Collect per-store delivery preferences
        const ordersPayload = {
            address_id: addressId,
            delivery_notes: deliveryNotes,
            orders: checkoutOrders.map(order => ({
                temp_id: order.temp_id,
                store_id: order.store_id,
                store_name: order.store_name,
                payment_method: getOrderPaymentMethod(order),
                subtotal: order.subtotal,
                delivery_fee: order.delivery_fee,
                distance_km: order.distance_km,
                total: order.total,
                requested_delivery_date: getStoreDeliveryDate(order.temp_id),  // Phase 1: Per-store date
                requested_delivery_time: getStoreDeliveryTime(order.temp_id),  // Phase 1: Per-store time
                items: order.items.map(item => ({
                    product_id: item.product_id,
                    variant_id: item.variant_id,
                    quantity: item.quantity,
                    price: item.price,
                    addons: Array.isArray(item.addons) ? item.addons : [],
                    addons_total: Number(item.addons_total != null
                        ? item.addons_total
                        : (Array.isArray(item.addons)
                            ? item.addons.reduce((s, a) => s + (Number(a.price || 0) * Number(a.quantity || 1)), 0)
                            : 0)),
                })),
                payment_proof_url: uploadedProofs[order.temp_id],
                payment_proof_public_id: uploadedProofData[order.temp_id]?.public_id || null
            }))
        };
        
        console.log('📦 Orders payload with per-store delivery preferences:', ordersPayload);

        let response, result;

        if (buyNowMode && buyNowItem) {
            // Buy Now mode: create order directly from product data
            const order = checkoutOrders[0];
            const buyNowPayload = {
                product_id: buyNowItem.product_id,
                variant_id: buyNowItem.variant_id || null,
                quantity: buyNowItem.quantity || 1,
                address_id: addressId,
                delivery_notes: deliveryNotes,
                payment_method: getOrderPaymentMethod(order),
                requested_delivery_date: getStoreDeliveryDate(order.temp_id),
                requested_delivery_time: getStoreDeliveryTime(order.temp_id),
                payment_proof_url: uploadedProofs[order.temp_id],
                payment_proof_public_id: uploadedProofData[order.temp_id]?.public_id || null,
                addons: Array.isArray(buyNowItem.addons) ? buyNowItem.addons : [],
                addon_option_ids: Array.isArray(buyNowItem.addon_option_ids) ? buyNowItem.addon_option_ids : [],
            };
            console.log('📦 Buy Now payload:', buyNowPayload);

            response = await fetch('/api/v1/checkout/buy-now/create-order', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify(buyNowPayload)
            });
        } else {
            // Normal cart checkout
            response = await fetch('/api/v1/checkout/create-orders', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify(ordersPayload)
            });
        }

        result = await response.json();
        
        if (response.ok && result.success) {
            showToast('Orders created successfully!');
            await completeCheckout();
        } else {
            if (result.code === 'active_order_limit') {
                showActiveOrderLimitModal(result);
            } else {
                showToast('Error creating orders: ' + (result.error || 'Unknown error'), 'error');
            }
            nextBtn.disabled = false;
            nextBtn.textContent = originalText;
            isCreatingOrders = false;
        }
    } catch (error) {
        console.error('Error creating orders:', error);
        showToast('Error creating orders. Please try again.', 'error');
        nextBtn.disabled = false;
        nextBtn.textContent = originalText;
        isCreatingOrders = false;
    }
}

async function completeCheckout() {
    const nextBtn = document.getElementById('checkoutNextBtn');
    
    if (buyNowMode) {
        // Buy Now mode: don't touch the cart
        buyNowMode = false;
        buyNowItem = null;
    } else {
        // Normal checkout: clear selected cart items
        cart = cart.filter(item => !item.is_selected);
        persistLocalCart();
        updateCartCount();
        updateCartDisplay();
    }
    
    // Close the modal first (prevents double clicks)
    document.getElementById('checkoutModal').classList.remove('active');
    
    // Clear checkout state without deleting the uploaded proofs that are now attached to orders
    finalizeCheckoutSession();
    
    showToast('Orders submitted for verification!');
    
    // Remove any lingering modal handlers
    if (checkoutModalCloseHandler) {
        document.getElementById('checkoutModal').removeEventListener('click', checkoutModalCloseHandler);
        checkoutModalCloseHandler = null;
    }
    
    // Reset button state
    nextBtn.disabled = false;
    nextBtn.textContent = '✓ Complete';
    isCreatingOrders = false;
    
    // Redirect to orders page after a short delay
    setTimeout(() => {
        window.location.href = "/my-account?page=orders";
    }, 1500);
}

function displayOrderSummary() {
    const container = document.getElementById('ordersByStore');
    let html = '';
    let total = 0;
    const cartItemsSafe = (typeof cart !== 'undefined' && Array.isArray(cart)) ? cart : [];

    const escHtml = (val) => {
        if (val === null || val === undefined) return '';
        return String(val)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    if (checkoutOrders && Array.isArray(checkoutOrders)) {
        checkoutOrders.forEach((order, index) => {
            if (!order.temp_id) {
                order.temp_id = 'temp_' + Date.now() + '_' + index;
            }
            
            const items = order.items || [];
            const grandTotal = order.total || 0;
            total += grandTotal;
            const totalItemsCount = items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);

            const itemRows = items.map(item => {
                const productId = item.product_id || item.id;
                const variantId = item.variant_id || null;
                let itemName = item.name || `Product #${productId || ''}`;
                let itemImage = item.image_url || item.product_image_url || '';
                let variantLabel = item.variant_name || '';

                if (buyNowMode && buyNowItem && buyNowItem.product_id === productId && (buyNowItem.variant_id || null) === variantId) {
                    itemName = buyNowItem.name || itemName;
                    itemImage = buyNowItem.image_url || itemImage;
                    variantLabel = buyNowItem.variant_name || variantLabel;
                } else if (buyNowMode && buyNowItem && Array.isArray(buyNowItem.addons)) {
                    const addonMatch = buyNowItem.addons.find(a =>
                        Number(a.product_id || a.id) === Number(productId) && !variantId
                    );
                    if (addonMatch) {
                        itemName = addonMatch.name || itemName;
                        itemImage = addonMatch.image_url || itemImage;
                    }
                } else {
                    const cartMatch = cartItemsSafe.find(ci => ci.id === productId && (ci.variant_id || null) === variantId);
                    if (cartMatch) {
                        if (cartMatch.name) itemName = cartMatch.name;
                        if (cartMatch.image_url) itemImage = cartMatch.image_url;
                        if (cartMatch.variant_name) variantLabel = cartMatch.variant_name;
                    }
                }

                const unitPrice = Number(item.price || 0);
                const qty = Number(item.quantity || 0);
                let addons = Array.isArray(item.addons) ? item.addons : [];
                if ((!addons || !addons.length) && buyNowMode && buyNowItem && Array.isArray(buyNowItem.structured_addons)) {
                    addons = buyNowItem.structured_addons;
                }
                const cartMatchForAddons = cartItemsSafe.find(ci => ci.id === productId && (ci.variant_id || null) === variantId);
                if ((!addons || !addons.length) && cartMatchForAddons && Array.isArray(cartMatchForAddons.addons)) {
                    addons = cartMatchForAddons.addons;
                }
                const addonsTotal = Number(item.addons_total != null
                    ? item.addons_total
                    : addons.reduce((s, a) => s + (Number(a.price || 0) * Number(a.quantity || qty || 1)), 0));
                const lineTotal = (unitPrice * qty) + addonsTotal;
                const addonsRows = addons.map(a => {
                    const aName = a.name || 'Add-on';
                    const aGroup = a.group_name ? `${a.group_name}: ` : '';
                    const aPrice = Number(a.price || 0);
                    const aUnits = Math.max(1, Number(a.units || 0));
                    // quantity from checkout may already be units * product qty; prefer units when present
                    const displayQty = a.units != null ? aUnits : Math.max(1, Number(a.quantity || 1));
                    const aImg = a.image_url
                        ? `<img src="${escHtml(a.image_url)}" alt="${escHtml(aName)}" style="width:20px;height:20px;object-fit:cover;border-radius:5px;border:1px solid var(--border);flex-shrink:0;">`
                        : `<div style="width:20px;height:20px;border-radius:5px;border:1px solid var(--border);background:var(--cream);flex-shrink:0;display:flex;align-items:center;justify-content:center;"><i class="ri-gift-line" style="font-size:10px;color:var(--muted);"></i></div>`;
                    return `<div style="display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11px;color:var(--muted);">
                        ${aImg}
                        <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">+ ${escHtml(aGroup)}${escHtml(aName)}${displayQty > 1 ? ` ×${displayQty}` : ''}</span>
                        <span style="margin-left:auto;white-space:nowrap;">₱${(aPrice * (a.units != null ? aUnits : 1)).toFixed(2)}</span>
                    </div>`;
                }).join('');

                return `<li style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:7px 0;border-bottom:1px dashed rgba(107,76,59,0.12);">
                    <div style="display:flex;align-items:flex-start;gap:8px;min-width:0;flex:1;">
                        ${itemImage
                            ? `<img src="${escHtml(itemImage)}" alt="${escHtml(itemName)}" style="width:32px;height:32px;object-fit:cover;border-radius:8px;border:1px solid var(--border);flex-shrink:0;">`
                            : `<div style="width:32px;height:32px;border-radius:8px;border:1px solid var(--border);background:var(--cream);display:flex;align-items:center;justify-content:center;color:var(--muted);flex-shrink:0;"><i class="ri-flower-line"></i></div>`
                        }
                        <div style="min-width:0;flex:1;">
                            <div style="color:var(--charcoal);font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(itemName)}</div>
                            <div style="font-size:11px;color:var(--muted);line-height:1.3;">
                                Qty: ${qty} × ₱${unitPrice.toFixed(2)}${variantLabel ? ` · ${escHtml(variantLabel)}` : ''}
                            </div>
                            ${addonsRows}
                        </div>
                    </div>
                    <strong style="white-space:nowrap;color:var(--deep-rose);">₱${lineTotal.toFixed(2)}</strong>
                </li>`;
            }).join('');

            html += `
                <div class="checkout-payment-card">
                    <div class="checkout-payment-head">
                        <span style="color: var(--muted); font-size: 12px;">Store Order</span>
                        <span style="font-weight: 600;">Amount: <span style="color: var(--deep-rose); font-size: 18px;">₱${Number(grandTotal).toFixed(2)}</span></span>
                    </div>
                    <div class="checkout-payment-summary">
                        <strong style="color:var(--charcoal);">${escHtml(order.store_name || 'Store')}</strong>
                        • ${totalItemsCount} item${totalItemsCount !== 1 ? 's' : ''}
                    </div>
                    <ul class="checkout-items-list">
                        ${itemRows || '<li style="color:var(--muted);">No items found</li>'}
                    </ul>
                    <div class="checkout-review-meta">
                        ${order.free_delivery_applied
                            ? `<span>Delivery fee: <strong style="color:#27AE60;">FREE</strong><span style="display:block;font-size:12px;font-weight:500;color:#27AE60;margin-top:2px;">Your order qualifies for free delivery.</span></span>`
                            : order.free_delivery_enabled && Number(order.amount_to_free_delivery || 0) > 0
                                ? `<span>Delivery fee: <strong>₱${Number(order.delivery_fee || 0).toFixed(2)}</strong><span style="display:block;font-size:12px;font-weight:500;color:#9A5B00;margin-top:2px;">Add ₱${Number(order.amount_to_free_delivery).toFixed(2)} more to get free delivery (min ₱${Number(order.free_delivery_minimum || 0).toFixed(2)}).</span></span>`
                                : `<span>Delivery fee: <strong>₱${Number(order.delivery_fee || 0).toFixed(2)}</strong></span>`
                        }
                        <span>Distance: <strong>${Number(order.distance_km || 0).toFixed(2)} km</strong></span>
                    </div>
                </div>
            `;
        });
    }

    container.innerHTML = html;
    document.getElementById('step2Subtotal').textContent = '₱' + total.toFixed(2);
    document.getElementById('step2Total').textContent = '₱' + total.toFixed(2);
}

async function displayGCashPayment() {
    const container = document.getElementById('gcashPaymentContainer');
    if (!container) return;

    if (!Array.isArray(checkoutOrders) || checkoutOrders.length === 0 || !checkoutOrders[currentOrderIndex]) {
        container.innerHTML = `
            <div style="padding:16px;background:#fff8f6;border:1px solid var(--border);border-radius:var(--radius-md);color:var(--muted);text-align:center;">
                <div style="font-weight:600;color:var(--charcoal);margin-bottom:6px;">Payment details are not ready yet</div>
                <div style="font-size:13px;">Please go back to Review, then proceed to Payment again.</div>
            </div>
        `;
        const nextBtn = document.getElementById('checkoutNextBtn');
        if (nextBtn) {
            nextBtn.disabled = false;
            nextBtn.textContent = '→ Proceed to Payment';
        }
        return;
    }

    const order = checkoutOrders[currentOrderIndex];
    const paymentMethod = getOrderPaymentMethod(order);
    const proofState = getProofState(order.temp_id);
    const hasPreview = proofState.hasUploaded || proofState.hasPending;
    const previewSrc = proofState.previewSrc;
    const deliveryDate = getStoreDeliveryDate(order.temp_id);
    const deliveryTime = getStoreDeliveryTime(order.temp_id);
    const orderItems = Array.isArray(order.items) ? order.items : [];
    const totalItemsCount = orderItems.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    const cartItemsSafe = (typeof cart !== 'undefined' && Array.isArray(cart)) ? cart : [];

    const escHtml = (val) => {
        if (val === null || val === undefined) return '';
        return String(val)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    const paymentItemsHtml = orderItems.length
        ? orderItems.map(item => {
            const productId = item.product_id || item.id;
            const variantId = item.variant_id || null;
            const cartMatch = cartItemsSafe.find(ci => ci.id === productId && (ci.variant_id || null) === variantId) || null;

            const itemName = item.name || item.product_name || (cartMatch && cartMatch.name) || ('Product #' + (productId || ''));
            const itemImage = item.image_url || item.product_image_url || (cartMatch && cartMatch.image_url) || '';
            const qty = Number(item.quantity || 0);
            const variantLabel = item.variant_name || (cartMatch && cartMatch.variant_name) || '';
            const addons = Array.isArray(item.addons) ? item.addons : (cartMatch && Array.isArray(cartMatch.addons) ? cartMatch.addons : []);
            const addonsRows = addons.map(a => {
                const aName = a.name || 'Add-on';
                const aGroup = a.group_name ? `${a.group_name}: ` : '';
                const aImg = a.image_url
                    ? `<img src="${escHtml(a.image_url)}" alt="${escHtml(aName)}" style="width:18px;height:18px;object-fit:cover;border-radius:4px;border:1px solid var(--border);flex-shrink:0;">`
                    : '';
                return `<div style="display:flex;align-items:center;gap:5px;margin-top:3px;font-size:10px;color:var(--muted);">
                    ${aImg}
                    <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">+ ${escHtml(aGroup)}${escHtml(aName)}</span>
                </div>`;
            }).join('');

            return `<li style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:7px 0;border-bottom:1px dashed rgba(107,76,59,0.12);">
                <div style="display:flex;align-items:flex-start;gap:8px;min-width:0;flex:1;">
                    ${itemImage
                        ? `<img src="${escHtml(itemImage)}" alt="${escHtml(itemName)}" style="width:32px;height:32px;object-fit:cover;border-radius:8px;border:1px solid var(--border);flex-shrink:0;">`
                        : `<div style="width:32px;height:32px;border-radius:8px;border:1px solid var(--border);background:var(--cream);display:flex;align-items:center;justify-content:center;color:var(--muted);flex-shrink:0;"><i class="ri-flower-line"></i></div>`
                    }
                    <div style="min-width:0;">
                        <div style="color:var(--charcoal);font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(itemName)}</div>
                        ${variantLabel ? `<div style="font-size:11px;color:var(--muted);line-height:1.2;">${escHtml(variantLabel)}</div>` : ''}
                        ${addonsRows}
                    </div>
                </div>
                <strong style="white-space:nowrap;color:var(--deep-rose);">x${qty}</strong>
            </li>`;
        }).join('')
        : '<li style="color:var(--muted);">No items found for this order.</li>';

    let html = `
        <div style="text-align: center; margin-bottom: 16px;">
            <div style="font-size: 12px; color: var(--muted); margin-bottom: 8px;">Order ${currentOrderIndex + 1} of ${checkoutOrders.length}</div>
            <div style="font-size: 18px; font-weight: 600;">${order.store_name || 'Store'}</div>
        </div>

        <div class="checkout-payment-card">
            <div class="checkout-payment-head">
                <span style="color: var(--muted); font-size: 12px;">Payment Summary</span>
                <span style="font-weight: 600;">Amount: <span style="color: var(--deep-rose); font-size: 18px;">&#8369;${Number(order.total || 0).toFixed(2)}</span></span>
            </div>
            <div class="checkout-payment-summary">
                Paying <strong style="color:var(--charcoal);">${order.store_name || 'Store'}</strong> • ${totalItemsCount} item${totalItemsCount !== 1 ? 's' : ''}
            </div>
            <ul class="checkout-items-list">
                ${paymentItemsHtml}
            </ul>
        </div>

        <!-- Phase 1: Per-store delivery date/time picker -->
        <div class="checkout-delivery-card">
            <h5 class="checkout-delivery-title">Requested Delivery</h5>
            <div id="storeClosedMsg_${order.temp_id}" style="display: none; padding: 10px; background: rgba(192,57,43,0.08); border: 1px solid rgba(192,57,43,0.2); border-radius: var(--radius-md); margin-bottom: 10px; color: #c0392b; font-size: 12px; font-weight: 600;">
                <i class="ri-close-circle-line"></i> Store is closed on this day. Please select a different date.
            </div>
            <div class="checkout-delivery-grid">
                <div>
                    <label class="checkout-delivery-label">Date</label>
                    <input type="text" id="storeDeliveryDate_${order.temp_id}" value="${deliveryDate}" class="checkout-delivery-input" placeholder="Select date" required readonly>
                </div>
                <div>
                    <label class="checkout-delivery-label">Time Slot</label>
                    <select id="storeDeliveryTime_${order.temp_id}" class="checkout-delivery-input" required>
                        <option value="">Loading...</option>
                    </select>
                </div>
            </div>
            <div style="font-size:11px; color:var(--muted); margin-top:8px;">
                Closed days, past dates, and past hours are locked based on this store's open schedule.
            </div>
        </div>
    `;

    const gcashEnabled = order.allow_gcash !== false;
    const codEnabled = order.allow_cod === true;
    const paymentSelector = `
        <div class="checkout-payment-card">
            <h5 class="checkout-delivery-title">Payment Method</h5>
            <div class="checkout-payment-methods">
                <label class="checkout-payment-method-option" style="cursor:${gcashEnabled ? 'pointer' : 'not-allowed'}; opacity:${gcashEnabled ? '1' : '.55'}; background:${paymentMethod === 'gcash' ? 'rgba(212,120,138,.12)' : '#fff'};">
                    <input type="radio" name="checkoutPaymentMethod_${order.temp_id}" value="gcash" ${paymentMethod === 'gcash' ? 'checked' : ''} ${gcashEnabled ? '' : 'disabled'} onchange="onCheckoutPaymentMethodChange('${order.temp_id}', this.value)" />
                    <span style="font-size:13px;">GCash</span>
                </label>
                <label class="checkout-payment-method-option" style="cursor:${codEnabled ? 'pointer' : 'not-allowed'}; opacity:${codEnabled ? '1' : '.55'}; background:${paymentMethod === 'cod' ? 'rgba(212,120,138,.12)' : '#fff'};">
                    <input type="radio" name="checkoutPaymentMethod_${order.temp_id}" value="cod" ${paymentMethod === 'cod' ? 'checked' : ''} ${codEnabled ? '' : 'disabled'} onchange="onCheckoutPaymentMethodChange('${order.temp_id}', this.value)" />
                    <span style="font-size:13px;">Cash on Delivery</span>
                </label>
            </div>
            ${gcashEnabled ? '' : '<div style="font-size:12px; color:var(--muted); margin-top:8px;">GCash is currently disabled by this store.</div>'}
            ${codEnabled ? '' : '<div style="font-size:12px; color:var(--muted); margin-top:8px;">Cash on Delivery is currently disabled by this store.</div>'}
        </div>`;
    html += paymentSelector;

    if (paymentMethod === 'gcash' && order.gcash_instructions) {
        html += `
            <div class="checkout-payment-card">
                <h5 class="checkout-delivery-title">Payment Instructions</h5>
                <div class="checkout-instructions-body">${order.gcash_instructions}</div>
            </div>
        `;
    }

    if (paymentMethod === 'gcash') {
    html += `
        <div class="checkout-payment-card">
            <h5 class="checkout-delivery-title">GCash QR Code</h5>
            <div class="checkout-instructions-body" style="text-align: center; padding: 16px;">
    `;

    if (order.gcash_qr_codes && order.gcash_qr_codes.length > 0) {
        // Find primary QR or use first one
        const primaryQR = order.gcash_qr_codes.find(q => q.is_primary) || order.gcash_qr_codes[0];
        html += `<img src="${primaryQR.url}" style="max-width: 200px; height: auto; border-radius: var(--radius-md);">`;
    } else {
        html += `<div style="padding: 28px 12px; color: var(--muted);"><i class="ri-qr-code-2-line" style="font-size: 48px;"></i><div style="margin-top: 12px;">No QR code available</div></div>`;
    }

    html += `
            </div>
        </div>

        <div class="checkout-proof-wrap">
            <div class="checkout-proof-title">Upload Payment Receipt</div>
            <div class="checkout-proof-upload-zone">
                <div id="proofPreview_${order.temp_id}" class="checkout-proof-preview" style="display: ${hasPreview ? 'block' : 'none'};">
                    <img id="previewImg_${order.temp_id}" ${previewSrc ? `src="${previewSrc}"` : ''}>
                    <button type="button" class="checkout-proof-clear-btn" onclick="clearProof('${order.temp_id}')">
                        ${proofState.hasUploaded ? 'Remove Image' : 'Clear Image'}
                    </button>
                </div>
                <input type="file" id="proofInput_${order.temp_id}" accept="image/*" onchange="handleProofSelect('${order.temp_id}', event)" style="display: none;">
                <button type="button" class="checkout-proof-choose-btn" onclick="document.getElementById('proofInput_${order.temp_id}').click()">
                    <i class="ri-image-add-line"></i> ${hasPreview ? 'Replace Image' : 'Choose Image'}
                </button>
                <small class="checkout-proof-note">Select screenshot or photo of your GCash payment</small>
            </div>
            <div id="uploadStatus_${order.temp_id}" class="checkout-proof-status">
                ${proofState.hasUploaded ? '<span style="color: var(--sage);">Receipt uploaded</span>' : proofState.hasPending ? '<span style="color: var(--muted);">Image selected. Use the button below to upload.</span>' : ''}
            </div>
        </div>
    `;
    } else {
    html += `
        <div class="checkout-payment-card">
            <div style="font-weight:600; margin-bottom:4px; color:var(--charcoal);"><i class="ri-money-dollar-circle-line"></i> Cash on Delivery selected</div>
            <div style="font-size:12px; color:var(--muted);">No payment receipt required. Please prepare the exact amount upon delivery.</div>
        </div>
    `;
    }

    container.innerHTML = html;
    
    // Phase 1: Add event listeners for per-store delivery date/time
    const timeInput = document.getElementById(`storeDeliveryTime_${order.temp_id}`);
    
    if (timeInput) {
        timeInput.addEventListener('change', (e) => {
            const selectedOption = e.target.options[e.target.selectedIndex];
            if (!e.target.value || (selectedOption && selectedOption.disabled)) {
                showToast('Please select an open delivery time slot', 'error');
                return;
            }
            setStoreDeliveryPreference(order.temp_id, getStoreDeliveryDate(order.temp_id), e.target.value);
        });
    }
    
    // Initialize calendar with store open days locked; then load matching time slots
    const resolvedDate = await initCheckoutDeliveryDatePicker(order, deliveryDate);
    fetchCheckoutTimeSlots(order.store_id, order.temp_id, resolvedDate);
    
    updateCheckoutPaymentAction();

    // Reset the creating orders flag when moving between orders
    isCreatingOrders = false;
}

function onCheckoutPaymentMethodChange(tempId, method) {
    setOrderPaymentMethod(tempId, method);
    displayGCashPayment();
}

function handleProofSelect(tempId, event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const previewUrl = e.target.result;
            const previewImg = document.getElementById(`previewImg_${tempId}`);
            const previewBox = document.getElementById(`proofPreview_${tempId}`);

            if (previewImg) {
                previewImg.src = previewUrl;
            }
            if (previewBox) {
                previewBox.style.display = 'block';
            }
            
            if (!uploadedProofData[tempId]) {
                uploadedProofData[tempId] = {};
            }
            uploadedProofData[tempId].preview = previewUrl;
            uploadedProofData[tempId].file = file;
            updateCheckoutPaymentAction();
        };
        reader.readAsDataURL(file);
    }
}

async function uploadProof(tempId) {
    let file = uploadedProofData[tempId]?.file;
    const input = document.getElementById(`proofInput_${tempId}`);
    
    if (!file && input) {
        file = input.files[0];
    }

    if (!file) {
        showToast('Please select an image');
        return false;
    }

    const statusDiv = document.getElementById(`uploadStatus_${tempId}`);
    statusDiv.innerHTML = '<i class="ri-loader-4-line" style="animation: spin 1s linear infinite;"></i> Uploading...';

    const formData = new FormData();
    formData.append('file', file);
    
    const sessionId = sessionStorage.getItem('active_checkout') || 'temp_' + Date.now();
    formData.append('checkout_session', sessionId);

    try {
        const token = await getAuthToken();
        const requestOptions = {
            method: 'POST',
            body: formData
        };
        if (token) {
            requestOptions.headers = { 'Authorization': 'Bearer ' + token };
        }

        const response = await fetch('/api/v1/checkout/upload-proof', {
            ...requestOptions
        });

        const result = await response.json();

        if (response.ok && result.success) {
            const proofs = JSON.parse(sessionStorage.getItem(`${sessionId}_proofs`) || '{}');
            proofs[tempId] = { url: result.url, public_id: result.public_id };
            sessionStorage.setItem(`${sessionId}_proofs`, JSON.stringify(proofs));
            
            saveProofData(tempId, {
                url: result.url,
                preview: uploadedProofData[tempId]?.preview || result.url,
                public_id: result.public_id
            });
            
            statusDiv.innerHTML = '<span style="color: var(--sage);">Receipt uploaded successfully</span>';
            updateCheckoutPaymentAction();
            return true;
        }

        statusDiv.innerHTML = '<span style="color: var(--deep-rose);">Upload failed</span>';
        showToast('Upload failed: ' + (result.error || 'Unknown error'));
        return false;
    } catch (error) {
        statusDiv.innerHTML = '<span style="color: var(--deep-rose);">Error uploading</span>';
        console.error('Upload error:', error);
        return false;
    }
}

async function getAuthToken() {
    return localStorage.getItem('jwt_token') || '';
}

function searchProducts(event) {
    event.preventDefault();
    const query = document.getElementById('searchInput').value.trim();
    if (query) window.location.href = "/search?q=" + encodeURIComponent(query);
}

function clearProof(tempId) {
    const input = document.getElementById(`proofInput_${tempId}`);
    if (input) {
        input.value = '';
    }

    const preview = document.getElementById(`proofPreview_${tempId}`);
    if (preview) {
        preview.style.display = 'none';
    }

    const previewImg = document.getElementById(`previewImg_${tempId}`);
    if (previewImg) {
        previewImg.removeAttribute('src');
    }

    clearProofData(tempId);
    
    const statusDiv = document.getElementById(`uploadStatus_${tempId}`);
    if (statusDiv) {
        statusDiv.innerHTML = '';
    }

    updateCheckoutPaymentAction();
}

async function syncGuestCart() {
    let guestCart = [];
    try {
        const parsed = JSON.parse(localStorage.getItem('cart') || '[]');
        guestCart = Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        guestCart = [];
    }
    if (guestCart.length === 0) {
        document.getElementById('cartSyncModal').classList.remove('active');
        showToast('No items to sync');
        return;
    }
    
    showToast('Transferring items to your account...', 'info');
    
    let successCount = 0;
    let errorCount = 0;
    
    try {
        for (const item of guestCart) {
            const payload = {
                product_id: item.product_id || item.id,
                quantity: item.quantity
            };
            
            if (item.variant_id) {
                payload.variant_id = item.variant_id;
            }
            const addonPayload = Array.isArray(item.addon_option_ids) && item.addon_option_ids.length
                ? item.addon_option_ids
                : guestAddonPayload(item.addons);
            if (addonPayload.length) {
                payload.addon_option_ids = addonPayload;
            }
            
            try {
                const response = await fetch('/api/cart/items', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                
                if (data.success) {
                    successCount++;
                } else {
                    errorCount++;
                }
            } catch (err) {
                errorCount++;
            }
        }
        
        localStorage.removeItem('cart');
        document.getElementById('cartSyncModal').classList.remove('active');
        await loadCart();
        
        if (successCount > 0) {
            showToast(`Added ${successCount} item(s) to your cart!${errorCount > 0 ? ` (${errorCount} failed)` : ''}`);
        } else if (errorCount > 0) {
            showToast(`Failed to sync ${errorCount} item(s). Please try adding them manually.`, 'error');
        } else {
            showToast('Cart synced successfully!');
        }
        
    } catch (error) {
        console.error('Error syncing cart:', error);
        showToast('Error transferring items. Please try again.', 'error');
        document.getElementById('cartSyncModal').classList.remove('active');
    }
}

function handleAccountNavigation(page) {
    document.getElementById('userMenu')?.classList.remove('show');
    const isOnAccount = window.location.pathname.includes('/my-account');
    if (isOnAccount && typeof loadAccountPage === 'function') {
        loadAccountPage(page);
    } else {
        window.location.href = "/my-account?page=" + page;
    }
    return false;
}

function debugCart() {
    console.log('Cart items:', cart.length);
    cart.forEach((item, index) => {
        console.log(`${index + 1}: ${item.name} (x${item.quantity}) - ₱${item.price}`);
    });
}
window.addToCartLocalStorage = addToCartLocalStorage;
window.persistLocalCart = persistLocalCart;


function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    if (type === 'error') {
        toast.style.background = '#c0392b';
    } else {
        toast.style.background = 'var(--charcoal)';
    }
    setTimeout(() => toast.classList.remove('show'), 3000);
}

/** True when an API/cart error is about store delivery coverage. */
function isDeliveryUnavailableError(message) {
    if (!message || !String(message).trim()) return false;
    const m = String(message).toLowerCase();
    return m.includes("can't deliver") ||
        m.includes('cannot deliver') ||
        m.includes('cannot be delivered') ||
        m.includes('does not deliver') ||
        (m.includes('outside') &&
            (m.includes('delivery') || m.includes('distance') || m.includes('radius') || m.includes('area'))) ||
        m.includes('delivery distance') ||
        m.includes('delivery radius') ||
        m.includes('delivery area') ||
        m.includes('delivery coverage') ||
        m.includes('maximum delivery') ||
        m.includes('missing map coordinates') ||
        m.includes('undeliverable');
}

function humanizeDeliveryReason(reason) {
    const raw = (reason || '').trim();
    const lower = raw.toLowerCase();
    if (!raw || lower.includes('outside delivery distance') || lower.includes('outside delivery area')) {
        return 'This shop can’t deliver to your saved address — it’s outside their delivery coverage.';
    }
    return raw;
}

/**
 * Friendly modal for delivery-coverage failures (mirrors Flutter delivery_unavailable_dialog).
 * opts: { title?, reason?, tip? }
 */
function showDeliveryUnavailableModal(opts) {
    const options = opts || {};
    const title = options.title || 'Outside delivery area';
    const detail = humanizeDeliveryReason(options.reason);
    const tip = options.tip ||
        'You can still browse this shop, but you won’t be able to add items to your cart or check out unless you use an address inside their coverage — or turn on “Browse outside area” only for browsing.';

    let overlay = document.getElementById('deliveryUnavailableModal');
    if (!overlay) {
        const style = document.createElement('style');
        style.textContent = `
            .delivery-unavail-overlay{position:fixed;inset:0;background:rgba(42,35,30,.55);backdrop-filter:blur(6px);display:none;align-items:center;justify-content:center;padding:1.25rem;z-index:12050}
            .delivery-unavail-overlay.show{display:flex}
            .delivery-unavail-card{width:min(440px,100%);background:rgba(255,255,255,.96);border:1px solid rgba(255,255,255,.75);border-radius:20px;box-shadow:0 20px 60px rgba(90,40,80,.18);padding:1.35rem 1.4rem 1.15rem}
            .delivery-unavail-head{display:flex;align-items:center;gap:.85rem;margin-bottom:.9rem}
            .delivery-unavail-icon{width:42px;height:42px;border-radius:50%;background:rgba(216,120,160,.14);color:#c24e68;display:flex;align-items:center;justify-content:center;font-size:1.25rem;flex-shrink:0}
            .delivery-unavail-title{font-family:var(--font-display),Georgia,serif;font-size:1.35rem;font-weight:500;color:#2c2520;line-height:1.2;margin:0}
            .delivery-unavail-detail{font-size:.95rem;color:#2c2520;line-height:1.5;margin:0 0 .75rem;opacity:.9}
            .delivery-unavail-tip{font-size:.8rem;color:#9a8d85;line-height:1.45;margin:0 0 1rem}
            .delivery-unavail-actions{display:flex;justify-content:flex-end}
            .delivery-unavail-btn{border:none;border-radius:10px;background:#c24e68;color:#fff;padding:.55rem 1.1rem;font-weight:600;font-size:.9rem;cursor:pointer;font-family:inherit}
            .delivery-unavail-btn:hover{background:#a83a4e}
        `;
        document.head.appendChild(style);

        overlay = document.createElement('div');
        overlay.id = 'deliveryUnavailableModal';
        overlay.className = 'delivery-unavail-overlay';
        overlay.innerHTML = `
            <div class="delivery-unavail-card" role="dialog" aria-modal="true" aria-labelledby="deliveryUnavailTitle">
                <div class="delivery-unavail-head">
                    <div class="delivery-unavail-icon" aria-hidden="true"><i class="ri-map-pin-off-line"></i></div>
                    <h3 class="delivery-unavail-title" id="deliveryUnavailTitle"></h3>
                </div>
                <p class="delivery-unavail-detail" id="deliveryUnavailDetail"></p>
                <p class="delivery-unavail-tip" id="deliveryUnavailTip"></p>
                <div class="delivery-unavail-actions">
                    <button type="button" class="delivery-unavail-btn" id="deliveryUnavailOk">Got it</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    overlay.querySelector('#deliveryUnavailTitle').textContent = title;
    overlay.querySelector('#deliveryUnavailDetail').textContent = detail;
    overlay.querySelector('#deliveryUnavailTip').textContent = tip;
    overlay.classList.add('show');

    const close = function () {
        overlay.classList.remove('show');
        overlay.removeEventListener('click', onBackdrop);
        okBtn.removeEventListener('click', close);
        document.removeEventListener('keydown', onKey);
    };
    const onBackdrop = function (e) { if (e.target === overlay) close(); };
    const onKey = function (e) { if (e.key === 'Escape' || e.key === 'Enter') close(); };
    const okBtn = overlay.querySelector('#deliveryUnavailOk');
    okBtn.addEventListener('click', close);
    overlay.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);
    okBtn.focus();
}

/** Cart/action failures: delivery coverage → modal, otherwise toast. */
function showCartActionError(error) {
    const msg = (error && error.message) ? error.message : String(error || 'Something went wrong');
    if (isDeliveryUnavailableError(msg)) {
        showDeliveryUnavailableModal({ reason: msg });
    } else {
        showToast(msg.startsWith('Error:') ? msg : ('Error: ' + msg), 'error');
    }
}
window.isDeliveryUnavailableError = isDeliveryUnavailableError;
window.showActiveOrderLimitModal = showActiveOrderLimitModal;
window.showCartActionError = showCartActionError;

// Unified confirmation modal helper
(function setupUnifiedConfirmModal() {
    if (window.openConfirmModal) return;

    const style = document.createElement('style');
    style.textContent = `
        .app-confirm-overlay{position:fixed;inset:0;background:rgba(42,35,30,.48);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);display:none;align-items:center;justify-content:center;padding:clamp(.75rem,3vw,1.25rem);z-index:12000}
        .app-confirm-overlay.show{display:flex}
        .app-confirm-card{width:min(20.5rem,100%);max-width:100%;background:rgba(255,253,249,.94);border:1px solid rgba(255,255,255,.72);border-radius:18px;box-shadow:0 20px 48px rgba(90,40,80,.16),inset 0 1px 0 rgba(255,255,255,.8);backdrop-filter:blur(18px) saturate(1.2);-webkit-backdrop-filter:blur(18px) saturate(1.2);padding:1.15rem 1.15rem 1.05rem}
        .app-confirm-title{font-family:var(--font-display),Georgia,serif;font-size:1.35rem;font-weight:500;color:var(--charcoal,#2c2520);margin:0 0 .45rem;letter-spacing:-0.02em;line-height:1.25}
        .app-confirm-message{font-family:var(--font-sans),'DM Sans',system-ui,sans-serif;font-size:.9rem;color:var(--muted,#9a8d85);line-height:1.55;margin:0 0 1.05rem;white-space:pre-line}
        .app-confirm-actions{display:flex;justify-content:flex-end;align-items:center;gap:.5rem;flex-wrap:wrap}
        .app-confirm-btn{border:1.5px solid rgba(181,68,90,.22);border-radius:999px;background:rgba(255,255,255,.92);color:var(--charcoal,#2c2520);padding:.48rem .95rem;font-size:.85rem;font-weight:600;cursor:pointer;font-family:var(--font-sans),'DM Sans',system-ui,sans-serif;transition:background .2s ease,border-color .2s ease,color .2s ease,box-shadow .2s ease}
        .app-confirm-btn:hover{background:rgba(255,245,248,.96);border-color:var(--deep-rose,#b5445a);color:var(--deep-rose,#b5445a)}
        .app-confirm-btn.primary{background:linear-gradient(135deg,#c24e68 0%,#d878a0 55%,#b070c8 100%);border-color:rgba(255,255,255,.35);color:#fff;box-shadow:0 6px 16px rgba(181,68,90,.22)}
        .app-confirm-btn.primary:hover{background:linear-gradient(135deg,#b04058 0%,#c86890 55%,#9f60b8 100%);border-color:rgba(255,255,255,.35);color:#fff}
        @media (max-width:380px){
            .app-confirm-card{padding:1rem .95rem .9rem;border-radius:16px}
            .app-confirm-title{font-size:1.2rem}
            .app-confirm-actions{flex-direction:column-reverse;align-items:stretch}
            .app-confirm-btn{width:100%;text-align:center;justify-content:center}
        }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement('div');
    overlay.className = 'app-confirm-overlay';
    overlay.innerHTML = `
        <div class="app-confirm-card" role="dialog" aria-modal="true" aria-labelledby="appConfirmTitle">
            <div class="app-confirm-title" id="appConfirmTitle">Please Confirm</div>
            <div class="app-confirm-message" id="appConfirmMessage"></div>
            <div class="app-confirm-actions">
                <button type="button" class="app-confirm-btn" id="appConfirmCancel">Cancel</button>
                <button type="button" class="app-confirm-btn primary" id="appConfirmOk">Confirm</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const msgEl = overlay.querySelector('#appConfirmMessage');
    const titleEl = overlay.querySelector('#appConfirmTitle');
    const cancelBtn = overlay.querySelector('#appConfirmCancel');
    const okBtn = overlay.querySelector('#appConfirmOk');

    window.openConfirmModal = function(message, opts) {
        const options = opts || {};
        titleEl.textContent = options.title || 'Please Confirm';
        msgEl.textContent = message || 'Are you sure you want to continue?';
        cancelBtn.textContent = options.cancelText || 'Cancel';
        okBtn.textContent = options.confirmText || 'Confirm';
        return new Promise(function(resolve) {
            overlay.classList.add('show');
            if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();
            const close = function(result) {
                overlay.classList.remove('show');
                if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();
                overlay.removeEventListener('click', handleOverlayClick);
                cancelBtn.removeEventListener('click', onCancel);
                okBtn.removeEventListener('click', onConfirm);
                document.removeEventListener('keydown', onKey);
                resolve(result);
            };
            const onCancel = function() { close(false); };
            const onConfirm = function() { close(true); };
            const handleOverlayClick = function(e) { if (e.target === overlay) close(false); };
            const onKey = function(e) {
                if (e.key === 'Escape') close(false);
                if (e.key === 'Enter') close(true);
            };
            overlay.addEventListener('click', handleOverlayClick);
            cancelBtn.addEventListener('click', onCancel);
            okBtn.addEventListener('click', onConfirm);
            document.addEventListener('keydown', onKey);
        });
    };
})();

// Unified prompt modal helper (styled replacement for window.prompt)
(function setupUnifiedPromptModal() {
    if (window.openPromptModal) return;

    const style = document.createElement('style');
    style.textContent = `
        .app-prompt-overlay{position:fixed;inset:0;background:rgba(42,35,30,.48);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);display:none;align-items:center;justify-content:center;padding:clamp(.75rem,3vw,1.25rem);z-index:12001}
        .app-prompt-overlay.show{display:flex}
        .app-prompt-card{width:min(22rem,100%);max-width:100%;background:rgba(255,253,249,.94);border:1px solid rgba(255,255,255,.72);border-radius:18px;box-shadow:0 20px 48px rgba(90,40,80,.16),inset 0 1px 0 rgba(255,255,255,.8);backdrop-filter:blur(18px) saturate(1.2);-webkit-backdrop-filter:blur(18px) saturate(1.2);padding:1.15rem 1.15rem 1.05rem}
        .app-prompt-title{font-family:var(--font-display),Georgia,serif;font-size:1.35rem;font-weight:500;color:var(--charcoal,#2c2520);margin:0 0 .45rem;letter-spacing:-0.02em;line-height:1.25}
        .app-prompt-message{font-family:var(--font-sans),'DM Sans',system-ui,sans-serif;font-size:.9rem;color:var(--muted,#9a8d85);line-height:1.55;margin:0 0 .75rem;white-space:pre-line}
        .app-prompt-input{width:100%;box-sizing:border-box;font-family:var(--font-sans),'DM Sans',system-ui,sans-serif;font-size:.875rem;color:var(--charcoal,#2c2520);background:rgba(255,255,255,.9);border:1.5px solid rgba(181,68,90,.22);border-radius:10px;padding:.5rem .75rem;outline:none;transition:border-color .2s ease,box-shadow .2s ease;margin-bottom:1rem}
        .app-prompt-input:focus{border-color:var(--deep-rose,#b5445a);box-shadow:0 0 0 3px rgba(181,68,90,.1)}
        .app-prompt-actions{display:flex;justify-content:flex-end;align-items:center;gap:.5rem;flex-wrap:wrap}
        .app-prompt-btn{border:1.5px solid rgba(181,68,90,.22);border-radius:999px;background:rgba(255,255,255,.92);color:var(--charcoal,#2c2520);padding:.48rem .95rem;font-size:.85rem;font-weight:600;cursor:pointer;font-family:var(--font-sans),'DM Sans',system-ui,sans-serif;transition:background .2s ease,border-color .2s ease,color .2s ease,box-shadow .2s ease}
        .app-prompt-btn:hover{background:rgba(255,245,248,.96);border-color:var(--deep-rose,#b5445a);color:var(--deep-rose,#b5445a)}
        .app-prompt-btn.primary{background:linear-gradient(135deg,#c24e68 0%,#d878a0 55%,#b070c8 100%);border-color:rgba(255,255,255,.35);color:#fff;box-shadow:0 6px 16px rgba(181,68,90,.22)}
        .app-prompt-btn.primary:hover{background:linear-gradient(135deg,#b04058 0%,#c86890 55%,#9f60b8 100%);border-color:rgba(255,255,255,.35);color:#fff}
        @media (max-width:380px){
            .app-prompt-card{padding:1rem .95rem .9rem;border-radius:16px}
            .app-prompt-title{font-size:1.2rem}
            .app-prompt-actions{flex-direction:column-reverse;align-items:stretch}
            .app-prompt-btn{width:100%;text-align:center}
        }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement('div');
    overlay.className = 'app-prompt-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `
        <div class="app-prompt-card" role="document">
            <div class="app-prompt-title" id="appPromptTitle">Enter Details</div>
            <div class="app-prompt-message" id="appPromptMessage"></div>
            <input type="text" class="app-prompt-input" id="appPromptInput" autocomplete="off" />
            <div class="app-prompt-actions">
                <button type="button" class="app-prompt-btn" id="appPromptCancel">Cancel</button>
                <button type="button" class="app-prompt-btn primary" id="appPromptOk">OK</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const msgEl = overlay.querySelector('#appPromptMessage');
    const titleEl = overlay.querySelector('#appPromptTitle');
    const inputEl = overlay.querySelector('#appPromptInput');
    const cancelBtn = overlay.querySelector('#appPromptCancel');
    const okBtn = overlay.querySelector('#appPromptOk');

    // Returns the trimmed input string on confirm, or null on cancel — same as window.prompt()
    window.openPromptModal = function(message, opts) {
        const options = opts || {};
        titleEl.textContent = options.title || 'Enter Details';
        msgEl.textContent = message || '';
        inputEl.value = options.defaultValue || '';
        inputEl.placeholder = options.placeholder || '';
        cancelBtn.textContent = options.cancelText || 'Cancel';
        okBtn.textContent = options.confirmText || 'OK';
        return new Promise(function(resolve) {
            overlay.classList.add('show');
            if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();
            // Focus input after paint
            requestAnimationFrame(function() { inputEl.focus(); inputEl.select(); });
            const close = function(result) {
                overlay.classList.remove('show');
                if (typeof updateChatFabVisibility === 'function') updateChatFabVisibility();
                overlay.removeEventListener('click', handleOverlayClick);
                cancelBtn.removeEventListener('click', onCancel);
                okBtn.removeEventListener('click', onConfirm);
                inputEl.removeEventListener('keydown', onInputKey);
                resolve(result);
            };
            const onCancel = function() { close(null); };
            const onConfirm = function() { close(inputEl.value.trim() || ''); };
            const handleOverlayClick = function(e) { if (e.target === overlay) close(null); };
            const onInputKey = function(e) {
                if (e.key === 'Enter') { e.preventDefault(); onConfirm(); }
                if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
            };
            overlay.addEventListener('click', handleOverlayClick);
            cancelBtn.addEventListener('click', onCancel);
            okBtn.addEventListener('click', onConfirm);
            inputEl.addEventListener('keydown', onInputKey);
        });
    };
})();

// Global money formatting for UI text: ₱/Php/PHP + number
(function setupMoneyFormatter() {
    const moneyPattern = /(₱\s*|PHP\s*|Php\s*)(\d[\d,]*(?:\.\d+)?)/g;
    const moneyCheckPattern = /(₱\s*|PHP\s*|Php\s*)(\d[\d,]*(?:\.\d+)?)/;

    window.formatMoneyValue = function(value) {
        const n = Number(String(value).replace(/,/g, ''));
        if (!Number.isFinite(n)) return value;
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(n);
    };

    function formatNodeText(node) {
        if (!node || !node.nodeValue || !moneyCheckPattern.test(node.nodeValue)) return;
        const next = node.nodeValue.replace(moneyPattern, function(_, prefix, amount) {
            return prefix + window.formatMoneyValue(amount);
        });
        if (next !== node.nodeValue) node.nodeValue = next;
    }

    function formatMoneyIn(root) {
        if (!root) return;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode: function(textNode) {
                const parent = textNode.parentElement;
                if (!parent) return NodeFilter.FILTER_REJECT;
                const tag = parent.tagName;
                if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'BUTTON') {
                    return NodeFilter.FILTER_REJECT;
                }
                if (parent.closest('[data-no-money-format], .tender-btn, .tender-quick')) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        let n;
        while ((n = walker.nextNode())) formatNodeText(n);
    }

    // Initial pass
    formatMoneyIn(document.body);

    // Re-format dynamically injected or updated content
    const observer = new MutationObserver(function(mutations) {
        for (const m of mutations) {
            if (m.type === 'characterData') {
                formatNodeText(m.target);
                continue;
            }
            m.addedNodes.forEach(function(node) {
                if (node.nodeType === Node.TEXT_NODE) {
                    formatNodeText(node);
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    formatMoneyIn(node);
                }
            });
        }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
})();

// Initialize cart display
updateCartCount();
updateCartDisplay();
updateChatFabVisibility();

// Keep chat FAB hidden while any modal / overlay is open
(function setupChatFabOverlayWatcher() {
    if (typeof MutationObserver === 'undefined') return;
    let scheduled = false;
    const schedule = function () {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(function () {
            scheduled = false;
            updateChatFabVisibility();
        });
    };
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'hidden'],
    });
})();
    
/* --- SCRIPT BREAK --- */

    function viewProduct(productId) {
        window.location.href = "/products/0".replace('0', productId);
    }

    (function () {
        const cfg = document.getElementById('browsePageConfig');
        const grid = document.getElementById('browseProductGrid');
        const searchEl = document.getElementById('browseSearchInput');
        const sortEl = document.getElementById('browseSort');
        const emptyEl = document.getElementById('browseEmptyState');
        if (!grid || !searchEl || !sortEl) return;

        let activeCategorySlug = ((cfg && cfg.dataset.initialCategory) || '').toLowerCase().trim();

        function norm(s) { return (s || '').toLowerCase(); }

        function setActiveChip() {
            document.querySelectorAll('.browse-chip').forEach(function (btn) {
                const s = norm(btn.getAttribute('data-category-slug'));
                const on = (activeCategorySlug === '' && s === '') || (activeCategorySlug !== '' && s === activeCategorySlug);
                btn.classList.toggle('browse-chip--active', on);
            });
        }

        function applySortAll() {
            const mode = sortEl.value;
            const sorted = Array.from(grid.querySelectorAll('.product-card'));
            if (mode === 'price_low') {
                sorted.sort(function (a, b) {
                    return parseFloat(a.dataset.effectivePrice || 0) - parseFloat(b.dataset.effectivePrice || 0);
                });
            } else if (mode === 'price_high') {
                sorted.sort(function (a, b) {
                    return parseFloat(b.dataset.effectivePrice || 0) - parseFloat(a.dataset.effectivePrice || 0);
                });
            } else if (mode === 'name') {
                sorted.sort(function (a, b) {
                    return norm(a.dataset.name).localeCompare(norm(b.dataset.name));
                });
            } else {
                sorted.sort(function (a, b) {
                    return (b.dataset.created || '').localeCompare(a.dataset.created || '');
                });
            }
            sorted.forEach(function (el) { grid.appendChild(el); });
        }

        function applyFilters() {
            const q = norm(searchEl.value.trim());
            let any = false;
            let visibleCount = 0;
            grid.querySelectorAll('.product-card').forEach(function (card) {
                const slug = norm(card.getAttribute('data-category-slug'));
                const hay = norm(card.getAttribute('data-search-hay') || '');
                const catOk = !activeCategorySlug || slug === activeCategorySlug;
                const qOk = !q || hay.indexOf(q) !== -1;
                const show = catOk && qOk;
                card.style.display = show ? '' : 'none';
                if (show) {
                    any = true;
                    visibleCount += 1;
                }
            });
            applySortAll();
            if (emptyEl) emptyEl.style.display = any ? 'none' : 'block';
        }

        document.querySelectorAll('.browse-chip').forEach(function (btn) {
            btn.addEventListener('click', function () {
                activeCategorySlug = norm(btn.getAttribute('data-category-slug'));
                setActiveChip();
                applyFilters();
            });
        });

        searchEl.addEventListener('input', applyFilters);
        sortEl.addEventListener('change', applyFilters);

        function bootBrowse() {
            if (activeCategorySlug) {
                var match = false;
                document.querySelectorAll('.browse-chip').forEach(function (b) {
                    if (norm(b.getAttribute('data-category-slug')) === activeCategorySlug) match = true;
                });
                if (!match) activeCategorySlug = '';
            }
            setActiveChip();
            applyFilters();
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootBrowse);
        } else {
            bootBrowse();
        }
    })();

/* --- SCRIPT BREAK --- */

    window.__eflowersChatUnread = 0;

/* --- SCRIPT BREAK --- */

    // ═══════════════════════════════════════════════════════════════════════
    // CHAT WIDGET — Client-side logic
    // ═══════════════════════════════════════════════════════════════════════
    const chatWidget = (() => {
        const API = '/api/v1/chat';
        let _token = null;
        let _userId = null;
        let _userRole = null;
        let _convos = [];
        let _activeConvoId = null;
        let _activeOtherUid = null;
        let _onlineByUserId = {};
        let _inboxPresenceTimer = null;
        let _messages = [];
        let _pollTimer = null;
        let _messagesPollBusy = false;
        let _unreadPollBusy = false;
        let _typingTimer = null;
        let _typingPollTimer = null;
        let _typingKeepAlive = null;
        let _lastTypingPing = 0;
        let _unreadPollTimer = null;
        let _liveSyncTimer = null;
        let _readPollTimer = null;
        let _onlinePollTimer = null;
        let _lastUnreadCount = 0;
        let _lastMessagesFingerprint = '';
        let _lastInboxFingerprint = '';
        let _allStores = null;
        let _deliverableStores = [];
        let _loadingDeliverableStores = false;
        let _locallyReadIds = new Set(); // suppress poll race after opening a thread
        let _supportFaqs = null;
        let _quickAnswersMode = false;
        let _preferredOrderId = null;
        let _pendingOrderContext = null;
        let _threadOrderContext = null;
        let _suggestOrderId = null;
        let _openingFromOrderDetails = false;

        function _headers() {
            const h = { 'Content-Type': 'application/json' };
            if (_token) h['Authorization'] = 'Bearer ' + _token;
            return h;
        }

        // Fetch wrapper that includes cookies for session auth
        function _fetch(url, opts = {}) {
            opts.credentials = 'include';
            if (!opts.headers) opts.headers = _headers();
            return fetch(url, opts);
        }

        function _timeAgo(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            const now = new Date();
            const diff = (now - d) / 1000;
            if (diff < 60) return 'now';
            if (diff < 3600) return Math.floor(diff / 60) + 'm';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h';
            return Math.floor(diff / 86400) + 'd';
        }

        function _initials(name) {
            if (!name) return '?';
            const parts = name.trim().split(' ');
            return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : parts[0][0].toUpperCase();
        }

        const DEFAULT_CUSTOMER_AVATAR_URL = '/static/images/default-customer-avatar.svg';

        function _customerDefaultAvatarHtml(size) {
            size = size || 38;
            return `<img class="avatar avatar--customer-default" src="${DEFAULT_CUSTOMER_AVATAR_URL}" alt="" style="width:${size}px;height:${size}px;object-fit:cover;border-radius:50%;">`;
        }

        function _avatarHtml(url, name, size, customerDefault) {
            size = size || 38;
            if (url) return `<img class="avatar" src="${url}" alt="" style="width:${size}px;height:${size}px;">`;
            if (customerDefault) return _customerDefaultAvatarHtml(size);
            return `<div class="avatar-placeholder" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.37)}px;">${_initials(name)}</div>`;
        }

        function _withPresenceDot(avatarHtml, isOnline) {
            if (!isOnline) return avatarHtml;
            return `<div class="avatar-wrap">${avatarHtml}<span class="presence-dot" title="Online" aria-label="Online"></span></div>`;
        }

        function _isUserOnlineCached(uid) {
            if (uid == null || uid === '') return false;
            return !!_onlineByUserId[String(uid)];
        }

        async function _refreshOnlineStatuses(userIds) {
            const ids = Array.from(new Set(
                (userIds || [])
                    .map(function (id) { return parseInt(id, 10); })
                    .filter(function (id) { return Number.isFinite(id) && id > 0; })
            ));
            if (!ids.length) return;
            try {
                const res = await _fetch(API + '/presence/status', {
                    method: 'POST',
                    headers: _headers(),
                    body: JSON.stringify({ user_ids: ids }),
                });
                const data = await res.json();
                const online = (data && data.online) || {};
                Object.keys(online).forEach(function (k) {
                    _onlineByUserId[k] = !!online[k];
                });
            } catch (e) { }
        }

        function _inboxPartnerIds() {
            return (_convos || [])
                .map(function (c) {
                    const other = c.other_user || {};
                    return other.id || null;
                })
                .filter(Boolean);
        }

        async function _refreshInboxPresence({ rerender = true } = {}) {
            await _refreshOnlineStatuses(_inboxPartnerIds());
            if (rerender && !_activeConvoId) {
                _renderInbox({ skipPresenceRefresh: true });
            }
            _applyHeaderPresence();
        }

        function _startInboxPresencePoll() {
            if (_inboxPresenceTimer) return;
            _inboxPresenceTimer = setInterval(function () {
                if (document.hidden) return;
                const overlay = document.getElementById('chat-overlay');
                if (!overlay || !overlay.classList.contains('open')) return;
                // Thread open: dedicated online poll in _startPoll owns status
                if (_activeConvoId) return;
                _refreshInboxPresence({ rerender: true });
            }, 20000);
        }

        function _setDetailStatus(online) {
            const el = document.getElementById('chat-detail-status');
            if (!el || _quickAnswersMode) return;
            if (online) {
                el.innerHTML = '<span class="online-dot"></span> Online';
            } else {
                el.innerHTML = '<span class="offline-dot"></span> Offline';
            }
        }

        function _stopInboxPresencePoll() {
            if (_inboxPresenceTimer) {
                clearInterval(_inboxPresenceTimer);
                _inboxPresenceTimer = null;
            }
        }

        function _applyHeaderPresence() {
            if (!_activeOtherUid) return;
            const online = _isUserOnlineCached(_activeOtherUid);
            _setDetailStatus(online);
            // No avatar green dot in the open thread — Online/Offline text already shows it
            const el = document.getElementById('chat-detail-avatar');
            if (!el) return;
            const bare = el.getAttribute('data-bare-avatar');
            if (!bare) return;
            el.innerHTML = bare;
        }

        function _adminAvatar(size) {
            size = size || 38;
            const iconSize = Math.max(14, Math.round(size * 0.46));
            return `<div class="avatar-badge admin" style="width:${size}px;height:${size}px;"><i class="ri-shield-user-line" style="font-size:${iconSize}px;"></i></div>`;
        }

        function _botAvatar(size) {
            size = size || 38;
            const iconSize = Math.max(14, Math.round(size * 0.46));
            return `<div class="avatar-badge bot" style="width:${size}px;height:${size}px;"><i class="ri-robot-2-line" style="font-size:${iconSize}px;"></i></div>`;
        }

        // ═══ INIT ═══
        function init(token, userId, role) {
            _token = token;
            _userId = userId;
            _userRole = role || _userRole;
            const fab = document.getElementById('chat-fab');
            if (fab && !fab.hasAttribute('hidden')) fab.style.display = 'flex';
            _updateSupportEntryVisibility();
            _updateStoreDiscoveryVisibility();
            if (_userId) {
                // Prefer server-rendered count, then session cache — never flash to 0
                let seeded = 0;
                if (typeof window.__eflowersChatUnread === 'number') {
                    seeded = window.__eflowersChatUnread;
                } else {
                    try {
                        const cached = sessionStorage.getItem('eflowers_chat_unread');
                        if (cached != null) seeded = parseInt(cached, 10) || 0;
                    } catch (e) { }
                }
                if (seeded > 0) _setFabBadge(seeded);
                _lastInboxBadge = seeded;
                _inboxBadgeConfirmed = seeded > 0;

                // Inbox is source of truth while drawer is closed (seller page jumps)
                _syncBadgeFromInbox();
                if (!_unreadPollTimer) {
                    _unreadPollTimer = setInterval(function () {
                        const drawerOpen = !!document.getElementById('chat-overlay')?.classList.contains('open');
                        // Thread open: message poll owns freshness — skip unread churn
                        if (drawerOpen && _activeConvoId) return;
                        if (drawerOpen) _pollUnread();
                        else _syncBadgeFromInbox();
                    }, 20000);
                }
                if (!_badgeVisibilityBound) {
                    _badgeVisibilityBound = true;
                    document.addEventListener('visibilitychange', function () {
                        if (!document.hidden && _userId) _syncBadgeFromInbox();
                    });
                    window.addEventListener('pageshow', function () {
                        if (_userId) _syncBadgeFromInbox();
                    });
                }

                // Deep-link from seller notification panel: ?open_chat=<conversation_id>
                try {
                    const params = new URLSearchParams(window.location.search || '');
                    const openChatId = parseInt(params.get('open_chat') || '', 10);
                    if (openChatId) {
                        setTimeout(function () {
                            open();
                            openConvo(openChatId);
                            params.delete('open_chat');
                            const qs = params.toString();
                            const next = window.location.pathname + (qs ? '?' + qs : '') + (window.location.hash || '');
                            window.history.replaceState({}, '', next);
                        }, 400);
                    }
                } catch (e) { }
            }
        }

        let _badgeVisibilityBound = false;
        let _badgeInboxSyncing = false;
        let _badgeInboxQueued = false;
        let _inboxBadgeConfirmed = false;
        let _lastInboxBadge = 0;

        /** Same source of truth as opening the chat modal — critical for seller/admin. */
        async function _syncBadgeFromInbox() {
            if (!_userId) return;
            if (_badgeInboxSyncing) {
                _badgeInboxQueued = true;
                return;
            }
            const drawerOpen = !!document.getElementById('chat-overlay')?.classList.contains('open');
            // While reading a thread, message/read polls own the badge
            if (drawerOpen && _activeConvoId) return;
            _badgeInboxSyncing = true;
            try {
                const res = await _fetch(API + '/conversations', { headers: _headers() });
                if (!res.ok) return;
                const data = await res.json();
                const next = data.conversations || [];
                if (!drawerOpen) {
                    _convos = next;
                }
                const localTotal = next.reduce(function (sum, c) {
                    return sum + (c.unread_count || 0);
                }, 0);
                _lastInboxBadge = localTotal;
                _inboxBadgeConfirmed = true;
                _setFabBadge(localTotal);
            } catch (e) {
                console.error('Chat: badge inbox sync failed', e);
            } finally {
                _badgeInboxSyncing = false;
                if (_badgeInboxQueued) {
                    _badgeInboxQueued = false;
                    _syncBadgeFromInbox();
                }
            }
        }

        function _isCustomerRole() {
            return !_userRole || _userRole === 'customer';
        }

        function _updateStoreDiscoveryVisibility() {
            const show = _isCustomerRole();
            const searchBar = document.querySelector('#chat-inbox-view .chat-search-bar');
            const results = document.getElementById('chat-search-results');
            if (searchBar) searchBar.style.display = show ? '' : 'none';
            if (results && !show) results.style.display = 'none';
        }

        // ═══ TOGGLE / OPEN / CLOSE ═══
        function toggle() {
            // Already initialized - just toggle drawer
            if (_userId) {
                const overlay = document.getElementById('chat-overlay');
                if (overlay.classList.contains('open')) { close(); }
                else { open(); }
                return;
            }

            // Not initialized yet - try session check (website uses Flask sessions)
            fetch('/api/chat/session-check', { credentials: 'include' })
                .then(res => {
                    if (!res.ok) throw new Error('Not logged in');
                    return res.json();
                })
                .then(data => {
                    if (data.user_id) {
                        init(data.token || '', data.user_id, data.role || '');
                        open();
                    } else {
                        window.location.href = '/login';
                    }
                })
                .catch(e => {
                    window.location.href = '/login';
                });
        }

        function open() {
            document.getElementById('chat-overlay').classList.add('open');
            showInbox();
            _startLiveSync();
            _startInboxPresencePoll();
        }

        function _ensureDrawerOpen() {
            document.getElementById('chat-overlay').classList.add('open');
            _startLiveSync();
            _startInboxPresencePoll();
        }

        function _blankDetailView(placeholderName) {
            _stopPoll();
            _activeConvoId = null;
            _activeOtherUid = null;
            _quickAnswersMode = false;
            _messages = [];
            _lastMessagesFingerprint = '';
            document.getElementById('chat-inbox-view').style.display = 'none';
            document.getElementById('chat-detail-view').style.display = 'flex';
            _setComposerVisible(true);
            const area = document.getElementById('chat-messages-area');
            if (area) area.innerHTML = '';
            const nameEl = document.getElementById('chat-detail-name');
            if (nameEl) nameEl.textContent = placeholderName || '';
            const statusEl = document.getElementById('chat-detail-status');
            if (statusEl) statusEl.innerHTML = '<span class="offline-dot"></span> Connecting…';
            const avatarEl = document.getElementById('chat-detail-avatar');
            if (avatarEl) {
                avatarEl.removeAttribute('data-bare-avatar');
                avatarEl.innerHTML = '';
            }
            const moreBtn = document.getElementById('chat-convo-more-btn');
            if (moreBtn) moreBtn.style.display = 'none';
        }

        function close() {
            _closeAllMenus();
            document.getElementById('chat-overlay').classList.remove('open');
            _stopPoll();
            _stopLiveSync();
            _stopInboxPresencePoll();
            _activeConvoId = null;
            _activeOtherUid = null;
            _locallyReadIds.clear();
            _syncBadgeFromInbox();
        }

        // ═══ INBOX ═══
        function showInbox() {
            _closeAllMenus();
            _activeConvoId = null;
            _activeOtherUid = null;
            _preferredOrderId = null;
            _pendingOrderContext = null;
            _suggestOrderId = null;
            _openingFromOrderDetails = false;
            _quickAnswersMode = false;
            _stopPoll();
            document.getElementById('chat-inbox-view').style.display = '';
            document.getElementById('chat-detail-view').style.display = 'none';
            _updateSupportEntryVisibility();
            // Paint optimistic local state immediately (Messenger-style), then reconcile
            _renderInbox();
            _loadDeliverableStores();
            _loadConversations({ quiet: true });
            _refreshInboxPresence({ rerender: true });
        }

        function _updateSupportEntryVisibility() { }

        function _applyLocalReadOverrides(list) {
            if (!list || !list.length) return list || [];
            if (!_locallyReadIds.size && !_activeConvoId) return list;
            return list.map(function (c) {
                if ((_locallyReadIds.has(c.id) || c.id === _activeConvoId) && (c.unread_count || 0) > 0) {
                    return Object.assign({}, c, { unread_count: 0 });
                }
                return c;
            });
        }

        async function _loadConversations({ quiet = false } = {}) {
            try {
                const res = await _fetch(API + '/conversations', { headers: _headers() });
                const data = await res.json();
                const raw = data.conversations || [];
                // Only lift suppress when server confirms unread is gone
                _locallyReadIds.forEach(function (id) {
                    const row = raw.find(function (c) { return c.id === id; });
                    if (row && (row.unread_count || 0) === 0 && id !== _activeConvoId) {
                        _locallyReadIds.delete(id);
                    }
                });
                let next = _applyLocalReadOverrides(raw);
                const fingerprint = next.map(function (c) {
                    return [c.id, c.unread_count || 0, c.last_message_at || '', c.last_message_text || ''].join(':');
                }).join('|');
                if (fingerprint === _lastInboxFingerprint && quiet) {
                    return;
                }
                _lastInboxFingerprint = fingerprint;
                _convos = next;
                _renderInbox();
                const localTotal = (_convos || []).reduce(function (sum, c) {
                    return sum + (c.unread_count || 0);
                }, 0);
                if (typeof localTotal === 'number') _setFabBadge(localTotal);
            } catch (e) { console.error('Chat: load convos failed', e); }
        }

        function _setFabBadge(count) {
            const n = Math.max(0, Number(count) || 0);
            _lastUnreadCount = n;
            try { sessionStorage.setItem('eflowers_chat_unread', String(n)); } catch (e) { }
            const badge = document.getElementById('chat-badge');
            const fab = document.getElementById('chat-fab');
            if (!badge || !fab) return;
            if (n > 0) {
                badge.textContent = n > 99 ? '99+' : String(n);
                badge.classList.add('show');
                fab.classList.add('pulse');
            } else {
                badge.classList.remove('show');
                fab.classList.remove('pulse');
            }
        }

        function _clearConversationUnreadLocal(convoId) {
            _locallyReadIds.add(convoId);
            _lastInboxFingerprint = '';
            const c = _convos.find(x => x.id === convoId);
            if (c) {
                const prev = c.unread_count || 0;
                c.unread_count = 0;
                if (prev > 0) _setFabBadge(_lastUnreadCount - prev);
            }
            // Keep hidden inbox DOM in sync so back-navigation is instant
            try { _renderInbox(); } catch (e) { console.error('Chat: inbox render failed', e); }
        }

        function _touchConversationPreview(convoId, previewText, senderId) {
            const idx = _convos.findIndex(c => c.id === convoId);
            if (idx === -1) {
                _loadConversations({ quiet: true });
                return;
            }
            const c = Object.assign({}, _convos[idx]);
            c.last_message_text = previewText;
            c.last_message_at = new Date().toISOString();
            c.last_sender_id = senderId;
            _convos.splice(idx, 1);
            _convos.unshift(c);
            _lastInboxFingerprint = '';
            // Update inbox DOM even while viewing a thread (instant back-nav)
            try { _renderInbox(); } catch (e) { console.error('Chat: inbox render failed', e); }
        }

        function _startLiveSync() {
            _stopLiveSync();
            _liveSyncTimer = setInterval(async () => {
                if (document.hidden) return;
                // Thread open: message poll owns freshness — skip badge/inbox churn
                if (_activeConvoId) return;
                await _pollUnread();
                await _loadConversations({ quiet: true });
            }, 12000);
        }

        // Background badge sync while drawer is closed (seller/admin dashboards)
        let _closedBadgeTimer = null;
        function _ensureClosedBadgeSync() {
            if (_closedBadgeTimer) return;
            _closedBadgeTimer = setInterval(function () {
                if (document.hidden || !_userId) return;
                const drawerOpen = !!document.getElementById('chat-overlay')?.classList.contains('open');
                if (!drawerOpen) _syncBadgeFromInbox();
            }, 20000);
        }
        _ensureClosedBadgeSync();

        function _stopLiveSync() {
            if (_liveSyncTimer) {
                clearInterval(_liveSyncTimer);
                _liveSyncTimer = null;
            }
        }

        async function _getAllStores() {
            if (_allStores) return _allStores;
            try {
                const res = await _fetch('/api/v1/customer/stores?include_outside_location=1', { headers: _headers() });
                const data = await res.json();
                _allStores = Array.isArray(data) ? data : [];
            } catch (e) {
                console.error('Chat: failed to load stores', e);
                _allStores = [];
            }
            return _allStores;
        }

        async function _loadDeliverableStores() {
            if (!_isCustomerRole() || _loadingDeliverableStores) return;
            _loadingDeliverableStores = true;
            try {
                const res = await _fetch('/api/v1/customer/stores?include_outside_location=1', { headers: _headers() });
                const data = await res.json();
                const list = Array.isArray(data) ? data : [];
                _deliverableStores = list.filter(function (s) {
                    return s.can_deliver_to_customer === true;
                });
                if (_renderInbox) {
                    _renderInbox();
                }
            } catch (e) {
                console.error('Chat: failed to load deliverable stores', e);
            } finally {
                _loadingDeliverableStores = false;
            }
        }

        function _renderDeliverableStoresHtml() {
            if (!_isCustomerRole() || !_deliverableStores || _deliverableStores.length === 0) {
                return '';
            }
            const cards = _deliverableStores.map(function (s) {
                const name = _esc(s.name || 'Store');
                const thumb = s.logo_url
                    ? `<img class="thumb" src="${s.logo_url}" alt="${name}" onerror="this.outerHTML='<div class=\\'thumb-placeholder\\'>${(name || 'S')[0]}</div>'">`
                    : `<div class="thumb-placeholder">${(name || 'S')[0]}</div>`;
                return `<div class="chat-deliverable-card" onclick="chatWidget.openWithStore(${s.id})" title="Chat with ${name}">
                <div class="thumb-wrap">
                    ${thumb}
                    <div class="delivery-check" title="Delivers to your address"><i class="ri-check-line"></i></div>
                </div>
                <div class="store-name">${name}</div>
                <div class="store-sub">Delivers</div>
            </div>`;
            }).join('');

            return `<div class="chat-deliverable-section">
            <div class="chat-deliverable-header">
                <span class="chat-deliverable-title"><i class="ri-map-pin-user-line"></i> Delivers to you</span>
            </div>
            <div class="chat-deliverable-track">
                ${cards}
            </div>
        </div>`;
        }

        function _renderInbox(opts) {
            opts = opts || {};
            const list = document.getElementById('chat-inbox-list');
            if (!list) return;
            const isAdmin = _userRole === 'admin';
            const isCustomer = _isCustomerRole();
            const supportConvo = isAdmin
                ? null
                : _convos.find(c => c.other_user && c.other_user.role === 'admin');
            const normalConvos = isAdmin
                ? _convos
                : _convos.filter(c => !(c.other_user && c.other_user.role === 'admin'));

            const deliverableRail = isCustomer ? _renderDeliverableStoresHtml() : '';
            const hasDeliverable = isCustomer && _deliverableStores && _deliverableStores.length > 0;
            const hasAnyItems = (!isAdmin) || normalConvos.length > 0 || hasDeliverable;

            if (!hasAnyItems) {
                list.innerHTML = '<div class="inbox-empty" id="chat-inbox-empty">No conversations yet</div>';
                return;
            }

            const parts = [];
            if (deliverableRail) {
                parts.push(deliverableRail);
            }

            if (!isAdmin) {
                const supportUnread = supportConvo ? (supportConvo.unread_count || 0) : 0;
                const supportPreview = supportConvo
                    ? (supportConvo.last_message_text || 'Chat with admin support')
                    : 'Chat with admin support';
                const supportTime = supportConvo ? _timeAgo(supportConvo.last_message_at) : '';
                const supportUid = supportConvo && supportConvo.other_user ? supportConvo.other_user.id : null;
                const supportAvatar = _withPresenceDot(
                    _adminAvatar(44),
                    _isUserOnlineCached(supportUid)
                );
                parts.push(`<div class="inbox-item" data-support-item="1" onclick="chatWidget._openSupportFromInbox()">
                ${supportAvatar}
                <div class="info">
                    <div class="name">Contact Support</div>
                    <div class="preview">${_esc(supportPreview)}</div>
                </div>
                <div class="meta">
                    <div class="time">${supportTime}</div>
                    ${supportUnread > 0 ? `<div class="unread-badge">${supportUnread > 99 ? '99+' : supportUnread}</div>` : ''}
                </div>
            </div>`);

                parts.push(`<div class="inbox-item" onclick="chatWidget.openQuickAnswers()">
                ${_botAvatar(44)}
                <div class="info">
                    <div class="name">Quick Answers</div>
                    <div class="preview">Tap to browse common questions</div>
                </div>
                <div class="meta">
                    <div class="time"></div>
                </div>
            </div>`);
            }
            parts.push(...normalConvos.map(c => {
                const other = c.other_user || {};
                const unread = c.unread_count || 0;
                // Customers see the store name; sellers see customer name; for riders show "{Store} Rider"
                const isSeller = (other.role === 'seller');
                const isRider = (other.role === 'rider' || c.is_rider_thread === true);
                const storeName = c.store_name || (c.order_context && c.order_context.store_name) || '';
                const displayName = isRider
                    ? (storeName ? `${storeName} Rider` : (other.full_name ? `${other.full_name} (Rider)` : 'Rider'))
                    : (isSeller ? (c.store_name || other.full_name || 'Unknown') : (other.full_name || 'Unknown'));
                const displayAvatar = isSeller ? (c.store_logo || other.avatar_url) : other.avatar_url;
                const avatar = _withPresenceDot(
                    _avatarHtml(displayAvatar, displayName, 44, !isSeller),
                    _isUserOnlineCached(other.id)
                );
                return `<div class="inbox-item" onclick="chatWidget.openConvo(${c.id})">
                ${avatar}
                <div class="info">
                    <div class="name">${displayName}</div>
                    <div class="preview">${c.last_message_text || 'No messages yet'}</div>
                </div>
                <div class="meta">
                    <div class="time">${_timeAgo(c.last_message_at)}</div>
                    ${unread > 0 ? `<div class="unread-badge">${unread > 99 ? '99+' : unread}</div>` : ''}
                    ${(other.role !== 'admin') ? `<button class="inbox-item-delete" onclick="event.stopPropagation(); chatWidget.confirmDeleteConversation(${c.id}, '${_esc(displayName)}')" title="Delete conversation">
                        <i class="ri-delete-bin-line"></i>
                    </button>` : ''}
                </div>
            </div>`;
            }));
            list.innerHTML = parts.join('');

            // Presence is refreshed on open + a slow timer — not on every inbox paint
            // (avoids spamming /presence/status during quiet sync).
        }

        // ═══ OPEN CONVERSATION (by ID) ═══
        async function openConvo(convoId) {
            _quickAnswersMode = false;
            if (!_openingFromOrderDetails) _suggestOrderId = null;
            _stopPoll();
            _messages = [];
            _lastMessagesFingerprint = '';
            _activeConvoId = convoId;
            document.getElementById('chat-inbox-view').style.display = 'none';
            document.getElementById('chat-detail-view').style.display = 'flex';
            _setComposerVisible(true);
            const area = document.getElementById('chat-messages-area');
            if (area) area.innerHTML = '';

            // Find conversation data
            let convo = _convos.find(c => c.id === convoId);
            if (convo) {
                _renderHeader(convo);
            }
            if (!convo) {
                try {
                    const qs = _preferredOrderId ? ('?order_id=' + _preferredOrderId) : '';
                    const res = await _fetch(API + '/conversations/' + convoId + qs, { headers: _headers() });
                    const data = await res.json();
                    convo = data.conversation;
                    if (convo && !convo.order_context && data.order_context) {
                        convo.order_context = data.order_context;
                    }
                } catch (e) { }
            }
            if (convo) {
                const existingIdx = _convos.findIndex(c => c.id === convo.id);
                if (existingIdx >= 0) {
                    _convos[existingIdx] = convo;
                } else {
                    _convos.unshift(convo);
                }
                _renderHeader(convo);
            }

            let orderCtx = (convo && convo.order_context) || _pendingOrderContext || null;
            _pendingOrderContext = null;
            if (orderCtx) _threadOrderContext = orderCtx;

            const otherRole = convo && convo.other_user ? convo.other_user.role : null;
            const needsOrderCtx = !orderCtx && (otherRole === 'rider' || _userRole === 'rider' || (convo && convo.is_rider_thread));
            if (needsOrderCtx || (_preferredOrderId && orderCtx && orderCtx.order_id !== _preferredOrderId)) {
                try {
                    const qs = _preferredOrderId ? ('?order_id=' + _preferredOrderId) : '';
                    const res = await _fetch(API + '/conversations/' + convoId + qs, { headers: _headers() });
                    const data = await res.json();
                    if (data.conversation) {
                        convo = data.conversation;
                        const existingIdx = _convos.findIndex(c => c.id === convo.id);
                        if (existingIdx >= 0) {
                            _convos[existingIdx] = convo;
                        } else {
                            _convos.unshift(convo);
                        }
                        _renderHeader(convo);
                        orderCtx = convo.order_context || data.order_context || orderCtx;
                        if (orderCtx) _threadOrderContext = orderCtx;
                    }
                } catch (e) { }
            }

            // Instantly clear unread badge + mark read (don't wait for messages)
            try {
                _clearConversationUnreadLocal(convoId);
                _markRead();
            } catch (e) {
                console.error('Chat: local unread clear failed', e);
            }
            _lastMessagesFingerprint = '';
            await _loadMessages({ forceScroll: true });
            _refreshOrderSuggest();
            _startPoll();
        }

        // ═══ STORE SEARCH ═══
        let _searchTimer = null;

        async function searchStores(query) {
            const resultsEl = document.getElementById('chat-search-results');
            const inboxEl = document.getElementById('chat-inbox-list');

            if (!query || query.trim().length === 0) {
                resultsEl.style.display = 'none';
                inboxEl.style.display = '';
                return;
            }

            const allStores = await _getAllStores();
            const q = query.toLowerCase().trim();
            const matches = (allStores || []).filter(s => (s.name || '').toLowerCase().includes(q)).slice(0, 10);

            if (matches.length === 0) {
                resultsEl.innerHTML = '<div class="inbox-empty" style="padding:20px;">No stores found</div>';
            } else {
                resultsEl.innerHTML = matches.map(s => {
                    const logo = s.logo_url
                        ? `<div class="store-initial"><img src="${s.logo_url}" onerror="this.parentElement.textContent='${(s.name || 'S')[0]}'"></div>`
                        : `<div class="store-initial">${(s.name || 'S')[0]}</div>`;
                    const addr = s.address ? `<div class="addr">${_esc(s.address)}</div>` : '';
                    const deliveryBadge = s.can_deliver_to_customer === true
                        ? `<div class="delivery-badge"><i class="ri-checkbox-circle-fill"></i> Delivers to your address</div>`
                        : '';
                    return `<div class="search-result-item" onclick="chatWidget.openWithStore(${s.id})">
                    ${logo}
                    <div class="store-info">
                        <div class="name">${_esc(s.name)}</div>
                        ${deliveryBadge}
                        ${addr}
                    </div>
                    <button class="msg-btn">Message</button>
                </div>`;
                }).join('');
            }

            resultsEl.style.display = '';
            inboxEl.style.display = 'none';
        }

        // ═══ OPEN CONVERSATION WITH STORE (from product page) ═══
        async function openWithStore(storeId) {
            // Clear search
            const searchInput = document.getElementById('chat-store-search');
            if (searchInput) searchInput.value = '';
            const resultsEl = document.getElementById('chat-search-results');
            if (resultsEl) resultsEl.style.display = 'none';
            const inboxEl = document.getElementById('chat-inbox-list');
            if (inboxEl) inboxEl.style.display = '';
            if (!_userId) {
                // Try session check first
                try {
                    const chk = await fetch('/api/chat/session-check', { credentials: 'include' });
                    if (chk.ok) {
                        const d = await chk.json();
                        if (d.user_id) { init(d.token || '', d.user_id, d.role || ''); }
                        else { window.location.href = '/login'; return; }
                    } else { window.location.href = '/login'; return; }
                } catch (e) { window.location.href = '/login'; return; }
            }
            try {
                const res = await _fetch(API + '/conversations', {
                    method: 'POST',
                    headers: _headers(),
                    body: JSON.stringify({ store_id: storeId }),
                });
                const data = await res.json();
                if (data.conversation) {
                    open();
                    const existingIdx = _convos.findIndex(c => c.id === data.conversation.id);
                    if (existingIdx >= 0) {
                        _convos[existingIdx] = data.conversation;
                    } else {
                        _convos.unshift(data.conversation);
                    }
                    openConvo(data.conversation.id);
                } else {
                    alert(data.error || 'Could not open chat');
                }
            } catch (e) { console.error('Chat: open with store failed', e); }
        }

        async function openWithRiderOrder(orderId) {
            if (!orderId) return;
            if (!_userId) {
                try {
                    const chk = await fetch('/api/chat/session-check', { credentials: 'include' });
                    if (chk.ok) {
                        const d = await chk.json();
                        if (d.user_id) { init(d.token || '', d.user_id, d.role || ''); }
                        else { window.location.href = '/login'; return; }
                    } else { window.location.href = '/login'; return; }
                } catch (e) { window.location.href = '/login'; return; }
            }
            _preferredOrderId = orderId;
            _suggestOrderId = orderId;
            _openingFromOrderDetails = true;
            _ensureDrawerOpen();
            _blankDetailView('Rider');
            try {
                const res = await _fetch(API + '/conversations/rider-order', {
                    method: 'POST',
                    headers: _headers(),
                    body: JSON.stringify({ order_id: orderId }),
                });
                const data = await res.json();
                if (data.conversation) {
                    _pendingOrderContext = data.conversation.order_context || data.order_context || null;
                    const existingIdx = _convos.findIndex(c => c.id === data.conversation.id);
                    if (existingIdx >= 0) {
                        _convos[existingIdx] = data.conversation;
                    } else {
                        _convos.unshift(data.conversation);
                    }
                    await openConvo(data.conversation.id);
                } else {
                    alert(data.error || 'Could not open rider chat');
                }
            } catch (e) {
                console.error('Chat: open with rider order failed', e);
                alert('Could not open rider chat');
            } finally {
                _openingFromOrderDetails = false;
            }
        }

        function _hideOrderSuggest() {
            const el = document.getElementById('chat-order-suggest');
            if (el) el.classList.remove('show');
        }

        function _parseJsonObject(raw) {
            if (!raw) return null;
            if (typeof raw === 'object') return raw;
            if (typeof raw !== 'string') return null;
            const s = raw.trim();
            if (!s.startsWith('{')) return null;
            try { return JSON.parse(s); } catch (e) { return null; }
        }

        function _normalizeOrderCard(raw) {
            const src = _parseJsonObject(raw);
            if (!src || typeof src !== 'object' || Array.isArray(src)) return null;
            const orderId = Number(src.order_id || src.orderId || 0) || 0;
            const items = Array.isArray(src.items) ? src.items : [];
            const rawTotal = src.total_amount != null ? src.total_amount
                : (src.totalAmount != null ? src.totalAmount : src.total);
            let number = src.order_number || src.orderNumber || '';
            if (!number || String(number).indexOf('undefined') !== -1) {
                number = orderId ? ('ORD-' + String(orderId).padStart(5, '0')) : '';
            }
            if (!orderId && !number && !items.length) return null;
            return {
                order_id: orderId,
                order_number: number,
                status: src.status || '',
                store_name: src.store_name || src.storeName || '',
                total_amount: Number(rawTotal || 0),
                item_count: src.item_count || src.itemCount || items.length,
                items: items,
            };
        }

        function _normalizeCustomTicket(raw) {
            const src = _parseJsonObject(raw);
            if (!src || typeof src !== 'object' || Array.isArray(src)) return null;
            const id = Number(src.id || src.ticket_id || 0) || 0;
            const title = src.title || '';
            if (!id && !title) return null;
            return {
                id: id,
                ticket_number: src.ticket_number || ('CQT-' + String(id)),
                store_id: Number(src.store_id || 0),
                store_name: src.store_name || '',
                customer_id: Number(src.customer_id || 0),
                title: title,
                category: src.category || 'bouquets',
                base_price: Number(src.base_price || 0),
                inclusions: src.inclusions || '',
                image_url: src.image_url || '',
                status: src.status || 'pending',
                expires_at: src.expires_at || src.expires_at_raw || null,
                remaining_seconds: Number(src.remaining_seconds || 0),
                is_expired: !!src.is_expired,
                order_id: src.order_id ? Number(src.order_id) : null,
            };
        }

        function _customTicketFromMessage(m) {
            if (!m || m.is_deleted || m.message_type === 'deleted') return null;
            if (m.custom_ticket && typeof m.custom_ticket === 'object') {
                return _normalizeCustomTicket(m.custom_ticket);
            }
            if (m.message_type === 'custom_ticket') {
                return _normalizeCustomTicket(m.text);
            }
            return null;
        }

        function _formatRemainingSeconds(sec) {
            if (sec <= 0) return 'Expired';
            const h = Math.floor(sec / 3600);
            const m = Math.floor((sec % 3600) / 60);
            const s = Math.floor(sec % 60);
            if (h > 0) return `${h}h ${m}m left`;
            return `${m}m ${s}s left`;
        }

        function _customTicketCardHtml(ticket, isSent) {
            if (!ticket) return '<div class="chat-cq-card">Custom Quote</div>';
            const isExpired = ticket.status === 'expired' || (ticket.remaining_seconds != null && ticket.remaining_seconds <= 0 && ticket.status === 'pending');
            const canCheckout = !isSent && ticket.status === 'pending' && !isExpired;

            let statusBadgeHtml = '';
            if (ticket.status === 'accepted') {
                statusBadgeHtml = `<span class="chat-cq-timer accepted" style="background:#e8f5e9;color:#2e7d32;"><i class="ri-checkbox-circle-fill"></i> Ordered</span>`;
            } else if (ticket.status === 'cancelled') {
                statusBadgeHtml = `<span class="chat-cq-timer expired"><i class="ri-close-circle-line"></i> Cancelled</span>`;
            } else if (isExpired) {
                statusBadgeHtml = `<span class="chat-cq-timer expired"><i class="ri-time-line"></i> Expired</span>`;
            } else {
                statusBadgeHtml = `<span class="chat-cq-timer" data-expires-at="${_esc(ticket.expires_at || '')}" data-status="${ticket.status}">
                <i class="ri-time-line"></i> <span class="chat-cq-timer-text">${_formatRemainingSeconds(ticket.remaining_seconds)}</span>
            </span>`;
            }

            const imgHtml = ticket.image_url
                ? `<img class="chat-cq-img" src="${_esc(ticket.image_url)}" alt="${_esc(ticket.title)}" onclick="chatWidget.openLightbox('${_esc(ticket.image_url)}')">`
                : `<div class="chat-cq-img-placeholder"><i class="ri-flower-line"></i><span style="font-size:11px;margin-top:4px;">Custom Design</span></div>`;

            const inclusionsHtml = ticket.inclusions
                ? `<div class="chat-cq-inclusions">${_esc(ticket.inclusions)}</div>`
                : '';

            let actionHtml = '';
            if (ticket.status === 'accepted' && _userRole === 'customer') {
                actionHtml = `<button type="button" class="chat-cq-btn" onclick="window.location.href='/my-account?page=orders'" style="background:var(--charcoal);color:#fff;"><i class="ri-file-list-3-line"></i> View Order</button>`;
            } else if (canCheckout) {
                actionHtml = `<button type="button" class="chat-cq-btn" onclick="chatWidget.openTicketCheckout(${ticket.id})"><i class="ri-shopping-cart-2-line"></i> Review &amp; Checkout</button>`;
            } else if (isSent && ticket.status === 'pending') {
                actionHtml = `<div class="chat-cq-status-pill" style="background:#fef7e0;color:#b06000;"><i class="ri-hourglass-line"></i> Awaiting Customer Checkout</div>`;
            }

            return `<div class="chat-cq-card" data-ticket-id="${ticket.id}">
            <div class="chat-cq-top">
                <span class="chat-cq-badge">${_esc(ticket.category.toUpperCase())}</span>
                ${statusBadgeHtml}
            </div>
            <div class="chat-cq-img-wrap">
                ${imgHtml}
            </div>
            <div class="chat-cq-title">${_esc(ticket.title)}</div>
            ${inclusionsHtml}
            <div class="chat-cq-price-row">
                <span class="chat-cq-price-lbl">Arrangement Base Quote</span>
                <span class="chat-cq-price-val">${_formatPeso(ticket.base_price)}</span>
            </div>
            <div style="margin-top:4px;">
                ${actionHtml}
            </div>
        </div>`;
        }

        function _orderCardFromPreviewText(text) {
            const s = String(text || '');
            const m = s.match(/ORD-(\d+)/i);
            if (!m) return null;
            const orderId = parseInt(m[1], 10);
            if (!orderId) return null;
            const number = 'ORD-' + String(orderId).padStart(5, '0');
            return {
                order_id: orderId,
                order_number: number,
                status: '',
                store_name: '',
                total_amount: 0,
                item_count: 0,
                items: [],
            };
        }

        function _orderCardFromMessage(m) {
            if (!m || m.is_deleted || m.message_type === 'deleted') return null;
            return _normalizeOrderCard(m.order_card)
                || _normalizeOrderCard(m.text)
                || ((m.message_type === 'order_card') ? _orderCardFromPreviewText(m.text) : null);
        }

        function _threadHasOrderCard(orderId) {
            return _messages.some(function (m) {
                if (!m || m.is_deleted) return false;
                const stored = _normalizeOrderCard(m.order_card) || _normalizeOrderCard(m.text)
                    || ((m.message_type === 'order_card') ? _orderCardFromPreviewText(m.text) : null);
                return stored && Number(stored.order_id) === Number(orderId);
            });
        }

        function _formatPeso(n) {
            const num = Number(n || 0);
            return '₱' + num.toLocaleString('en-PH', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }

        function _orderCardPreview(ctx) {
            if (!ctx) return 'Order details';
            return 'Order ' + (ctx.order_number || ('ORD-' + (ctx.order_id || '')));
        }

        function _orderCardHtml(ctx) {
            if (!ctx) return '<div class="chat-oc-card">Order details</div>';
            const orderNo = ctx.order_number || (ctx.order_id ? ('ORD-' + String(ctx.order_id).padStart(5, '0')) : 'Order');
            const items = (ctx.items || []).slice(0, 4);
            const extra = Math.max(0, (ctx.item_count || (ctx.items || []).length) - items.length);
            const rows = items.map(function (item) {
                const title = [item.name, item.variant_name].filter(Boolean).join(' · ');
                const thumb = item.image_url
                    ? `<img src="${_esc(item.image_url)}" alt="">`
                    : '<div class="oc-ph"><i class="ri-flower-line"></i></div>';
                const addons = Array.isArray(item.addons) ? item.addons : [];
                const addonHtml = addons.map(function (a) {
                    const qty = Number(a.quantity || 1);
                    const label = '+ ' + (a.name || 'Add-on') + (qty > 1 ? (' ×' + qty) : '');
                    return `<div class="oc-addon">${_esc(label)}</div>`;
                }).join('');
                return `<div class="oc-item">${thumb}<div class="oc-item-body"><div class="oc-item-name">${_esc(title || 'Product')}</div>${addonHtml ? `<div class="oc-addons">${addonHtml}</div>` : ''}</div><span class="oc-qty">×${item.quantity || 1}</span></div>`;
            }).join('');
            return `<div class="chat-oc-card" data-order-id="${_esc(String(ctx.order_id || ''))}">
            <div class="oc-num">${_esc(orderNo)}</div>
            ${rows}
            ${extra > 0 ? `<div class="oc-more">+${extra} more</div>` : ''}
            <div class="oc-total"><span class="lbl">Total</span><span>${_formatPeso(ctx.total_amount)}</span></div>
        </div>`;
        }

        function _refreshOrderSuggest() {
            const el = document.getElementById('chat-order-suggest');
            if (!el) return;
            if (!_suggestOrderId || !_activeConvoId || _threadHasOrderCard(_suggestOrderId)) {
                el.classList.remove('show');
                return;
            }
            const copy = document.getElementById('chat-order-suggest-copy');
            if (copy) {
                copy.textContent = _userRole === 'rider'
                    ? 'Share this order so the customer knows which delivery you mean.'
                    : 'Share this order so your rider knows what you’re asking about.';
            }
            el.classList.add('show');
        }

        function dismissOrderSuggest() {
            _suggestOrderId = null;
            _hideOrderSuggest();
        }

        async function shareOrderCard() {
            if (!_activeConvoId || !_suggestOrderId) return;
            try {
                const res = await _fetch(API + '/conversations/' + _activeConvoId + '/messages', {
                    method: 'POST',
                    headers: _headers(),
                    body: JSON.stringify({ message_type: 'order_card', order_id: _suggestOrderId }),
                });
                const data = await res.json();
                if (data.message) {
                    if (data.already_sent && _messages.some(function (m) { return m.id === data.message.id; })) {
                        _hideOrderSuggest();
                        _suggestOrderId = null;
                        return;
                    }
                    if (!_messages.some(function (m) { return m.id === data.message.id; })) {
                        _messages.push(data.message);
                    }
                    _lastMessagesFingerprint = '';
                    _renderMessages({ scroll: true });
                    _touchConversationPreview(
                        _activeConvoId,
                        _orderCardPreview(_orderCardFromMessage(data.message)),
                        data.message.sender_id || _userId
                    );
                    _hideOrderSuggest();
                    _suggestOrderId = null;
                } else {
                    alert(data.error || 'Could not share order details');
                }
            } catch (e) {
                console.error('Chat: share order card failed', e);
            }
        }

        async function openSupport() {
            if (!_userId) {
                try {
                    const chk = await fetch('/api/chat/session-check', { credentials: 'include' });
                    if (!chk.ok) { window.location.href = '/login'; return; }
                    const d = await chk.json();
                    if (d.user_id) {
                        init(d.token || '', d.user_id, d.role || '');
                    } else {
                        window.location.href = '/login';
                        return;
                    }
                } catch (e) {
                    window.location.href = '/login';
                    return;
                }
            }
            try {
                const res = await _fetch(API + '/conversations/support', {
                    method: 'POST',
                    headers: _headers(),
                });
                const data = await res.json();
                if (res.ok && data.conversation) {
                    open();
                    openConvo(data.conversation.id);
                } else {
                    alert(data.error || 'Could not open support chat');
                }
            } catch (e) {
                console.error('Chat: open support failed', e);
            }
        }

        async function _loadSupportFaqs() {
            if (Array.isArray(_supportFaqs)) return _supportFaqs;
            try {
                const res = await fetch('/api/support-faqs', { credentials: 'same-origin' });
                const data = await res.json();
                _supportFaqs = Array.isArray(data.faqs) ? data.faqs : [];
            } catch (e) {
                _supportFaqs = [];
            }
            return _supportFaqs;
        }

        function _setComposerVisible(show) {
            const inputBar = document.getElementById('chat-input-bar');
            const replyBar = document.getElementById('chat-reply-bar');
            const imgPreview = document.getElementById('chat-img-preview');
            const typing = document.getElementById('chat-typing');
            if (inputBar) inputBar.style.display = show ? '' : 'none';
            if (replyBar) replyBar.style.display = show ? '' : 'none';
            if (imgPreview) imgPreview.style.display = 'none';
            if (typing) typing.classList.remove('is-visible');
            if (!show) _hideOrderSuggest();
        }

        async function openQuickAnswers() {
            _quickAnswersMode = true;
            _activeConvoId = null;
            _stopPoll();
            document.getElementById('chat-inbox-view').style.display = 'none';
            document.getElementById('chat-detail-view').style.display = 'flex';
            _setComposerVisible(false);
            const moreBtn = document.getElementById('chat-convo-more-btn');
            if (moreBtn) moreBtn.style.display = 'none';

            document.getElementById('chat-detail-avatar').innerHTML = _botAvatar(38);
            document.getElementById('chat-detail-name').textContent = 'Quick Answers';
            document.getElementById('chat-detail-status').innerHTML = '<span class="online-dot"></span> Auto Help';

            const area = document.getElementById('chat-messages-area');
            area.innerHTML = '<div style="text-align:center;color:var(--muted);padding:20px 0;font-size:13px;">Loading FAQs...</div>';

            const faqs = await _loadSupportFaqs();
            if (!faqs.length) {
                area.innerHTML = '<div style="text-align:center;color:var(--muted);padding:28px 0;font-size:13px;">No FAQs available yet.</div>';
                return;
            }

            area.innerHTML = '<div class="msg-row received"><div class="bubble">Hi! Select a question below to get an instant answer.</div></div>' +
                faqs.map(f => `<button type="button" class="qa-question" onclick="chatWidget.showFaqAnswer(${f.id})">${_esc(f.question)}</button>`).join('');
            area.scrollTop = 0;
        }

        function showFaqAnswer(faqId) {
            if (!Array.isArray(_supportFaqs)) return;
            const hit = _supportFaqs.find(f => f.id === faqId);
            if (!hit) return;
            const area = document.getElementById('chat-messages-area');
            if (!area) return;
            area.innerHTML += `<div class="msg-row sent"><div class="bubble">${_esc(hit.question)}</div></div>`;
            area.innerHTML += `<div class="msg-row received"><div class="bubble">${_esc(hit.answer || '')}</div></div>`;
            area.scrollTop = area.scrollHeight;
        }

        function _openSupportFromInbox() {
            const supportConvo = _convos.find(c => c.other_user && c.other_user.role === 'admin');
            if (supportConvo && supportConvo.id) {
                openConvo(supportConvo.id);
                return;
            }
            openSupport();
        }

        function _renderHeader(convo) {
            const other = convo.other_user || {};
            const isSeller = (other.role === 'seller');
            const isRider = (other.role === 'rider' || convo.is_rider_thread === true);
            const isAdmin = (other.role === 'admin');
            const moreBtn = document.getElementById('chat-convo-more-btn');
            if (moreBtn) {
                moreBtn.style.display = (isAdmin || _quickAnswersMode) ? 'none' : 'flex';
            }
            const quoteBtn = document.getElementById('chat-custom-quote-btn');
            if (quoteBtn) {
                const canQuote = (_userRole === 'seller' || _userRole === 'seller_admin') && !isAdmin && !isRider && !_quickAnswersMode;
                quoteBtn.style.display = canQuote ? 'inline-flex' : 'none';
            }
            const displayName = isRider
                ? (other.full_name || (convo.store_name ? convo.store_name + ' Rider' : 'Rider'))
                : (isSeller ? (convo.store_name || other.full_name || 'Unknown') : (other.full_name || 'Unknown'));
            const displayAvatar = isSeller ? (convo.store_logo || other.avatar_url) : other.avatar_url;
            const avatarEl = document.getElementById('chat-detail-avatar');
            let bare;
            if (other.role === 'admin') {
                bare = _adminAvatar(38);
            } else {
                bare = _avatarHtml(displayAvatar, displayName, 38, !isSeller);
            }
            _activeOtherUid = other.id || convo.seller_id || null;
            const storeId = convo.store_id || (other.store_id || null);
            if (avatarEl) {
                avatarEl.setAttribute('data-bare-avatar', bare);
                // Header uses Online/Offline text — skip avatar presence dot
                avatarEl.innerHTML = bare;
                if (isSeller && storeId) {
                    avatarEl.style.cursor = 'pointer';
                    avatarEl.title = `View ${displayName}'s store`;
                    avatarEl.onclick = function () {
                        window.location.href = `/store/${storeId}`;
                    };
                } else {
                    avatarEl.style.cursor = 'default';
                    avatarEl.removeAttribute('title');
                    avatarEl.onclick = null;
                }
            }
            const nameEl = document.getElementById('chat-detail-name');
            if (nameEl) {
                nameEl.textContent = displayName;
                if (isSeller && storeId) {
                    nameEl.style.cursor = 'pointer';
                    nameEl.title = `View ${displayName}'s store`;
                    nameEl.onclick = function () {
                        window.location.href = `/store/${storeId}`;
                    };
                } else {
                    nameEl.style.cursor = 'default';
                    nameEl.removeAttribute('title');
                    nameEl.onclick = null;
                }
            }
            // Paint cached presence immediately, then confirm with the server
            _setDetailStatus(_isUserOnlineCached(_activeOtherUid));
            _checkOnline(_activeOtherUid);
            if (_activeOtherUid) {
                _refreshOnlineStatuses([_activeOtherUid]).then(function () {
                    _applyHeaderPresence();
                });
            }
        }

        async function _checkOnline(uid) {
            if (!uid) return;
            try {
                const res = await _fetch(API + '/users/' + uid + '/online', { headers: _headers() });
                const data = await res.json();
                const online = !!data.is_online;
                _onlineByUserId[String(uid)] = online;
                if (String(uid) === String(_activeOtherUid)) {
                    _setDetailStatus(online);
                    _applyHeaderPresence();
                }
            } catch (e) { }
        }

        // ═══ MESSAGES ═══
        async function _loadMessages({ forceScroll = false } = {}) {
            if (!_activeConvoId) return;
            if (_messagesPollBusy && !forceScroll) return;
            const convoId = _activeConvoId;
            _messagesPollBusy = true;
            try {
                const area = document.getElementById('chat-messages-area');
                const nearBottom = !area || (area.scrollHeight - area.scrollTop - area.clientHeight) < 100;
                const prevLastId = _messages.length ? _messages[_messages.length - 1].id : null;
                const res = await _fetch(API + '/conversations/' + convoId + '/messages?per_page=50', { headers: _headers() });
                const data = await res.json();
                if (_activeConvoId !== convoId) return;
                const next = data.messages || [];
                const fingerprint = next.map(function (m) {
                    const oc = m.order_card || {};
                    return [m.id, m.is_deleted ? 1 : 0, m.is_read ? 1 : 0, m.message_type || '', oc.order_id || '', oc.order_number || '', (oc.items || []).length, m.text || '', m.image_url || ''].join(':');
                }).join('|');
                const unchanged = fingerprint === _lastMessagesFingerprint && !forceScroll;
                const nextLastId = next.length ? next[next.length - 1].id : null;
                const hasNew = nextLastId && nextLastId !== prevLastId;
                if (_activeConvoId !== convoId) return;
                _messages = next;
                _lastMessagesFingerprint = fingerprint;
                if (!unchanged) {
                    _renderMessages({ scroll: forceScroll || !prevLastId || (hasNew && nearBottom) });
                }
                _refreshOrderSuggest();

                // Keep inbox preview live while reading this thread
                if (hasNew && next.length) {
                    const last = next[next.length - 1];
                    const preview = last.message_type === 'image'
                        ? (last.text || '[Image]')
                        : last.message_type === 'order_card'
                            ? _orderCardPreview(_orderCardFromMessage(last))
                            : (last.text || '');
                    _touchConversationPreview(_activeConvoId, preview, last.sender_id);
                    if (last.sender_id != _userId) _markRead();
                }
            } catch (e) { console.error('Chat: load msgs failed', e); }
            finally { _messagesPollBusy = false; }
        }

        function _renderMessages({ scroll = true } = {}) {
            const area = document.getElementById('chat-messages-area');
            if (_messages.length === 0) {
                area.innerHTML = '<div style="text-align:center;color:var(--muted);padding:30px 0;font-size:13px;">Start a conversation!</div>';
                return;
            }

            let html = '';
            let lastDate = '';
            const lastSentByMe = [..._messages].reverse().find(m => m.sender_id == _userId);

            // Helper: build quoted reply HTML
            function replyHtml(m) {
                if (!m.reply_to_id) return '';
                const rName = _esc(m.reply_to_sender_name || 'Unknown');
                let rText;
                if (m.reply_to_text) {
                    rText = _esc(m.reply_to_text);
                } else if (m.reply_to_message_type === 'deleted') {
                    rText = '<i>Message has been deleted</i>';
                } else if (m.reply_to_message_type === 'image' || !m.reply_to_message_type) {
                    rText = _esc('[Image]');
                } else {
                    rText = '<i>Message has been deleted</i>';
                }
                return `<div class="msg-reply-quote"><div class="reply-name">${rName}</div><div class="reply-text">${rText}</div></div>`;
            }

            function senderMetaHtml(m, isSent) {
                if (isSent) return '';
                const senderName = _esc(m.sender_name || 'Unknown');
                return `<div class="msg-sender-meta"><span class="msg-sender-name">${senderName}</span></div>`;
            }

            function senderAvatarHtml(m, isSent) {
                if (isSent) return '';
                if (m.sender_avatar) return `<img class="sender-avatar" src="${m.sender_avatar}" alt="">`;
                if (m.sender_role !== 'seller' && m.sender_role !== 'admin') {
                    return _customerDefaultAvatarHtml(26);
                }
                const name = (m.sender_name || '?').trim();
                const initial = _esc((name[0] || '?').toUpperCase());
                return `<div class="sender-avatar-placeholder">${initial}</div>`;
            }

            // Helper: build 3-dot menu
            function menuHtml(m) {
                if (m.is_deleted) return '';
                const isMine = m.sender_id == _userId;
                const menuId = 'msg-menu-' + m.id;
                let items = '';
                items += `<div class="menu-item" onclick="chatWidget.setReply(${m.id})"><i class="ri-reply-line"></i> Reply</div>`;
                if (m.message_type !== 'order_card' && m.text) items += `<div class="menu-item" onclick="chatWidget.copyMessage(${m.id})"><i class="ri-file-copy-line"></i> Copy</div>`;
                if (isMine) items += `<div class="menu-item danger" onclick="chatWidget.deleteMessage(${m.id})"><i class="ri-delete-bin-line"></i> Delete</div>`;
                return `<div class="msg-menu-wrap"><button class="msg-menu-btn" onclick="chatWidget._toggleMenu('${menuId}',event)" title="More"><i class="ri-more-2-fill"></i></button><div class="msg-menu-popup" id="${menuId}">${items}</div></div>`;
            }

            let i = 0;
            while (i < _messages.length) {
                const m = _messages[i];
                const d = new Date(m.created_at);
                const dateStr = d.toLocaleDateString();
                if (dateStr !== lastDate) {
                    html += `<div class="msg-timestamp">${dateStr}</div>`;
                    lastDate = dateStr;
                }

                const isSent = m.sender_id == _userId;
                const cls = isSent ? 'sent' : 'received';
                const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                // Deleted message
                if (m.is_deleted || m.message_type === 'deleted') {
                    html += `<div class="msg-row ${cls}">`;
                    html += senderAvatarHtml(m, isSent);
                    html += `<div class="bubble">${senderMetaHtml(m, isSent)}<div class="msg-deleted-content"><i class="ri-forbid-line"></i> Message has been deleted</div><div style="font-size:10px;color:#999;margin-top:3px;text-align:${isSent ? 'right' : 'left'}">${time}</div></div>`;
                    html += `</div>`;
                    i++; continue;
                }

                const orderCard = _orderCardFromMessage(m);
                if (orderCard) {
                    html += `<div class="msg-row ${cls} chat-oc-row">`;
                    html += senderAvatarHtml(m, isSent);
                    html += `<div class="chat-oc-wrap">${replyHtml(m)}${_orderCardHtml(orderCard)}<div class="oc-time">${time}</div></div>`;
                    html += menuHtml(m);
                    html += `</div>`;
                    if (isSent && m === lastSentByMe && m.is_read) {
                        html += `<div class="msg-seen">Seen</div>`;
                    }
                    i++; continue;
                }

                const customTicket = _customTicketFromMessage(m);
                if (customTicket) {
                    html += `<div class="msg-row ${cls} chat-cq-row">`;
                    html += senderAvatarHtml(m, isSent);
                    html += `<div class="chat-cq-wrap">${replyHtml(m)}${_customTicketCardHtml(customTicket, isSent)}<div class="oc-time" style="font-size:10px;color:#999;margin-top:4px;padding:0 4px;text-align:${isSent ? 'right' : 'left'};">${time}</div></div>`;
                    html += menuHtml(m);
                    html += `</div>`;
                    if (isSent && m === lastSentByMe && m.is_read) {
                        html += `<div class="msg-seen">Seen</div>`;
                    }
                    i++; continue;
                }

                // Group consecutive image-only messages from the same sender
                if (m.message_type === 'image' && m.image_url && !m.text) {
                    const imgs = [m];
                    while (i + 1 < _messages.length && imgs.length < 5) {
                        const next = _messages[i + 1];
                        if (next.message_type === 'image' && next.image_url && !next.text && next.sender_id === m.sender_id && !next.is_deleted) {
                            imgs.push(next);
                            i++;
                        } else break;
                    }

                    html += `<div class="msg-row ${cls}">`;
                    html += senderAvatarHtml(m, isSent);

                    if (imgs.length === 1) {
                        let content = replyHtml(m);
                        content += `<img class="chat-img" src="${m.image_url}" alt="Image" onclick="chatWidget.openLightbox('${m.image_url}')">`;
                        html += `<div class="bubble">${senderMetaHtml(m, isSent)}${content}<div style="font-size:10px;color:#999;margin-top:3px;text-align:${isSent ? 'right' : 'left'}">${time}</div></div>`;
                    } else {
                        const gCls = 'g' + imgs.length;
                        const gridHtml = imgs.map(img =>
                            `<img class="grid-thumb" src="${img.image_url}" alt="Image" onclick="chatWidget.openLightbox('${img.image_url}')">`
                        ).join('');
                        html += `<div class="bubble">${senderMetaHtml(m, isSent)}<div class="img-grid ${gCls}">${gridHtml}</div><div style="font-size:10px;color:#999;margin-top:3px;text-align:${isSent ? 'right' : 'left'}">${time}</div></div>`;
                    }
                    html += menuHtml(m);
                    html += `</div>`;

                    // Seen receipt for last grouped image
                    const lastImg = imgs[imgs.length - 1];
                    if (isSent && lastImg === lastSentByMe && lastImg.is_read) {
                        html += `<div class="msg-seen">Seen</div>`;
                    }
                } else {
                    // Normal text or image-with-caption message
                    let content = replyHtml(m);
                    if (m.message_type === 'image' && m.image_url) {
                        content += `<img class="chat-img" src="${m.image_url}" alt="Image" onclick="chatWidget.openLightbox('${m.image_url}')">`;
                        if (m.text) content += `<div class="caption">${_esc(m.text)}</div>`;
                    } else {
                        content += _esc(m.text || '');
                    }

                    html += `<div class="msg-row ${cls}">`;
                    html += senderAvatarHtml(m, isSent);
                    html += `<div class="bubble">${senderMetaHtml(m, isSent)}${content}<div style="font-size:10px;color:#999;margin-top:3px;text-align:${isSent ? 'right' : 'left'}">${time}</div></div>`;
                    html += menuHtml(m);
                    html += `</div>`;

                    if (isSent && m === lastSentByMe && m.is_read) {
                        html += `<div class="msg-seen">Seen</div>`;
                    }
                }
                i++;
            }

            area.innerHTML = html;
            if (scroll) area.scrollTop = area.scrollHeight;
        }

        function _esc(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        // ═══ SEND ═══
        async function send() {
            // If there are pending images, send them
            if (_pendingImages.length > 0) {
                await _sendPendingImages();
                return;
            }
            const input = document.getElementById('chat-msg-input');
            const text = input.value.trim();
            if (!text || !_activeConvoId) return;
            input.value = '';
            const replyToId = _replyTo ? _replyTo.id : null;
            cancelReply();

            try {
                const body = { text, message_type: 'text' };
                if (replyToId) body.reply_to_id = replyToId;
                const res = await _fetch(API + '/conversations/' + _activeConvoId + '/messages', {
                    method: 'POST',
                    headers: _headers(),
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (data.message) {
                    _messages.push(data.message);
                    _lastMessagesFingerprint = '';
                    _renderMessages({ scroll: true });
                    _touchConversationPreview(
                        _activeConvoId,
                        data.message.text || text,
                        data.message.sender_id || _userId
                    );
                }
            } catch (e) { console.error('Chat: send failed', e); }
        }

        let _pendingImages = [];
        let _replyTo = null; // { id, sender_name, text }

        function setReply(msgId) {
            const msg = _messages.find(m => m.id === msgId);
            if (!msg) return;
            _replyTo = { id: msg.id, sender_name: msg.sender_name || 'Unknown', text: msg.message_type === 'order_card' ? _orderCardPreview(_orderCardFromMessage(msg)) : (msg.text || (msg.message_type === 'image' ? '[Image]' : '')) };
            document.getElementById('chat-reply-name').textContent = 'Replying to ' + _replyTo.sender_name;
            document.getElementById('chat-reply-text').textContent = _replyTo.text;
            document.getElementById('chat-reply-bar').classList.add('show');
            document.getElementById('chat-msg-input').focus();
            _closeAllMenus();
        }

        function cancelReply() {
            _replyTo = null;
            document.getElementById('chat-reply-bar').classList.remove('show');
        }

        function copyMessage(msgId) {
            const msg = _messages.find(m => m.id === msgId);
            if (!msg || !msg.text) return;
            navigator.clipboard.writeText(msg.text).then(() => {
                // Brief toast
                const toast = document.createElement('div');
                toast.textContent = 'Copied to clipboard';
                toast.style.cssText = 'position:fixed;bottom:120px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:6px 16px;border-radius:20px;font-size:12px;z-index:100001;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 1500);
            }).catch(() => { });
            _closeAllMenus();
        }

        async function deleteMessage(msgId) {
            if (!_activeConvoId) return;
            _closeAllMenus();
            if (!await window.openConfirmModal('Delete this message?')) return;
            try {
                const res = await _fetch(API + '/conversations/' + _activeConvoId + '/messages/' + msgId, {
                    method: 'DELETE', headers: _headers(),
                });
                const data = await res.json();
                if (data.message && typeof data.message === 'object') {
                    const idx = _messages.findIndex(m => m.id === msgId);
                    if (idx !== -1) { _messages[idx] = data.message; _renderMessages(); }
                } else {
                    // Fallback: mark locally
                    const idx = _messages.findIndex(m => m.id === msgId);
                    if (idx !== -1) {
                        _messages[idx].is_deleted = true;
                        _messages[idx].text = null;
                        _messages[idx].image_url = null;
                        _messages[idx].message_type = 'deleted';
                        _renderMessages();
                    }
                }
            } catch (e) { console.error('Chat: delete failed', e); }
        }

        function _menuPortal() {
            return document.getElementById('chat-msg-menu');
        }

        function _positionMenu(popup, btn) {
            const drawer = document.getElementById('chat-drawer');
            const bounds = (drawer || document.getElementById('chat-overlay')).getBoundingClientRect();
            const btnRect = btn.getBoundingClientRect();
            const pad = 8;
            popup.style.visibility = 'hidden';
            popup.classList.add('open');
            const mw = popup.offsetWidth || 148;
            const mh = popup.offsetHeight || 120;
            popup.style.visibility = '';

            let top = btnRect.bottom + 4;
            if (top + mh > bounds.bottom - pad) {
                top = btnRect.top - mh - 4;
            }
            if (top < bounds.top + pad) top = bounds.top + pad;
            if (top + mh > bounds.bottom - pad) {
                top = Math.max(bounds.top + pad, bounds.bottom - pad - mh);
            }

            const isSent = !!btn.closest('.msg-row.sent');
            let left = isSent ? (btnRect.right - mw) : btnRect.left;
            const minL = bounds.left + pad;
            const maxL = bounds.right - pad - mw;
            if (left < minL) left = minL;
            if (left > maxL) left = Math.max(minL, maxL);

            popup.style.top = Math.round(top) + 'px';
            popup.style.left = Math.round(left) + 'px';
            popup.style.right = 'auto';
        }

        function _toggleMenu(id, ev) {
            ev.stopPropagation();
            const source = document.getElementById(id);
            const portal = _menuPortal();
            const btn = ev.currentTarget || ev.target.closest('.msg-menu-btn');
            if (!source || !portal || !btn) return;
            const already = portal.classList.contains('open') && portal.dataset.sourceId === String(id);
            _closeAllMenus();
            if (already) return;
            portal.innerHTML = source.innerHTML;
            portal.dataset.sourceId = id;
            _positionMenu(portal, btn);
        }
        function _closeAllMenus() {
            const portal = _menuPortal();
            if (portal) {
                portal.classList.remove('open');
                portal.innerHTML = '';
                portal.removeAttribute('data-source-id');
            }
            const convoMenu = document.getElementById('chat-convo-menu');
            if (convoMenu) {
                convoMenu.classList.remove('open');
                convoMenu.innerHTML = '';
            }
            document.querySelectorAll('.msg-menu-popup.open, .convo-menu-popup.open').forEach(el => {
                if (el.id !== 'chat-msg-menu' && el.id !== 'chat-convo-menu') el.classList.remove('open');
            });
        }
        document.addEventListener('click', _closeAllMenus);
        window.addEventListener('resize', _closeAllMenus);
        document.getElementById('chat-messages-area').addEventListener('scroll', _closeAllMenus, { passive: true });
        const _menuPortalEl = document.getElementById('chat-msg-menu');
        if (_menuPortalEl) {
            _menuPortalEl.addEventListener('click', function (e) {
                e.stopPropagation();
                if (e.target.closest('.menu-item')) setTimeout(_closeAllMenus, 0);
            });
        }
        const _convoMenuEl = document.getElementById('chat-convo-menu');
        if (_convoMenuEl) {
            _convoMenuEl.addEventListener('click', function (e) {
                e.stopPropagation();
                if (e.target.closest('.menu-item')) setTimeout(_closeAllMenus, 0);
            });
        }

        function toggleConvoMenu(ev) {
            if (ev) ev.stopPropagation();
            const menu = document.getElementById('chat-convo-menu');
            const btn = document.getElementById('chat-convo-more-btn');
            if (!menu || !btn || !_activeConvoId || _quickAnswersMode) {
                _closeAllMenus();
                return;
            }

            const convo = _convos.find(c => c.id === _activeConvoId);
            const other = (convo && convo.other_user) || {};
            if (other.role === 'admin') {
                _closeAllMenus();
                return;
            }

            const isOpen = menu.classList.contains('open');
            _closeAllMenus();
            if (isOpen) return;

            const isSeller = other.role === 'seller';
            const storeId = (convo && convo.store_id) || (other.store_id || null);

            let items = '';
            if (isSeller && storeId) {
                items += `<div class="menu-item" onclick="chatWidget.viewStore()"><i class="ri-store-2-line"></i> Visit Store</div>`;
            }
            items += `<div class="menu-item danger" onclick="chatWidget.deleteCurrentConversation()"><i class="ri-delete-bin-line"></i> Delete Conversation</div>`;

            menu.innerHTML = items;
            menu.classList.add('open');

            const drawer = document.getElementById('chat-drawer');
            const bounds = (drawer || document.getElementById('chat-overlay')).getBoundingClientRect();
            const btnRect = btn.getBoundingClientRect();
            const pad = 8;
            const mw = menu.offsetWidth || 170;
            const mh = menu.offsetHeight || 80;

            let top = btnRect.bottom + 4;
            if (top + mh > bounds.bottom - pad) {
                top = btnRect.top - mh - 4;
            }
            let left = btnRect.right - mw;
            if (left < bounds.left + pad) left = bounds.left + pad;
            if (left + mw > bounds.right - pad) left = bounds.right - pad - mw;

            menu.style.top = Math.round(top) + 'px';
            menu.style.left = Math.round(left) + 'px';
        }

        function viewStore() {
            _closeAllMenus();
            if (!_activeConvoId) return;
            const convo = _convos.find(c => c.id === _activeConvoId);
            const other = (convo && convo.other_user) || {};
            const storeId = (convo && convo.store_id) || (other.store_id || null);
            if (storeId) {
                window.location.href = `/store/${storeId}`;
            }
        }

        async function deleteCurrentConversation() {
            _closeAllMenus();
            if (!_activeConvoId || _quickAnswersMode) return;
            const convoId = _activeConvoId;
            const convo = _convos.find(c => c.id === convoId);
            const other = (convo && convo.other_user) || {};
            if (other.role === 'admin') return;

            let name = 'this conversation';
            if (convo) {
                const isSeller = (other.role === 'seller');
                const isRider = (other.role === 'rider' || convo.is_rider_thread === true);
                name = isRider
                    ? (other.full_name || (convo.store_name ? convo.store_name + ' Rider' : 'Rider'))
                    : (isSeller ? (convo.store_name || other.full_name || 'this seller') : (other.full_name || 'this conversation'));
            } else {
                const nameEl = document.getElementById('chat-detail-name');
                if (nameEl && nameEl.textContent) name = nameEl.textContent.trim();
            }

            const confirmMsg = `Delete your conversation with ${name}?`;
            if (!await window.openConfirmModal(confirmMsg)) return;

            try {
                const res = await _fetch(API + '/conversations/' + convoId, {
                    method: 'DELETE',
                    headers: _headers(),
                });
                if (!res.ok) {
                    console.error('Chat: delete conversation failed');
                    return;
                }
                _convos = _convos.filter(c => c.id !== convoId);
                _locallyReadIds.delete(convoId);

                const remainingUnread = _convos.reduce((sum, c) => sum + (c.unread_count || 0), 0);
                _setFabBadge(remainingUnread);
                _renderInbox();

                // Automatically navigate back to inbox!
                showInbox();
            } catch (e) {
                console.error('Chat: delete conversation error', e);
            }
        }

        async function confirmDeleteConversation(convoId, displayName) {
            _closeAllMenus();
            if (!convoId) return;
            const convo = _convos.find(c => c.id === convoId);
            if (convo && convo.other_user && convo.other_user.role === 'admin') return;

            const confirmMsg = `Delete your conversation with ${displayName || 'this contact'}?`;
            if (!await window.openConfirmModal(confirmMsg)) return;

            try {
                const res = await _fetch(API + '/conversations/' + convoId, {
                    method: 'DELETE',
                    headers: _headers(),
                });
                if (!res.ok) {
                    console.error('Chat: delete conversation failed');
                    return;
                }
                _convos = _convos.filter(c => c.id !== convoId);
                _locallyReadIds.delete(convoId);

                const remainingUnread = _convos.reduce((sum, c) => sum + (c.unread_count || 0), 0);
                _setFabBadge(remainingUnread);
                _renderInbox();

                if (_activeConvoId === convoId) {
                    showInbox();
                }
            } catch (e) {
                console.error('Chat: delete conversation error', e);
            }
        }

        function previewImage(fileInput) {
            const files = Array.from(fileInput.files);
            if (!files.length || !_activeConvoId) { fileInput.value = ''; return; }

            // Limit to 5 total
            const remaining = 5 - _pendingImages.length;
            const toAdd = files.slice(0, remaining);

            toAdd.forEach(file => {
                const reader = new FileReader();
                reader.onload = function (e) {
                    _pendingImages.push({ file, dataUrl: e.target.result });
                    _renderPreviews();
                };
                reader.readAsDataURL(file);
            });

            if (files.length > remaining) {
                alert('You can attach up to 5 images at a time.');
            }
            fileInput.value = '';
        }

        function _renderPreviews() {
            const bar = document.getElementById('chat-img-preview');
            const thumbs = document.getElementById('chat-preview-thumbs');
            const countEl = document.getElementById('chat-preview-count');
            if (_pendingImages.length === 0) {
                bar.style.display = 'none';
                return;
            }
            bar.style.display = 'flex';
            countEl.textContent = _pendingImages.length + '/5';
            thumbs.innerHTML = _pendingImages.map((item, i) =>
                `<div class="preview-thumb-wrap">
                <img src="${item.dataUrl}" alt="Preview">
                <button class="remove-thumb" onclick="chatWidget.removeImage(${i})" title="Remove">&times;</button>
            </div>`
            ).join('');
        }

        function removeImage(index) {
            _pendingImages.splice(index, 1);
            _renderPreviews();
        }

        function cancelImage() {
            _pendingImages = [];
            _renderPreviews();
        }

        async function _sendPendingImages() {
            if (!_pendingImages.length || !_activeConvoId) return;
            const images = [..._pendingImages];
            _pendingImages = [];
            _renderPreviews();

            for (const item of images) {
                const fd = new FormData();
                fd.append('file', item.file);
                try {
                    const res = await _fetch(API + '/conversations/' + _activeConvoId + '/messages/image', {
                        method: 'POST',
                        headers: _token ? { 'Authorization': 'Bearer ' + _token } : {},
                        body: fd,
                    });
                    const data = await res.json();
                    if (data.message) {
                        _messages.push(data.message);
                        _lastMessagesFingerprint = '';
                        _renderMessages({ scroll: true });
                        _touchConversationPreview(
                            _activeConvoId,
                            data.message.text || '[Image]',
                            data.message.sender_id || _userId
                        );
                    }
                } catch (e) { console.error('Chat: send image failed', e); }
            }
        }

        async function confirmSendImage() {
            await _sendPendingImages();
        }

        async function sendImage(fileInput) {
            if (!fileInput.files[0] || !_activeConvoId) return;
            const fd = new FormData();
            fd.append('file', fileInput.files[0]);

            try {
                const res = await _fetch(API + '/conversations/' + _activeConvoId + '/messages/image', {
                    method: 'POST',
                    headers: _token ? { 'Authorization': 'Bearer ' + _token } : {},
                    body: fd,
                });
                const data = await res.json();
                if (data.message) {
                    _messages.push(data.message);
                    _lastMessagesFingerprint = '';
                    _renderMessages({ scroll: true });
                    _touchConversationPreview(
                        _activeConvoId,
                        data.message.text || '[Image]',
                        data.message.sender_id || _userId
                    );
                }
            } catch (e) { console.error('Chat: send image failed', e); }
            fileInput.value = '';
        }

        // ═══ MARK READ ═══
        async function _markRead() {
            if (!_activeConvoId) return;
            const convoId = _activeConvoId;
            _clearConversationUnreadLocal(convoId);
            try {
                await _fetch(API + '/conversations/' + convoId + '/read', { method: 'POST', headers: _headers() });
                // Reconcile only after server has cleared — poll respects _locallyReadIds
                await _pollUnread();
                if (convoId !== _activeConvoId) {
                    _locallyReadIds.delete(convoId);
                }
            } catch (e) { }
        }

        function _hasOpenMenu() {
            const portal = _menuPortal();
            return !!(portal && portal.classList.contains('open'));
        }

        // ═══ POLLING (while a conversation is open) ═══
        function _startPoll() {
            _stopPoll();
            _pollTimer = setInterval(async () => {
                if (document.hidden) return;
                if (!_hasOpenMenu()) await _loadMessages();
            }, 7000);
            // Typing TTL is ~10s — poll often enough that indicators feel live
            _typingPollTimer = setInterval(function () {
                if (!document.hidden && _activeConvoId) _pollTyping();
            }, 2000);
            _pollTyping();
            // Mark read on open + when new messages arrive — not on a tight timer
            _markRead();
            _onlinePollTimer = setInterval(function () {
                if (!document.hidden && _activeConvoId && _activeOtherUid) {
                    _checkOnline(_activeOtherUid);
                }
            }, 15000);
            if (_activeOtherUid) _checkOnline(_activeOtherUid);
        }
        function _stopPoll() {
            if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
            if (_typingPollTimer) { clearInterval(_typingPollTimer); _typingPollTimer = null; }
            if (_readPollTimer) { clearInterval(_readPollTimer); _readPollTimer = null; }
            if (_onlinePollTimer) { clearInterval(_onlinePollTimer); _onlinePollTimer = null; }
            clearTimeout(_typingTimer);
            clearInterval(_typingKeepAlive);
            _typingKeepAlive = null;
        }

        async function _pollUnread() {
            if (!_userId || document.hidden || _unreadPollBusy) return;
            _unreadPollBusy = true;
            try {
                const drawerOpen = !!document.getElementById('chat-overlay')?.classList.contains('open');
                // While drawer is closed, inbox sync owns the FAB (avoids wiping seller badge on page jumps)
                if (!drawerOpen) {
                    await _syncBadgeFromInbox();
                    return;
                }
                const res = await _fetch(API + '/unread-count', { headers: _headers() });
                if (!res.ok) return;
                const data = await res.json();
                let n = Number(data.unread_count) || 0;

                if (_activeConvoId && _locallyReadIds.has(_activeConvoId) && _convos.length) {
                    const localSum = (_convos || []).reduce(function (sum, c) {
                        return sum + (c.unread_count || 0);
                    }, 0);
                    if (n > localSum) n = localSum;
                }

                _setFabBadge(n);
            } catch (e) { }
            finally { _unreadPollBusy = false; }
        }

        // ═══ TYPING ═══
        function _pingTyping() {
            if (!_activeConvoId) return;
            const now = Date.now();
            // Throttle network pings while still refreshing within server TTL.
            if (now - _lastTypingPing < 1800) return;
            _lastTypingPing = now;
            _fetch(API + '/conversations/' + _activeConvoId + '/typing', {
                method: 'POST',
                headers: _headers(),
            }).catch(function () { });
        }

        function onType() {
            if (!_activeConvoId) return;
            _pingTyping();
            clearTimeout(_typingTimer);
            clearInterval(_typingKeepAlive);
            // Keep signaling while the user continues to type.
            _typingKeepAlive = setInterval(_pingTyping, 2000);
            _typingTimer = setTimeout(function () {
                clearInterval(_typingKeepAlive);
                _typingKeepAlive = null;
            }, 4000);
        }

        async function _pollTyping() {
            if (!_activeConvoId) return;
            try {
                const res = await _fetch(API + '/conversations/' + _activeConvoId + '/typing', { headers: _headers() });
                const data = await res.json();
                const el = document.getElementById('chat-typing');
                const nameEl = document.getElementById('chat-typing-name');
                if (!el) return;
                if (data.typing && data.typing.length > 0) {
                    if (nameEl) nameEl.textContent = data.typing[0].full_name || 'Someone';
                    el.classList.add('is-visible');
                } else {
                    el.classList.remove('is-visible');
                }
            } catch (e) { }
        }

        // ═══════════════════════════════════════════════════════════════════
        // CUSTOM QUOTE TICKET ACTIONS (SELLER CREATION & CUSTOMER CHECKOUT)
        // ═══════════════════════════════════════════════════════════════════
        let _activeCheckoutTicket = null;
        let _availableStoreAddons = [];
        let _selectedCheckoutAddons = {}; // optId -> qty
        let _quoteCountdownInterval = null;

        function _startQuoteCountdownTicker() {
            if (_quoteCountdownInterval) return;
            _quoteCountdownInterval = setInterval(() => {
                const timers = document.querySelectorAll('.chat-cq-timer');
                if (!timers.length) return;
                const now = new Date().getTime();
                timers.forEach(t => {
                    const expiresAt = t.getAttribute('data-expires-at');
                    const status = t.getAttribute('data-status');
                    if (!expiresAt) return;
                    const target = new Date(expiresAt).getTime();
                    const diffSec = Math.max(0, Math.floor((target - now) / 1000));
                    const textEl = t.querySelector('.chat-cq-timer-text');
                    if (diffSec <= 0 || status === 'expired') {
                        if (textEl) textEl.textContent = 'Expired';
                        t.classList.add('expired');
                    } else {
                        if (textEl) textEl.textContent = _formatRemainingSeconds(diffSec);
                    }
                });
            }, 1000);
        }
        _startQuoteCountdownTicker();

        function openCustomQuoteModal() {
            if (!_activeConvoId) return;
            const modal = document.getElementById('chat-cq-create-modal');
            if (modal) {
                document.getElementById('chat-cq-title').value = '';
                document.getElementById('chat-cq-category').value = 'bouquets';
                document.getElementById('chat-cq-price').value = '';
                document.getElementById('chat-cq-inclusions').value = '';
                document.getElementById('chat-cq-image').value = '';
                const allowDedicationCheckbox = document.getElementById('chat-cq-allow-dedication');
                if (allowDedicationCheckbox) allowDedicationCheckbox.checked = true;
                modal.classList.add('open');
            }
        }

        function closeCustomQuoteModal() {
            const modal = document.getElementById('chat-cq-create-modal');
            if (modal) modal.classList.remove('open');
        }

        async function submitCustomQuote(e) {
            if (e && e.preventDefault) e.preventDefault();
            if (!_activeConvoId) return;

            const title = document.getElementById('chat-cq-title').value.trim();
            const category = document.getElementById('chat-cq-category').value;
            const price = document.getElementById('chat-cq-price').value;
            const inclusions = document.getElementById('chat-cq-inclusions').value.trim();
            const imageFile = document.getElementById('chat-cq-image').files[0];
            const allowDedicationCheckbox = document.getElementById('chat-cq-allow-dedication');
            const allowDedication = allowDedicationCheckbox ? allowDedicationCheckbox.checked : true;

            if (!title || !price || Number(price) <= 0) {
                alert('Please enter a valid title and base price.');
                return;
            }

            const btn = document.getElementById('chat-cq-submit-btn');
            const prevText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Sending Quote...';

            try {
                const fd = new FormData();
                fd.append('title', title);
                fd.append('category', category);
                fd.append('base_price', price);
                fd.append('allow_dedication_card', allowDedication ? 'true' : 'false');
                if (inclusions) fd.append('inclusions', inclusions);
                if (imageFile) fd.append('image', imageFile);

                const res = await _fetch(API + '/conversations/' + _activeConvoId + '/custom-ticket', {
                    method: 'POST',
                    body: fd,
                    headers: _token ? { 'Authorization': 'Bearer ' + _token } : {}
                });
                const data = await res.json();
                if (res.ok && data.status === 'ok') {
                    closeCustomQuoteModal();
                    if (data.message) {
                        _messages.push(data.message);
                        _lastMessagesFingerprint = '';
                        _renderMessages({ scroll: true });
                    }
                } else {
                    alert(data.error || 'Failed to create quote ticket.');
                }
            } catch (err) {
                console.error('Custom quote creation error:', err);
                alert('Error creating quote: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = prevText;
            }
        }

        let _customerAddresses = [];
        let _storeScheduleData = null;

        async function openTicketCheckout(ticketId) {
            try {
                const res = await _fetch(API + '/custom-ticket/' + ticketId);
                const data = await res.json();
                if (!res.ok || !data.ticket) {
                    alert(data.error || 'Could not load ticket details.');
                    return;
                }
                _activeCheckoutTicket = data.ticket;
                _selectedCheckoutAddons = {};

                // Render summary card
                const sumEl = document.getElementById('chat-cq-checkout-summary');
                if (sumEl) {
                    sumEl.innerHTML = `
                    <div style="font-size:11px;font-weight:700;color:var(--deep-rose);text-transform:uppercase;">${_esc(_activeCheckoutTicket.category)}</div>
                    <div style="font-size:15px;font-weight:800;color:var(--charcoal);margin:2px 0;">${_esc(_activeCheckoutTicket.title)}</div>
                    ${_activeCheckoutTicket.inclusions ? `<div style="font-size:12px;color:var(--muted);margin-top:3px;">Inclusions: ${_esc(_activeCheckoutTicket.inclusions)}</div>` : ''}
                    <div style="font-size:14px;font-weight:700;color:var(--deep-rose);margin-top:6px;">Base Quote: ${_formatPeso(_activeCheckoutTicket.base_price)}</div>
                `;
                }

                // Dedication card section conditional visibility based on allow_dedication_card
                const dedicationGroup = document.getElementById('chat-cq-dedication-group');
                if (dedicationGroup) {
                    const isAllowed = _activeCheckoutTicket.allow_dedication_card !== false;
                    dedicationGroup.style.display = isAllowed ? 'block' : 'none';
                }

                // Load store active add-ons
                const addonsEl = document.getElementById('chat-cq-addons-list');
                if (addonsEl) addonsEl.innerHTML = '<div style="font-size:12px;color:var(--muted);text-align:center;padding:10px;">Loading add-ons...</div>';

                const aRes = await _fetch(API + '/stores/' + _activeCheckoutTicket.store_id + '/addons');
                const aData = await aRes.json();
                _availableStoreAddons = (aData && aData.addons) ? aData.addons : [];
                _renderCheckoutAddons();
                _recalcCheckoutTotals();

                // Load customer saved addresses
                await _loadCustomerAddresses();

                // Load store schedule & set min date for delivery date picker
                await _setupDeliveryScheduleDatePicker();

                // Configure payment methods based on store permissions
                _setupPaymentMethodOptions();

                // Reset inputs
                document.getElementById('chat-cq-dedication').value = '';
                document.getElementById('chat-cq-gcash-receipt').value = '';

                const modal = document.getElementById('chat-cq-checkout-modal');
                if (modal) modal.classList.add('open');
            } catch (err) {
                console.error('Error opening checkout modal:', err);
                alert('Failed to load checkout.');
            }
        }

        async function _loadCustomerAddresses() {
            const sel = document.getElementById('chat-cq-delivery-address-select');
            if (!sel) return;
            sel.innerHTML = '<option value="">Loading saved addresses...</option>';

            try {
                const res = await _fetch('/api/account/addresses', {
                    headers: _token ? { 'Authorization': 'Bearer ' + _token } : {}
                });
                const data = await res.json();
                _customerAddresses = (data && data.addresses) ? data.addresses : [];

                if (!_customerAddresses.length) {
                    sel.innerHTML = '<option value="">No saved addresses found. Please add one in Account.</option>';
                    return;
                }

                sel.innerHTML = _customerAddresses.map((addr, idx) => {
                    const label = addr.address_label || 'Address';
                    const full = addr.address_line || `${addr.street || ''}, ${addr.barangay || ''}, ${addr.municipality || ''}`;
                    const isSelected = addr.is_default || idx === 0;
                    return `<option value="${addr.id}" ${isSelected ? 'selected' : ''}>${_esc(label)} · ${_esc(full)}</option>`;
                }).join('');

                // Automatically check delivery coverage for default/first address
                const activeId = sel.value;
                if (activeId) {
                    await onCheckoutAddressChange(activeId);
                }
            } catch (err) {
                console.error('Failed to load addresses:', err);
                sel.innerHTML = '<option value="">Failed to load addresses</option>';
            }
        }

        let _addressCanDeliver = true;
        let _addressBlockReason = null;

        async function onCheckoutAddressChange(addrId) {
            const warnEl = document.getElementById('chat-cq-address-coverage-warning');
            const submitBtn = document.getElementById('chat-cq-checkout-submit-btn');
            if (!addrId || !_activeCheckoutTicket) {
                _addressCanDeliver = false;
                _addressBlockReason = 'Please select a delivery address.';
                if (warnEl) {
                    warnEl.textContent = _addressBlockReason;
                    warnEl.style.display = 'block';
                }
                if (submitBtn) submitBtn.disabled = true;
                return;
            }

            if (warnEl) {
                warnEl.style.display = 'block';
                warnEl.style.background = '#fef3c7';
                warnEl.style.color = '#92400e';
                warnEl.style.borderColor = '#fcd34d';
                warnEl.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Checking store delivery coverage…';
            }

            try {
                const basePrice = Number(_activeCheckoutTicket.base_price || 0);
                const res = await _fetch(API + '/stores/' + _activeCheckoutTicket.store_id + '/check-delivery?address_id=' + addrId + '&subtotal=' + basePrice);
                const data = await res.json();

                _addressCanDeliver = (data && data.can_deliver === true);
                _addressBlockReason = data ? data.reason : null;

                if (_addressCanDeliver) {
                    if (warnEl) warnEl.style.display = 'none';
                    if (submitBtn) submitBtn.disabled = false;
                    if (data.delivery_fee != null) {
                        const feeEl = document.getElementById('chat-cq-calc-fee');
                        if (feeEl) feeEl.textContent = _formatPeso(data.delivery_fee);
                        _recalcCheckoutTotals(Number(data.delivery_fee));
                    }
                } else {
                    if (warnEl) {
                        warnEl.style.display = 'block';
                        warnEl.style.background = '#fee2e2';
                        warnEl.style.color = '#991b1b';
                        warnEl.style.borderColor = '#fca5a5';
                        warnEl.innerHTML = `<i class="ri-error-warning-line"></i> ${_esc(_addressBlockReason || 'The store cannot deliver to this address.')}`;
                    }
                    if (submitBtn) submitBtn.disabled = true;
                }
            } catch (e) {
                console.warn('Failed to check address coverage:', e);
                if (warnEl) warnEl.style.display = 'none';
                if (submitBtn) submitBtn.disabled = false;
            }
        }

        async function _setupDeliveryScheduleDatePicker() {
            const dateInput = document.getElementById('chat-cq-delivery-date');
            const timeSelect = document.getElementById('chat-cq-delivery-time');
            if (!dateInput || !_activeCheckoutTicket) return;

            // Fetch store schedule open days
            let openDays = [];
            let hasSchedule = false;
            try {
                const todayPh = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Manila' }));
                const todayIso = todayPh.toISOString().split('T')[0];
                const res = await _fetch('/api/store/' + _activeCheckoutTicket.store_id + '/time-slots?date=' + todayIso);
                const data = await res.json();
                if (data && data.success && Array.isArray(data.open_days) && data.open_days.length) {
                    openDays = data.open_days.map(d => String(d).toLowerCase());
                    hasSchedule = true;
                } else if (data && data.open_days && Array.isArray(data.open_days)) {
                    openDays = data.open_days.map(d => String(d).toLowerCase());
                    hasSchedule = openDays.length > 0;
                }
            } catch (e) {
                console.warn('Could not inspect store open days:', e);
            }

            const now = new Date();
            const phToday = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Manila' }));
            const yyyy = phToday.getFullYear();
            const mm = String(phToday.getMonth() + 1).padStart(2, '0');
            const dd = String(phToday.getDate()).padStart(2, '0');
            const todayStr = `${yyyy}-${mm}-${dd}`;

            const maxDate = new Date(phToday);
            maxDate.setDate(maxDate.getDate() + 14);

            const weekdayNames = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
            function isDayOpen(d) {
                if (!hasSchedule || !openDays.length) return true;
                const wName = weekdayNames[d.getDay()];
                return openDays.includes(wName);
            }

            // Find first open date starting from today
            let firstOpenDate = new Date(phToday);
            if (hasSchedule && openDays.length) {
                for (let i = 0; i <= 14; i++) {
                    const checkD = new Date(phToday);
                    checkD.setDate(checkD.getDate() + i);
                    if (isDayOpen(checkD)) {
                        firstOpenDate = checkD;
                        break;
                    }
                }
            }

            const firstOpenStr = `${firstOpenDate.getFullYear()}-${String(firstOpenDate.getMonth() + 1).padStart(2, '0')}-${String(firstOpenDate.getDate()).padStart(2, '0')}`;

            // Ensure flatpickr is available (either global or via ensureFlatpickr)
            if (typeof ensureFlatpickr === 'function') {
                try { await ensureFlatpickr(); } catch (e) { }
            }

            if (dateInput._flatpickr) {
                dateInput._flatpickr.destroy();
            }

            if (typeof flatpickr === 'function') {
                dateInput.removeAttribute('min');
                dateInput.removeAttribute('max');
                flatpickr(dateInput, {
                    dateFormat: 'Y-m-d',
                    defaultDate: firstOpenStr,
                    minDate: todayStr,
                    maxDate: maxDate,
                    disableMobile: true, // Use flatpickr UI on mobile for consistent styling and disabled-day locking
                    enable: [
                        function (date) {
                            return isDayOpen(date);
                        }
                    ],
                    onDayCreate: function (dObj, dStr, fp, dayElem) {
                        if (dayElem.classList.contains('flatpickr-disabled') || dayElem.classList.contains('notAllowed')) {
                            dayElem.classList.add('checkout-day-closed');
                            dayElem.title = 'Store closed on this day';
                        }
                    },
                    onChange: function (selectedDates, dateStr) {
                        if (dateStr) onCheckoutDateChange(dateStr);
                    }
                });
                dateInput.value = firstOpenStr;
            } else {
                // Native fallback with locking validation on change
                dateInput.min = todayStr;
                dateInput.max = `${maxDate.getFullYear()}-${String(maxDate.getMonth() + 1).padStart(2, '0')}-${String(maxDate.getDate()).padStart(2, '0')}`;
                dateInput.value = firstOpenStr;
                dateInput.onchange = function (e) {
                    const val = e.target.value;
                    if (!val) return;
                    const pickedDate = new Date(val + 'T00:00:00');
                    if (!isDayOpen(pickedDate)) {
                        alert('The store is closed on this day. Please select an available open day.');
                        e.target.value = firstOpenStr;
                        onCheckoutDateChange(firstOpenStr);
                        return;
                    }
                    onCheckoutDateChange(val);
                };
            }

            // Fetch time slots for the resolved first open date
            await onCheckoutDateChange(firstOpenStr);
        }

        async function onCheckoutDateChange(dateStr) {
            const timeSelect = document.getElementById('chat-cq-delivery-time');
            if (!timeSelect) return;

            if (!dateStr || !_activeCheckoutTicket) {
                timeSelect.innerHTML = '<option value="">Select date first</option>';
                return;
            }

            timeSelect.innerHTML = '<option value="">Loading slots...</option>';

            try {
                const res = await _fetch('/api/store/' + _activeCheckoutTicket.store_id + '/time-slots?date=' + dateStr);
                const data = await res.json();
                _storeScheduleData = data;

                const rawSlots = data.time_slots || data.slots || [];
                if (data.is_open === false || !rawSlots.length) {
                    const reason = data.block_reason === 'closed' ? 'Store is closed on this day' :
                        (data.block_reason === 'order_cutoff' || data.block_reason === 'cutoff_passed') ? 'Order cutoff has passed for this day' :
                            data.block_reason === 'slots_passed' ? 'All delivery slots for today have passed' :
                                data.block_reason === 'lead_time' ? 'Remaining slots are inside prep window' :
                                    data.block_reason === 'no_schedule' ? 'Delivery hours not set' : 'No available slots';
                    timeSelect.innerHTML = `<option value="">${reason}</option>`;
                    return;
                }

                timeSelect.innerHTML = rawSlots.map((slot, idx) => {
                    const val = typeof slot === 'object' && slot !== null ? (slot.value || slot.label || '') : slot;
                    const lbl = typeof slot === 'object' && slot !== null ? (slot.label || slot.value || '') : slot;
                    return `<option value="${_esc(val)}" ${idx === 0 ? 'selected' : ''}>${_esc(lbl)}</option>`;
                }).join('');
            } catch (err) {
                console.error('Failed to fetch time slots:', err);
                timeSelect.innerHTML = '<option value="">Failed to load time slots</option>';
            }
        }

        function _setupPaymentMethodOptions() {
            const ticket = _activeCheckoutTicket;
            const codRadio = document.getElementById('chat-cq-pay-cod');
            const gcashRadio = document.getElementById('chat-cq-pay-gcash');
            const codLabel = document.getElementById('chat-cq-pay-cod-label');
            const gcashLabel = document.getElementById('chat-cq-pay-gcash-label');
            const noticeEl = document.getElementById('chat-cq-pay-notice');

            const codAllowed = ticket ? ticket.store_allows_cod !== false : true;
            const gcashAllowed = ticket ? ticket.store_allows_gcash !== false : true;

            if (codRadio && codLabel) {
                codRadio.disabled = !codAllowed;
                codLabel.style.opacity = codAllowed ? '1' : '0.45';
                codLabel.style.cursor = codAllowed ? 'pointer' : 'not-allowed';
                codLabel.title = codAllowed ? '' : 'Cash on delivery disabled by store';
            }

            if (gcashRadio && gcashLabel) {
                gcashRadio.disabled = !gcashAllowed;
                gcashLabel.style.opacity = gcashAllowed ? '1' : '0.45';
                gcashLabel.style.cursor = gcashAllowed ? 'pointer' : 'not-allowed';
                gcashLabel.title = gcashAllowed ? '' : 'GCash payment disabled by store';
            }

            // Set initial checked option
            if (codAllowed) {
                codRadio.checked = true;
                onPaymentMethodChange('cod');
            } else if (gcashAllowed) {
                gcashRadio.checked = true;
                onPaymentMethodChange('gcash');
            } else {
                onPaymentMethodChange('cod');
            }

            if (noticeEl) {
                if (!codAllowed && !gcashAllowed) {
                    noticeEl.textContent = 'This store currently has no payment methods configured.';
                    noticeEl.style.display = 'block';
                } else if (!gcashAllowed) {
                    noticeEl.textContent = 'GCash is disabled by this store. Only Cash on Delivery is available.';
                    noticeEl.style.display = 'block';
                } else if (!codAllowed) {
                    noticeEl.textContent = 'Cash on delivery is disabled by this store. Only GCash is available.';
                    noticeEl.style.display = 'block';
                } else {
                    noticeEl.style.display = 'none';
                }
            }
        }

        function _renderCheckoutAddons() {
            const el = document.getElementById('chat-cq-addons-list');
            if (!el) return;
            if (!_availableStoreAddons.length) {
                el.innerHTML = '<div style="font-size:12px;color:var(--muted);text-align:center;padding:10px;">No add-ons available for this store.</div>';
                return;
            }

            el.innerHTML = _availableStoreAddons.map(a => {
                const currentQty = _selectedCheckoutAddons[a.id] || 0;
                return `
                <div class="chat-cq-addon-row">
                    <div class="chat-cq-addon-info">
                        <div class="chat-cq-addon-name">${_esc(a.name)}</div>
                        <div class="chat-cq-addon-price">+ ${_formatPeso(a.price)}</div>
                    </div>
                    <div class="chat-cq-addon-ctrl">
                        ${currentQty > 0 ? `
                            <button type="button" class="chat-cq-qty-btn" onclick="chatWidget.updateAddonQty(${a.id}, -1)">-</button>
                            <span style="font-size:13px;font-weight:700;min-width:18px;text-align:center;">${currentQty}</span>
                            <button type="button" class="chat-cq-qty-btn" onclick="chatWidget.updateAddonQty(${a.id}, 1)" ${currentQty >= a.stock_quantity ? 'disabled' : ''}>+</button>
                        ` : `
                            <button type="button" class="chat-cq-btn" style="padding:4px 10px;font-size:11.5px;width:auto;box-shadow:none;" onclick="chatWidget.updateAddonQty(${a.id}, 1)">+ Add</button>
                        `}
                    </div>
                </div>
            `;
            }).join('');
        }

        function updateAddonQty(optId, delta) {
            const item = _availableStoreAddons.find(a => a.id === optId);
            if (!item) return;
            const current = _selectedCheckoutAddons[optId] || 0;
            const next = Math.max(0, Math.min(item.stock_quantity, current + delta));
            if (next === 0) {
                delete _selectedCheckoutAddons[optId];
            } else {
                _selectedCheckoutAddons[optId] = next;
            }
            _renderCheckoutAddons();
            _recalcCheckoutTotals();
        }

        function _recalcCheckoutTotals() {
            if (!_activeCheckoutTicket) return;
            const base = Number(_activeCheckoutTicket.base_price || 0);
            let addonsTotal = 0;
            Object.keys(_selectedCheckoutAddons).forEach(id => {
                const qty = _selectedCheckoutAddons[id];
                const opt = _availableStoreAddons.find(a => String(a.id) === String(id));
                if (opt) addonsTotal += Number(opt.price || 0) * qty;
            });
            const fee = 100.00;
            const total = base + addonsTotal + fee;

            document.getElementById('chat-cq-calc-base').textContent = _formatPeso(base);
            document.getElementById('chat-cq-calc-addons').textContent = _formatPeso(addonsTotal);
            document.getElementById('chat-cq-calc-fee').textContent = _formatPeso(fee);
            document.getElementById('chat-cq-calc-total').textContent = _formatPeso(total);
        }

        function onPaymentMethodChange(method) {
            const gcashSec = document.getElementById('chat-cq-gcash-section');
            if (gcashSec) {
                gcashSec.style.display = (method === 'gcash') ? 'flex' : 'none';
            }
        }

        function closeCheckoutModal() {
            const modal = document.getElementById('chat-cq-checkout-modal');
            if (modal) modal.classList.remove('open');
            _activeCheckoutTicket = null;
            _selectedCheckoutAddons = {};
        }

        async function submitCheckoutTicket(e) {
            if (e && e.preventDefault) e.preventDefault();
            if (!_activeCheckoutTicket) return;

            const addrSelect = document.getElementById('chat-cq-delivery-address-select');
            const addrId = addrSelect ? addrSelect.value : null;
            if (!addrId) {
                alert('Please select a delivery address or add one under Account > Addresses.');
                return;
            }

            if (!_addressCanDeliver) {
                alert(_addressBlockReason || 'The store cannot deliver to the selected address. Please select another address.');
                return;
            }

            const chosenAddress = _customerAddresses.find(a => String(a.id) === String(addrId));
            const addrText = chosenAddress ? (chosenAddress.address_line || `${chosenAddress.street || ''}, ${chosenAddress.barangay || ''}, ${chosenAddress.municipality || ''}`) : '';

            const dateVal = document.getElementById('chat-cq-delivery-date').value;
            const timeVal = document.getElementById('chat-cq-delivery-time').value;
            if (!dateVal) {
                alert('Please select a delivery date.');
                return;
            }
            if (!timeVal) {
                alert('Please select a valid delivery time slot.');
                return;
            }

            const dedication = document.getElementById('chat-cq-dedication').value.trim();

            const payRadio = document.querySelector('input[name="chat-cq-pay"]:checked');
            const payMethod = payRadio ? payRadio.value : 'cod';

            if (payMethod === 'gcash' && _activeCheckoutTicket.store_allows_gcash === false) {
                alert('GCash payment is disabled by this store.');
                return;
            }
            if (payMethod === 'cod' && _activeCheckoutTicket.store_allows_cod === false) {
                alert('Cash on delivery is disabled by this store.');
                return;
            }

            const receiptFile = document.getElementById('chat-cq-gcash-receipt').files[0];
            if (payMethod === 'gcash' && !receiptFile) {
                alert('Please upload your GCash payment receipt screenshot.');
                return;
            }

            const btn = document.getElementById('chat-cq-checkout-submit-btn');
            const prevText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Processing Order...';

            try {
                const fd = new FormData();
                fd.append('delivery_address_id', addrId);
                fd.append('delivery_address', addrText);
                if (chosenAddress && chosenAddress.latitude) fd.append('customer_latitude', chosenAddress.latitude);
                if (chosenAddress && chosenAddress.longitude) fd.append('customer_longitude', chosenAddress.longitude);
                fd.append('payment_method', payMethod);
                if (dateVal) fd.append('requested_delivery_date', dateVal);
                if (timeVal) fd.append('requested_delivery_time', timeVal);
                if (dedication) fd.append('dedication_card', dedication);

                // Add-ons list
                const addonsArray = Object.keys(_selectedCheckoutAddons).map(optId => ({
                    addon_option_id: Number(optId),
                    quantity: _selectedCheckoutAddons[optId]
                }));
                fd.append('addons', JSON.stringify(addonsArray));

                if (receiptFile) {
                    fd.append('receipt', receiptFile);
                }

                const res = await _fetch(API + '/custom-ticket/' + _activeCheckoutTicket.id + '/checkout', {
                    method: 'POST',
                    body: fd,
                    headers: _token ? { 'Authorization': 'Bearer ' + _token } : {}
                });
                const data = await res.json();
                if (res.ok && data.status === 'ok') {
                    closeCheckoutModal();
                    await window.openConfirmModal('Success! Custom order has been placed. Redirecting to My Orders...', { title: 'Order Placed', confirmText: 'OK' });
                    await _loadMessages({ forceScroll: true });
                    // Navigate to My Orders page
                    window.location.href = '/my-account?page=orders';
                } else {
                    await window.openConfirmModal(data.error || 'Checkout failed. Please try again.', { title: 'Checkout Failed', confirmText: 'OK' });
                }
            } catch (err) {
                console.error('Ticket checkout failed:', err);
                await window.openConfirmModal('Error during checkout: ' + err.message, { title: 'Error', confirmText: 'OK' });
            } finally {
                btn.disabled = false;
                btn.innerHTML = prevText;
            }
        }

        // ═══ LIGHTBOX ═══
        function openLightbox(url) {
            document.getElementById('chat-lightbox-img').src = url;
            document.getElementById('chat-lightbox').classList.add('open');
        }
        function closeLightbox() {
            document.getElementById('chat-lightbox').classList.remove('open');
            document.getElementById('chat-lightbox-img').src = '';
        }

        // ═══ PUBLIC API ═══
        return {
            init,
            toggle,
            open,
            close,
            showInbox,
            openConvo,
            openWithStore,
            openWithRiderOrder,
            openSupport,
            openQuickAnswers,
            showFaqAnswer,
            _openSupportFromInbox,
            shareOrderCard,
            dismissOrderSuggest,
            searchStores,
            send,
            sendImage,
            previewImage,
            cancelImage,
            confirmSendImage,
            removeImage,
            openLightbox,
            closeLightbox,
            onType,
            setReply,
            cancelReply,
            copyMessage,
            deleteMessage,
            _toggleMenu,
            toggleConvoMenu,
            viewStore,
            deleteCurrentConversation,
            confirmDeleteConversation,
            openCustomQuoteModal,
            closeCustomQuoteModal,
            submitCustomQuote,
            openTicketCheckout,
            closeCheckoutModal,
            updateAddonQty,
            onPaymentMethodChange,
            onCheckoutDateChange,
            onCheckoutAddressChange,
            submitCheckoutTicket,
        };
    })();
    window.chatWidget = chatWidget;

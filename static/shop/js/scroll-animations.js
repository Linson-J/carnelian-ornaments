(function () {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const revealSelectors = [
        '.hero-carousel',
        '.home-section',
        '.section-heading',
        '.category-card',
        '.product-card',
        '.story-section',
        '.story-card',
        '.catalog-hero',
        '.catalog-card',
        '.product-detail',
        '.cart-shell',
        '.checkout-shell',
        '.profile-shell',
        '.wishlist-shell',
        '.global-footer__brand',
        '.global-footer__nav',
        '.global-footer__contact',
        '.global-footer__newsletter'
    ];
    const mediaSelectors = [
        '.product-image',
        '.catalog-product-image',
        '.product-detail-media',
        '.promo-banner-img'
    ];

    document.documentElement.classList.add('js-scroll-ready');

    if (reduceMotion) {
        document.documentElement.classList.add('scroll-motion-reduced');
        return;
    }

    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                revealObserver.unobserve(entry.target);
            }
        });
    }, {
        root: null,
        threshold: 0.16,
        rootMargin: '0px 0px -8% 0px'
    });

    const parallaxItems = new Set();

    function prepareRevealElement(element, index) {
        if (element.dataset.scrollReady === 'true') return;
        element.dataset.scrollReady = 'true';
        element.classList.add('scroll-reveal');
        element.style.setProperty('--scroll-delay', `${Math.min(index % 8, 7) * 70}ms`);
        revealObserver.observe(element);
    }

    function prepareMediaElement(element) {
        if (element.dataset.scrollMediaReady === 'true') return;
        element.dataset.scrollMediaReady = 'true';
        element.classList.add('scroll-media-reveal');
        parallaxItems.add(element);
    }

    function scan(root = document) {
        revealSelectors.forEach((selector) => {
            root.querySelectorAll(selector).forEach(prepareRevealElement);
        });
        mediaSelectors.forEach((selector) => {
            root.querySelectorAll(selector).forEach(prepareMediaElement);
        });
    }

    function updateParallax() {
        const viewportHeight = window.innerHeight || 1;
        parallaxItems.forEach((element) => {
            const rect = element.getBoundingClientRect();
            if (rect.bottom < 0 || rect.top > viewportHeight) return;
            const progress = (rect.top + rect.height / 2 - viewportHeight / 2) / viewportHeight;
            const translate = Math.max(-18, Math.min(18, progress * -24));
            const rotate = Math.max(-1.4, Math.min(1.4, progress * -1.8));
            element.style.setProperty('--scroll-parallax-y', `${translate}px`);
            element.style.setProperty('--scroll-parallax-rotate', `${rotate}deg`);
        });
    }

    let ticking = false;
    function requestParallaxUpdate() {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(() => {
            ticking = false;
            updateParallax();
        });
    }

    scan();
    updateParallax();

    const mutationObserver = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    scan(node);
                }
            });
        });
        requestParallaxUpdate();
    });

    mutationObserver.observe(document.body, {
        childList: true,
        subtree: true
    });

    window.addEventListener('scroll', requestParallaxUpdate, { passive: true });
    window.addEventListener('resize', requestParallaxUpdate);
    window.addEventListener('pageshow', () => {
        scan();
        requestParallaxUpdate();
    });
})();

(function () {
  // Sticky nav shadow
  var nav = document.querySelector('[data-nav]');
  if (nav) {
    var onScroll = function () { nav.classList.toggle('is-scrolled', window.scrollY > 20); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // Mobile menu
  var toggle = document.querySelector('[data-nav-toggle]');
  var links = document.getElementById('nav-links');
  if (toggle && links) {
    var setMenu = function (open) {
      links.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', String(open));
    };
    toggle.addEventListener('click', function () { setMenu(!links.classList.contains('is-open')); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && links.classList.contains('is-open')) {
        setMenu(false);
        toggle.focus();
      }
    });
    links.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false); });
  }

  // Reveal on scroll, with a one-by-one delay for the children of .stagger
  var revealItems = document.querySelectorAll('.reveal, .stagger > *');
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var showItem = function (el) {
    el.classList.add('is-in');
    // Clear the delay afterwards so it doesn't slow down the card hover effect.
    if (el.style.transitionDelay) {
      window.setTimeout(function () { el.style.transitionDelay = ''; }, 1300);
    }
  };
  if (reducedMotion || !('IntersectionObserver' in window)) {
    revealItems.forEach(function (el) { el.classList.add('is-in'); });
  } else {
    document.querySelectorAll('.stagger').forEach(function (group) {
      Array.prototype.forEach.call(group.children, function (child, index) {
        child.style.transitionDelay = Math.min(index % 4, 3) * 90 + 'ms';
      });
    });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          showItem(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
    revealItems.forEach(function (el) { observer.observe(el); });
  }

  // Quote modal. <dialog> traps focus, closes on Esc and returns focus when closed.
  var modal = document.querySelector('[data-quote-modal]');
  if (modal && typeof modal.showModal === 'function') {
    var motorInput = modal.querySelector('[data-motor-input]');
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest('[data-quote]');
      if (!trigger) return;
      e.preventDefault();
      motorInput.value = trigger.getAttribute('data-motor') || '';
      modal.showModal();
    });
    modal.querySelector('[data-modal-close]').addEventListener('click', function () { modal.close(); });
    // A click directly on the dialog element (not its contents) is a click on the backdrop.
    modal.addEventListener('click', function (e) { if (e.target === modal) modal.close(); });
  }

  // Detail page gallery
  var main = document.querySelector('[data-gallery-main]');
  var thumbs = document.querySelectorAll('[data-gallery-thumb]');
  thumbs.forEach(function (thumb) {
    thumb.addEventListener('click', function () {
      if (main) main.src = thumb.getAttribute('data-gallery-thumb');
      thumbs.forEach(function (t) { t.removeAttribute('aria-current'); });
      thumb.setAttribute('aria-current', 'true');
    });
  });
})();

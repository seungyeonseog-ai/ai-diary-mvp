function navigateToTab(tabName) {
  document.querySelector(`.main-tab[data-tab="${tabName}"]`)?.click();
}
window.initSpaceSection = function() {
  const tabs = {'대화하기':'chatting', '서재':'study', '텃밭':'garden', '리포트':'constellation'};
  document.querySelectorAll('.space-card').forEach(card => {
    if (card.dataset.spaceBound) return;
    card.dataset.spaceBound = 'true';
    card.addEventListener('click', () => {
      const name = card.querySelector('.space-card-title')?.textContent.trim();
      if (tabs[name]) navigateToTab(tabs[name]);
    });
  });
};
window.initSpaceSection();

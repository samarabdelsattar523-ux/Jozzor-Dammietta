/** @odoo-module **/
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('jozoor_filter_input');
    const items = document.querySelectorAll('.product-item');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            items.forEach((item) => {
                const name = (item.dataset.name || '').toLowerCase();
                const maker = (item.dataset.maker || '').toLowerCase();
                if (name.includes(query) || maker.includes(query)) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }
});

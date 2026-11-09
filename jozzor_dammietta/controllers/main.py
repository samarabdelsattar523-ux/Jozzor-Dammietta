from odoo import http
from odoo.http import request

CATEGORIES = ["All furniture", "Living room", "Dining", "Bedroom", "Office"]

PRODUCTS = [
    {
        "name": "Marsa Lounge Chair",
        "maker": "El Nasr Workshop",
        "category": "Living room",
        "price": "EGP 18,500",
        "image": "https://images.unsplash.com/photo-1567538096630-e0c55bd6374c?auto=format&fit=crop&w=900&q=85",
        "color": "#e8dfd3",
    },
    {
        "name": "Nile Oak Dining Set",
        "maker": "Hassan Woodcraft",
        "category": "Dining",
        "price": "EGP 42,000",
        "image": "https://images.unsplash.com/photo-1618220179428-22790b461013?auto=format&fit=crop&w=900&q=85",
        "color": "#dce2dc",
    },
    {
        "name": "Sahara Side Table",
        "maker": "Maison Fouad",
        "category": "Living room",
        "price": "EGP 6,800",
        "image": "https://images.unsplash.com/photo-1532372320572-cda25653a26d?auto=format&fit=crop&w=900&q=85",
        "color": "#e7e0d6",
    },
    {
        "name": "Cairo Cane Bed",
        "maker": "Dar El Tefl",
        "category": "Bedroom",
        "price": "EGP 31,500",
        "image": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=85",
        "color": "#e2ded7",
    },
]

MAKERS = [
    {
        "name": "El Nasr Workshop",
        "location": "Damietta, Egypt",
        "image": "https://images.unsplash.com/photo-1565793298595-6a879b1d9492?auto=format&fit=crop&w=160&q=80",
    },
    {
        "name": "Hassan Woodcraft",
        "location": "New Damietta, Egypt",
        "image": "https://images.unsplash.com/photo-1556761175-b413da4baf72?auto=format&fit=crop&w=160&q=80",
    },
    {
        "name": "Maison Fouad",
        "location": "Damietta, Egypt",
        "image": "https://images.unsplash.com/photo-1549497538-303791108f95?auto=format&fit=crop&w=160&q=80",
    },
]


class SandoqController(http.Controller):

    @http.route(["/sandoq"], type="http", auth="public", website=True, sitemap=True)
    def sandoq_home(self, **kwargs):
        return request.render("jozzor_dammietta.sandoq_home", {
            "categories": CATEGORIES,
            "products": PRODUCTS,
            "makers": MAKERS,
        })

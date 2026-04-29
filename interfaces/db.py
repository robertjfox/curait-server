"""Process-wide singleton instances of the database interfaces.

Every interface holds a reference to the shared Supabase client; one
instance per interface is enough for the whole process. Constructing
multiple instances (as we did when several modules called
``OutfitsInterface()`` at import time) doesn't allocate new connections,
but it does multiply downstream service objects (httpx clients, OpenAI
clients, etc.) and makes shutdown bookkeeping fragile.
"""
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface
from interfaces.threads_interface import ThreadsInterface
from interfaces.users_interface import UsersInterface
from interfaces.saved_products_interface import SavedProductsInterface


outfits: OutfitsInterface = OutfitsInterface()
outfit_items: OutfitItemsInterface = OutfitItemsInterface()
threads: ThreadsInterface = ThreadsInterface()
users: UsersInterface = UsersInterface()
saved_products: SavedProductsInterface = SavedProductsInterface()

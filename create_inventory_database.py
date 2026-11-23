# create_inventory_database.py
# In this file, I am building a fictional retail inventory database called inventory.db.
# It holds monthly sales, revenue, and stock levels for five stores in BC, Canada,
# for every month from January to December 2025.
# I designed it so I can run it as many times as I like, and each run starts fresh
# and produces exactly the same data.

import sqlite3
import random

DB_FILE = "inventory.db"

# I am fixing the random seed so my "random" variation comes out identical every run.
# This keeps my answer key valid no matter how many times I rebuild the database.
random.seed(2025)

connection = sqlite3.connect(DB_FILE)
cursor = connection.cursor()

# I am dropping my tables first if they already exist, so every run starts clean
cursor.execute("DROP TABLE IF EXISTS monthly_inventory")
cursor.execute("DROP TABLE IF EXISTS products")
cursor.execute("DROP TABLE IF EXISTS locations")

# Step 1: Creating the three tables

# I am creating a table to hold my five stores
cursor.execute("""
    CREATE TABLE locations (
        location_id INTEGER PRIMARY KEY,
        store_name  TEXT NOT NULL,
        province    TEXT NOT NULL
    )
""")

# I am creating a table to hold my six products and their prices (in Canadian dollars)
cursor.execute("""
    CREATE TABLE products (
        product_id   INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL,
        category     TEXT NOT NULL,
        unit_price   REAL NOT NULL
    )
""")

# I am creating the main table, which records sales, revenue, and stock
# for every store, product, and month
cursor.execute("""
    CREATE TABLE monthly_inventory (
        location_id   INTEGER NOT NULL,
        product_id    INTEGER NOT NULL,
        month         TEXT NOT NULL,      -- I am storing months as YYYY-MM
        units_sold    INTEGER NOT NULL,   -- how many units I sold during the month
        revenue       REAL NOT NULL,      -- units_sold x unit_price, in CAD
        units_on_hand INTEGER NOT NULL,   -- how many units I had left at the end of the month
        FOREIGN KEY (location_id) REFERENCES locations(location_id),
        FOREIGN KEY (product_id)  REFERENCES products(product_id)
    )
""")

# Step 2: Adding my stores and products

# I invented five stores across the Lower Mainland in BC.
# I gave each store a "size" so they don't all sell the same amount.
# A size of 1.30 means that store sells 30% more than an average store.
stores = [
    # (location_id, store_name, province, size)
    (1, "Vancouver", "BC", 1.30),
    (2, "Surrey",    "BC", 1.15),
    (3, "Burnaby",   "BC", 1.00),
    (4, "Coquitlam", "BC", 0.85),
    (5, "Langley",   "BC", 0.70),
]
cursor.executemany("INSERT INTO locations VALUES (?, ?, ?)",
                   [(s[0], s[1], s[2]) for s in stores])

# I chose six everyday products. Each has a typical number of units
# an average store sells in an average month.
products = [
    # (product_id, product_name, category, unit_price, typical_monthly_units)
    (1, "Bottled Water 12-pack", "Beverages",     5.99, 110),
    (2, "Paper Towels",          "Household",     8.49,  75),
    (3, "Laundry Detergent",     "Household",    12.99,  50),
    (4, "Granola Bars",          "Snacks",        4.49, 125),
    (5, "Coffee Beans 1lb",      "Beverages",    10.99,  60),
    (6, "Hand Soap",             "Personal Care", 3.49,  85),
]
cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?)",
                   [(p[0], p[1], p[2], p[3]) for p in products])

# Step 3: Generating my monthly numbers

months = [f"2025-{m:02d}" for m in range(1, 13)]

# I am giving each month a seasonal factor: a slow January, a summer bump,
# and a strong December holiday season.
seasonal_factor = {
    "2025-01": 0.85, "2025-02": 0.88, "2025-03": 0.95, "2025-04": 1.00,
    "2025-05": 1.05, "2025-06": 1.12, "2025-07": 1.15, "2025-08": 1.10,
    "2025-09": 1.00, "2025-10": 1.02, "2025-11": 1.10, "2025-12": 1.30,
}

rows = []
for location_id, store_name, province, size in stores:
    for month_number, month in enumerate(months):

        # I left out Coquitlam's July data on purpose. In my story, the store was
        # closed for renovation. This is my missing information test case.
        if store_name == "Coquitlam" and month == "2025-07":
            continue

        # I am adding a gentle upward trend, so sales grow about 1.2% each month
        growth = 1 + 0.012 * month_number

        for product_id, product_name, category, unit_price, typical_units in products:
            # I am adding a small random variation (up to 6% up or down)
            # so the numbers look realistic instead of perfectly smooth
            variation = random.uniform(0.94, 1.06)

            units_sold = round(typical_units * size * seasonal_factor[month] * growth * variation)
            revenue = round(units_sold * unit_price, 2)

            # I am setting end-of-month stock to roughly one and a half months of sales
            units_on_hand = round(typical_units * size * 1.5 * random.uniform(0.85, 1.15))

            # I made Laundry Detergent run low in December at every store,
            # so my agent has a clear low-stock situation to find
            if product_name == "Laundry Detergent" and month == "2025-12":
                units_on_hand = round(12 * size)

            rows.append((location_id, product_id, month, units_sold, revenue, units_on_hand))

cursor.executemany("INSERT INTO monthly_inventory VALUES (?, ?, ?, ?, ?, ?)", rows)

# I am saving everything to the database file
connection.commit()

# Step 4: Printing a quick summary so I can confirm it worked
for table in ["locations", "products", "monthly_inventory"]:
    count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {count} rows")

connection.close()
print("Database created: inventory.db")

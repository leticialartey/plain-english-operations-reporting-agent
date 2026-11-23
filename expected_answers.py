# expected_answers.py
# In this file, I am querying my inventory database directly with SQL to get
# the correct answers to my test questions. I also verified these answers
# independently in Excel. Later, I will compare my agent's answers against
# these to measure whether it was accurate.

import sqlite3
import pandas as pd

# I am connecting to the database I built in create_inventory_database.py
connection = sqlite3.connect("inventory.db")


# I wrote this helper so I don't repeat the same code for every question.
# It runs my SQL and prints the results as a neat table under a title.
def show_answer(title, sql):
    print(f"\n{title}")
    results = pd.read_sql_query(sql, connection)
    if results.empty:
        print("(No rows came back)")
    else:
        print(results.to_string(index=False))


# My formal test questions

# Test Question 1: "What is the total revenue across all stores in 2025?"
# I am adding up every revenue value in the table to get one business-wide total.
show_answer("Test Question 1: Total revenue across all stores in 2025 (CAD)",
    """
    SELECT ROUND(SUM(revenue), 2) AS total_revenue
    FROM monthly_inventory
    WHERE month LIKE '2025-%'
    """)

# Test Question 2: "Which store has the highest revenue in 2025?"
# I am totaling revenue for each store and sorting from highest to lowest.
show_answer("Test Question 2: Revenue by store in 2025 (CAD)",
    """
    SELECT l.store_name, ROUND(SUM(m.revenue), 2) AS total_revenue
    FROM monthly_inventory m
    JOIN locations l ON m.location_id = l.location_id
    WHERE m.month LIKE '2025-%'
    GROUP BY l.store_name
    ORDER BY total_revenue DESC
    """)

# Test Question 3: "Which product sold the most units in 2025?"
# I am totaling units sold for each product across all stores.
show_answer("Test Question 3: Units sold by product in 2025",
    """
    SELECT p.product_name, SUM(m.units_sold) AS total_units_sold
    FROM monthly_inventory m
    JOIN products p ON m.product_id = p.product_id
    WHERE m.month LIKE '2025-%'
    GROUP BY p.product_name
    ORDER BY total_units_sold DESC
    """)

# Test Question 4: "How much did the Coquitlam store sell in July 2025?"
# I left this data out on purpose. When I ask for the rows, nothing comes back,
# and when I ask for a total, SQL returns None. Both mean I have no record,
# NOT that Coquitlam sold zero.
show_answer("Test Question 4 (rows): Coquitlam's July 2025 records",
    """
    SELECT l.store_name, m.month, m.units_sold, m.revenue
    FROM monthly_inventory m
    JOIN locations l ON m.location_id = l.location_id
    WHERE l.store_name = 'Coquitlam' AND m.month = '2025-07'
    """)

show_answer("Test Question 4 (total): Coquitlam's July 2025 totals",
    """
    SELECT SUM(m.units_sold) AS total_units_sold, SUM(m.revenue) AS total_revenue
    FROM monthly_inventory m
    JOIN locations l ON m.location_id = l.location_id
    WHERE l.store_name = 'Coquitlam' AND m.month = '2025-07'
    """)


# My bonus questions (for the demo if time allows)

# Bonus 1: "Which month recorded the highest sales?"
# I am totaling revenue and units for each month across all stores.
show_answer("Bonus 1: Sales by month in 2025",
    """
    SELECT month, SUM(units_sold) AS total_units_sold,
           ROUND(SUM(revenue), 2) AS total_revenue
    FROM monthly_inventory
    WHERE month LIKE '2025-%'
    GROUP BY month
    ORDER BY month
    """)

# Bonus 2: "Are sales increasing or decreasing over time?"
# I am comparing each quarter, because a quarter smooths out single-month bumps.
show_answer("Bonus 2: Revenue by quarter in 2025 (CAD)",
    """
    SELECT CASE
             WHEN month <= '2025-03' THEN 'Q1 (Jan-Mar)'
             WHEN month <= '2025-06' THEN 'Q2 (Apr-Jun)'
             WHEN month <= '2025-09' THEN 'Q3 (Jul-Sep)'
             ELSE 'Q4 (Oct-Dec)'
           END AS quarter,
           ROUND(SUM(revenue), 2) AS total_revenue
    FROM monthly_inventory
    WHERE month LIKE '2025-%'
    GROUP BY quarter
    ORDER BY quarter
    """)

# Bonus 3: "Which product sold the most units in each store?"
# I am totaling units per store and product, then keeping only each store's top product.
show_answer("Bonus 3: Top-selling product in each store (units, 2025)",
    """
    WITH store_product AS (
        SELECT l.store_name, p.product_name, SUM(m.units_sold) AS total_units_sold
        FROM monthly_inventory m
        JOIN locations l ON m.location_id = l.location_id
        JOIN products  p ON m.product_id  = p.product_id
        WHERE m.month LIKE '2025-%'
        GROUP BY l.store_name, p.product_name
    )
    SELECT store_name, product_name, total_units_sold
    FROM store_product s
    WHERE total_units_sold = (SELECT MAX(total_units_sold)
                              FROM store_product
                              WHERE store_name = s.store_name)
    ORDER BY total_units_sold DESC
    """)

# Bonus 4: "Which product is running lowest on stock?"
# I am looking at the most recent month (December 2025) across all stores.
show_answer("Bonus 4: Stock on hand by product, end of December 2025",
    """
    SELECT p.product_name, SUM(m.units_on_hand) AS total_on_hand
    FROM monthly_inventory m
    JOIN products p ON m.product_id = p.product_id
    WHERE m.month = '2025-12'
    GROUP BY p.product_name
    ORDER BY total_on_hand ASC
    """)

connection.close()

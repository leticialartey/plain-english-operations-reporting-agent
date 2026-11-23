# tools.py
# In this file, I am building the three tools my agent can use:
#   1. run_query: runs a read-only SQL query on my inventory database
#   2. make_chart: draws a bar chart from query results and saves it as an image
#   3. check_data_coverage: checks which stores are missing any months of data
# The model never touches the database directly. It asks for a tool, and my Python
# code decides whether to run it and sends the result back.

import sqlite3
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # I am telling Matplotlib to save charts as files without opening a window
import matplotlib.pyplot as plt

DB_FILE = "inventory.db"
CHART_FOLDER = "charts"
MAX_ROWS = 100  # I am capping results so a huge query can't flood the model with data


# Tool 1: run_query
def run_query(sql):
    # I am cleaning up the query and checking what kind of statement it is
    cleaned = sql.strip().rstrip(";").strip()
    first_word = cleaned.split()[0].upper() if cleaned else ""

    # I only allow queries that read data. Anything else is refused before it runs.
    if first_word not in ("SELECT", "WITH"):
        return {
            "status": "refused",
            "error": "Only read-only SELECT queries are allowed. "
                     "This tool cannot add, change, or delete data.",
        }

    # I am opening the database in read-only mode as a second layer of protection.
    # Even if a harmful query slipped past my check above, SQLite itself would block it.
    try:
        connection = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
        cursor = connection.cursor()
        cursor.execute(cleaned)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchmany(MAX_ROWS)
        connection.close()
    except Exception as problem:
        # I am sending the error back to the model so it can fix its query and try again
        return {"status": "error", "error": str(problem)}

    result = {
        "status": "ok",
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
    }

    # I am attaching notes that guide the model's next step, based on what came back.
    # I added most of these after my second test run, when the model ignored the rules
    # in its instructions but still paid attention to the tool results.
    notes = []
    sql_upper = cleaned.upper()

    # I am flagging the two ways missing data shows up, so the model doesn't mistake it for zero
    if len(rows) == 0:
        notes.append("No rows matched this query. This means no data exists "
                     "for what was asked. Do not treat this as zero.")
    elif all(value is None for row in rows for value in row):
        notes.append("The query returned only empty (NULL) values. This means no "
                     "matching data exists. Do not treat this as zero.")

    # I am warning the model when it used LIMIT, because then it can't see the full ranking
    if " LIMIT " in f" {sql_upper} ":
        notes.append("This query used LIMIT, so you only see the top rows. If the "
                     "question asks which is highest, lowest, or most, run the query "
                     "again WITHOUT LIMIT before answering, so you can see every item, "
                     "name the runner-up, and make a chart.")

    # I am telling the model to make a chart when the result compares three or more items
    elif len(rows) >= 3 and any(isinstance(v, (int, float)) for v in rows[0]):
        notes.append(f"This result compares {len(rows)} items. Call make_chart with "
                     "ALL of these results before giving your final answer.")

    # When the model adds up totals, I am automatically attaching the coverage check,
    # so it knows about any missing months right next to the numbers
    if any(word in sql_upper for word in ("SUM(", "COUNT(", "AVG(")):
        coverage = check_data_coverage()
        if coverage["status"] == "ok":
            notes.append("Data coverage: " + coverage["summary"])

    if notes:
        result["note"] = " ".join(notes)

    return result


# Tool 2: make_chart
def make_chart(title, labels, values, y_label):
    # checking the inputs first, because the model might send something unusable
    if not labels or not values or len(labels) != len(values):
        return {"status": "error",
                "error": "labels and values must be non-empty lists of the same length."}
    try:
        values = [float(v) for v in values]
    except (TypeError, ValueError):
        return {"status": "error", "error": "All values must be numbers."}

    #  creating the charts folder if it doesn't exist yet
    os.makedirs(CHART_FOLDER, exist_ok=True)

    # this is drawing a simple bar chart with the value written on top of each bar
    figure, axes = plt.subplots(figsize=(8, 5))
    bars = axes.bar([str(label) for label in labels], values, color="#1F4E79")
    axes.set_title(title)
    axes.set_ylabel(y_label)
    axes.bar_label(bars, labels=[f"{v:,.2f}" if v % 1 else f"{v:,.0f}" for v in values],
                   padding=3, fontsize=9)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()

    # naming each chart with the date and time so no chart overwrites another
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(CHART_FOLDER, f"chart_{timestamp}.png")
    figure.savefig(file_path, dpi=150)
    plt.close(figure)

    return {"status": "ok", "chart_file": file_path}


# Tool 3: check_data_coverage
def check_data_coverage():
    # I added this tool after my first test run. The model claimed there were no gaps
    # in the data without checking, so now Python does the checking instead.
    all_months = [f"2025-{m:02d}" for m in range(1, 13)]
    try:
        connection = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
        cursor = connection.cursor()
        store_names = [row[0] for row in cursor.execute(
            "SELECT store_name FROM locations ORDER BY location_id")]
        months_by_store = {}
        for store in store_names:
            months_by_store[store] = [row[0] for row in cursor.execute(
                """
                SELECT DISTINCT m.month
                FROM monthly_inventory m
                JOIN locations l ON m.location_id = l.location_id
                WHERE l.store_name = ?
                """, (store,))]
        connection.close()
    except Exception as problem:
        return {"status": "error", "error": str(problem)}

    # comparing each store's months against the full year to find any gaps
    gaps = []
    months_per_store = {}
    for store, months in months_by_store.items():
        months_per_store[store] = len(months)
        missing = [month for month in all_months if month not in months]
        if missing:
            gaps.append({"store": store, "missing_months": missing})

    if gaps:
        details = "; ".join(f"{g['store']} is missing {', '.join(g['missing_months'])}"
                            for g in gaps)
        summary = (f"The data is NOT complete. {details}. Any total that includes "
                   "these stores leaves out those months, and you must say so.")
    else:
        summary = "The data is complete: every store has all 12 months of 2025."

    return {"status": "ok", "months_expected": 12,
            "months_per_store": months_per_store, "gaps": gaps, "summary": summary}


# Testing my tools by themselves, with no AI involved.
# This part only runs when I run tools.py directly (python tools.py).
# When my agent imports these tools later, this part is skipped.
if __name__ == "__main__":

    print("\nTest 1: A normal query (revenue by store)")
    result = run_query("""
        SELECT l.store_name, ROUND(SUM(m.revenue), 2) AS total_revenue
        FROM monthly_inventory m
        JOIN locations l ON m.location_id = l.location_id
        GROUP BY l.store_name
        ORDER BY total_revenue DESC
    """)
    print(result)

    print("\nTest 2: Making a chart from Test 1's results")
    store_names = [row[0] for row in result["rows"]]
    revenues = [row[1] for row in result["rows"]]
    print(make_chart("Total Revenue by Store, 2025", store_names, revenues, "Revenue (CAD)"))

    print("\nTest 3: Missing data (Coquitlam in July 2025)")
    print(run_query("""
        SELECT SUM(m.units_sold) AS total_units_sold
        FROM monthly_inventory m
        JOIN locations l ON m.location_id = l.location_id
        WHERE l.store_name = 'Coquitlam' AND m.month = '2025-07'
    """))

    print("\nTest 4: A request to delete data (should be refused)")
    print(run_query("DELETE FROM monthly_inventory WHERE location_id = 4"))

    print("\nTest 5: A broken query with a wrong column name (should return an error)")
    print(run_query("SELECT total_sales FROM monthly_inventory"))

    print("\nTest 6: Checking data coverage (should find Coquitlam's missing July)")
    print(check_data_coverage())

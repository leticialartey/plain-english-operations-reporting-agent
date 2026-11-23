# agent.py
# In this file, I am building my Plain-English Operations Reporting Agent.
# A user types a question, my local AI model (Qwen 2.5 through Ollama) decides
# which tool to use, my Python code runs that tool, and the model uses the results
# to decide what to do next, until it can give a plain-language answer.

import json
import re
from datetime import datetime

import ollama

from tools import run_query, make_chart, check_data_coverage

MODEL = "qwen2.5:7b"
MAX_STEPS = 10       # I am limiting how many rounds the model can take for one question
MAX_CORRECTIONS = 2  # I am blocking an answer after two failed checks in a row with no progress
LOG_FILE = "agent_log.txt"  # every question, tool request, action, and result is saved here

# I am keeping a small scorecard for the most recent question, so my test script can
# measure how often the model's FIRST answer was good, not just its final one
LAST_RUN_STATS = {}


def log(text=""):
    # I am showing each line on screen and also saving it to my log file,
    # so I have a permanent record of everything the agent did
    print(text)
    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(text + "\n")


def describe_action(tool_name, result):
    # I am writing a plain description of what Python actually did for each tool request,
    # which is the "actions Python executed" part of my record
    status = result.get("status")
    if tool_name == "run_query":
        if status == "ok":
            return f"Ran the SQL query in read-only mode and got {result['row_count']} row(s)."
        if status == "refused":
            return "Refused to run the query, because it was not a read-only SELECT."
        return "Tried to run the query, but SQLite returned an error."
    if tool_name == "make_chart":
        if status == "ok":
            return f"Drew the bar chart and saved it as {result['chart_file']}."
        if "Chart not drawn" in result.get("error", ""):
            return "Refused to draw the chart, because its data did not match any query result."
        return "Tried to draw the chart, but the inputs were not usable."
    if tool_name == "check_data_coverage":
        return "Counted the months of data for every store and listed any gaps."
    return "Did nothing, because no tool with that name exists."


# My instructions to the model.
# I am describing my database exactly, so the model writes correct SQL,
# and I am setting clear rules so it never invents numbers.
SYSTEM_PROMPT = """
You are a reporting assistant for a small retail business with five stores in
British Columbia, Canada. You answer questions from managers who are not technical,
using ONLY data from the company database.

THE DATABASE (SQLite) has three tables:

locations(location_id INTEGER, store_name TEXT, province TEXT)
  Stores: Vancouver, Surrey, Burnaby, Coquitlam, Langley

products(product_id INTEGER, product_name TEXT, category TEXT, unit_price REAL)
  Products: Bottled Water 12-pack, Paper Towels, Laundry Detergent,
  Granola Bars, Coffee Beans 1lb, Hand Soap

monthly_inventory(location_id INTEGER, product_id INTEGER, month TEXT,
                  units_sold INTEGER, revenue REAL, units_on_hand INTEGER)
  month is text in the format 'YYYY-MM', for example '2025-07'.
  revenue is already calculated in Canadian dollars (CAD). Do not multiply by price.
  units_on_hand is the stock left at the end of that month.
  The data covers January 2025 to December 2025 only.

To show store or product names, JOIN monthly_inventory to locations or products.

YOUR TOOLS:
- run_query: runs a read-only SQL SELECT query and returns the results.
- make_chart: draws a bar chart from results you already received.
- check_data_coverage: reports which stores are missing any months of data.

RULES YOU MUST FOLLOW:
1. Always use run_query to get numbers. Never answer with a number you did not
   receive from a query.
2. If a query returns an error, read the error, fix the SQL, and try again.
3. If a result comes back with a note saying no data exists, or the values are
   empty (None/NULL), tell the user the data is missing. Missing data is NOT zero.
   Never guess or estimate.
4. If the question asks which store, product, or month is highest, lowest, best,
   or worst, or asks you to compare or rank them, do NOT use LIMIT in your SQL.
   Get the full list, then call make_chart with ALL of the results before giving
   your final answer, and mention the runner-up in your answer.
   For a single total, or a lookup for one store and one month, do NOT make a chart.
5. Before answering any question about totals or rankings across stores or across
   the year, call check_data_coverage. If it reports gaps, mention them in your
   answer and explain which totals they affect. Never say the data is complete
   unless check_data_coverage told you it is.
6. "Sold the most" means the most units sold unless the user says revenue.
   Always say which measure you used.
7. You can only read data. If the user asks to add, change, or delete data,
   explain politely that you can only look up information.
8. Every tool result may include a "note". Read it carefully and follow what it
   says before giving your final answer.
9. Only mention store names, product names, and numbers that appear in tool
   results. Never guess a runner-up or claim the data is complete without evidence.
10. Write your final answer in plain, friendly English for a non-technical manager.
   Always include the actual figures as evidence, for example
   "Vancouver had the highest revenue, with $60,235.02 CAD."
   Format money with a dollar sign, commas, and two decimals.
"""


# Describing my tools to the model.
# The model never sees my Python code. It only sees these descriptions,
# so they need to say clearly what each tool does and what inputs it needs.
TOOL_DESCRIPTIONS = [
    {
        "type": "function",
        "function": {
            "name": "run_query",
            "description": "Run a read-only SQL SELECT query on the inventory "
                           "database and return the columns and rows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single SQLite SELECT query.",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_chart",
            "description": "Draw a bar chart comparing values, using results "
                           "already returned by run_query. Saves it as an image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Chart title."},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names for each bar, such as store names.",
                    },
                    "values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "One number per label, in the same order.",
                    },
                    "y_label": {"type": "string", "description": "Label for the y-axis."},
                },
                "required": ["title", "labels", "values", "y_label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_data_coverage",
            "description": "Check whether every store has all 12 months of 2025 data, "
                           "and list any missing months. Takes no inputs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# I am connecting each tool name the model might ask for to my real Python function
AVAILABLE_TOOLS = {
    "run_query": run_query,
    "make_chart": make_chart,
    "check_data_coverage": check_data_coverage,
}


def fix_list(value):
    # Small models sometimes send a list as text, like '["a", "b"]'.
    # I am converting that text back into a real list so my chart tool can use it.
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def collect_numbers(value, found):
    # I am digging through a tool result and collecting every number in it,
    # so I can later check the model's answer against real figures
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        found.append(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            collect_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            collect_numbers(item, found)


def check_chart_inputs(arguments, query_numbers, query_text):
    # After my sixth test run, the model drew a chart with invented values even though
    # its written answer was correct. Now I am checking the chart's data before drawing it.
    problems = []
    for value in arguments.get("values") or []:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not any(abs(number - real) < 0.01 for real in query_numbers):
            problems.append(f"value {value}")
    for label in arguments.get("labels") or []:
        if str(label) not in query_text:
            problems.append(f"label '{label}'")
    return problems


def find_unsupported_numbers(answer, tool_numbers):
    # I added this check after my third test run, when the model invented
    # believable numbers instead of running a second query.
    # I am pulling every number out of the model's answer and checking that
    # each one actually came from a tool result.
    unsupported = []
    for text in re.findall(r"\d[\d,]*(?:\.\d+)?", answer):
        number = float(text.replace(",", ""))

        # I am skipping small whole numbers and the year, because they are usually
        # months, counts, or product names (like "12-pack"), not data figures
        if (number <= 12 and number.is_integer()) or number == 2025:
            continue

        supported = any(abs(number - real) < 0.01 or round(real) == number
                        for real in tool_numbers)
        if not supported:
            unsupported.append(text)
    return unsupported


def remove_images(answer):
    # After my fifth test run, the model correctly linked to a real chart, but my check
    # rejected it. Now I am removing image links from the answer before checking,
    # and adding the real chart location myself if a chart was made.
    image_pattern = r"!\[[^\]]*\]\([^)]*\)"
    had_image = bool(re.search(image_pattern, answer))
    cleaned = re.sub(image_pattern, "", answer)
    # I am also removing chart file names, so their date and time aren't mistaken for data
    cleaned = re.sub(r"charts/chart_\d{8}_\d{6}\.png", "", cleaned)
    # I am tidying up the blank gaps left behind where images were removed
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), had_image


def is_ranking_question(question):
    # I am treating any question with a ranking word as one that needs a chart
    ranking_words = ["highest", "lowest", "most", "least", "best", "worst",
                     "top", "rank", "compare", "comparison"]
    words = re.findall(r"[a-z]+", question.lower())
    return any(word in words for word in ranking_words)


def promised_without_doing(answer):
    # I am catching answers where the model says it will do something
    # (like run a query or make a chart) but never actually called the tool,
    # (I check for fake images separately in remove_images)
    # After my fourth test run, I added "I can", "I could", and "let me", because the model
    # started offering to do the work ("I can run the query again") instead of doing it
    promise = re.search(r"\b(?:I(?:'ll| will| am going to| can| could)|let me)\s+"
                        r"(?:now\s+)?(?:also\s+)?"
                        r"(?:run|create|make|calculate|query|check|generate|draw)\b",
                        answer, re.IGNORECASE)
    return bool(promise)


def ask_agent(question):
    # I am recording the question and the time, so each entry in my log is easy to find
    log(f"\nQUESTION ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}): {question}")

    # I am starting the conversation with my instructions and the user's question
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    # I am resetting my scorecard for this new question
    LAST_RUN_STATS.clear()
    LAST_RUN_STATS.update({"first_try_accepted": None, "rejections": 0,
                           "chart_refusals": 0, "tool_calls": 0, "blocked": False})

    tool_numbers = []   # every number my tools have returned so far for this question
    query_numbers = []  # only the numbers that came from run_query, for checking charts
    query_text = ""     # all run_query results as text, for checking chart labels
    corrections = 0     # how many answers in a row have failed my checks
    chart_files = []    # every chart my chart tool has saved for this question
    needs_chart = is_ranking_question(question)

    for step in range(1, MAX_STEPS + 1):
        # I am sending the whole conversation so far to the model.
        # Temperature 0 makes its answers as consistent as possible between runs.
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            tools=TOOL_DESCRIPTIONS,
            options={"temperature": 0},
        )
        reply = response.message
        messages.append(reply)

        # If the model didn't ask for any tools, it is trying to give its final answer.
        # Before I accept it, I am checking that it is actually supported by evidence.
        if not reply.tool_calls:
            answer, had_image = remove_images(reply.content or "")
            unsupported = find_unsupported_numbers(answer, tool_numbers)
            promised = promised_without_doing(answer)
            fake_image = had_image and not chart_files
            missing_chart = needs_chart and not chart_files

            passed_checks = not (unsupported or promised or fake_image or missing_chart)

            # I am recording whether the model's very first answer passed, for my scorecard
            if LAST_RUN_STATS["first_try_accepted"] is None:
                LAST_RUN_STATS["first_try_accepted"] = passed_checks

            if passed_checks:
                log("\n[Check] Every number in the answer matches a tool result. Answer accepted.")
                # I am adding the real chart location myself, so the user knows where to find it
                if chart_files:
                    answer += f"\n\nChart saved: {chart_files[-1]}"
                return answer

            # I am printing the rejected answer, so I can see exactly what went wrong
            log("\n[Check] The model tried to answer with:")
            log("        " + answer.replace("\n", "\n        "))

            corrections += 1
            LAST_RUN_STATS["rejections"] += 1
            if corrections > MAX_CORRECTIONS:
                LAST_RUN_STATS["blocked"] = True
                # The model kept failing my checks without making progress, so I am blocking
                # the answer rather than showing the user numbers that might be invented
                log(f"\n[Check] The answer failed {corrections} times in a row with no "
                      "new tool calls. Answer blocked.")
                return ("I wasn't able to produce an answer that is fully supported by "
                        "the data, so I'm not showing one. Please try asking the "
                        "question in a simpler way.")

            # I am telling the model exactly what was wrong so it can fix its answer
            problems = []
            if unsupported:
                problems.append("These numbers in your answer did not come from any tool "
                                f"result: {', '.join(unsupported)}. Remove them, or call "
                                "run_query to get the real figures.")
            if promised or fake_image:
                problems.append("You described an action (like running a query or making a "
                                "chart) instead of doing it. Do not describe tool calls. "
                                "Call the tool now.")
            if missing_chart:
                problems.append("This question asks you to rank or compare, so you must call "
                                "make_chart with the full results before answering.")
            feedback = (" ".join(problems) + " Then give your final answer using only "
                        "numbers that appear in tool results.")

            log(f"[Check] Answer rejected ({corrections} in a row).")
            log(f"        Reason sent to the model: {feedback}")
            messages.append({"role": "user", "content": feedback})
            continue

        # The model is calling tools, which means it is making progress,
        # so I am resetting its count of failed answers in a row
        corrections = 0

        # I am running every tool the model asked for, one at a time
        for call in reply.tool_calls:
            tool_name = call.function.name
            arguments = call.function.arguments or {}

            LAST_RUN_STATS["tool_calls"] += 1

            # Part 1 of my record: what the model asked for
            log(f"\n[Step {step}] MODEL REQUESTED: {tool_name}")
            log(f"           Inputs: {arguments}")

            if tool_name not in AVAILABLE_TOOLS:
                # I am telling the model it asked for a tool that doesn't exist
                result = {"status": "error",
                          "error": f"There is no tool called '{tool_name}'."}
            else:
                chart_problems = []
                if tool_name == "make_chart":
                    arguments["labels"] = fix_list(arguments.get("labels"))
                    arguments["values"] = fix_list(arguments.get("values"))
                    chart_problems = check_chart_inputs(arguments, query_numbers, query_text)

                if chart_problems:
                    # I am refusing to draw a chart that contains data no query returned
                    LAST_RUN_STATS["chart_refusals"] += 1
                    log(f"\n[Check] Chart refused. These did not come from any query result: "
                          f"{', '.join(chart_problems)}")
                    result = {"status": "error",
                              "error": "Chart not drawn. These inputs did not come from any "
                                       f"query result: {', '.join(chart_problems)}. Copy the "
                                       "labels and values exactly from your run_query results "
                                       "and call make_chart again."}
                else:
                    try:
                        result = AVAILABLE_TOOLS[tool_name](**arguments)
                    except TypeError as problem:
                        # I am catching wrong or missing inputs so the model can try again
                        result = {"status": "error", "error": f"Wrong inputs: {problem}"}

            # Parts 2 and 3 of my record: what Python did, and what came back
            log(f"           PYTHON DID: {describe_action(tool_name, result)}")
            log(f"           RESULT RETURNED: {result}")

            # I am remembering every number the tools returned, for my evidence check,
            # and every chart that was actually saved
            collect_numbers(result, tool_numbers)
            if tool_name == "run_query" and result.get("status") == "ok":
                collect_numbers(result.get("rows"), query_numbers)
                query_text += json.dumps(result.get("rows"))
            if tool_name == "make_chart" and result.get("status") == "ok":
                chart_files.append(result["chart_file"])

            # I am sending the tool's result back to the model so it can decide what to do next
            messages.append({
                "role": "tool",
                "content": json.dumps(result),
                "tool_name": tool_name,
            })

    # If the model used up all its steps without finishing, I am stopping it safely
    log("\n[Check] The model reached the step limit without a final answer.")
    return ("I wasn't able to finish answering within the step limit. "
            "Please try rephrasing the question.")


# Running my agent as a simple question-and-answer program in the terminal
if __name__ == "__main__":
    print("Plain-English Operations Reporting Agent")
    log(f"\nSESSION STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (model: {MODEL})")
    print("Ask a question about 2025 sales and inventory, or type 'quit' to stop.")

    while True:
        question = input("\nYour question: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        if not question:
            continue

        answer = ask_agent(question)
        log("\nFINAL ANSWER:")
        log(answer)

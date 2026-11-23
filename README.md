# Plain-English Operations Reporting Agent

An AI agent that answers everyday business questions about a fictional retail company's sales and inventory. A manager with no technical background types a question such as "Which store has the highest revenue in 2025?", and the agent looks up the numbers in a database, makes a chart when the question asks for a ranking or comparison, and explains the answer in plain English.

The agent is designed so that every figure in an answer comes from a tool result. Python checks this before any answer is shown. If the data needed to answer a question doesn't exist, the agent is instructed to say so instead of guessing, and it it did so in every test of missing data.

## How it works

The agent has three parts working together.

**The model.** Qwen 2.5 7B, a free large language model (LLM) running locally on my Mac through Ollama. It reads the question, decides which tool to use, writes the SQL, and writes the final answer.

**The tools.** Three Python functions the agent can ask for:

- `run_query` runs a SQL query on the database. It only accepts queries that start with SELECT or WITH, and it opens the database in read-only mode, so data can never be changed.
- `make_chart` draws a bar chart from labels and values the model provides, and saves it in the `charts` folder.
- `check_data_coverage` checks whether every store has all 12 months of 2025 data and lists any gaps.

**The checks.** Python code that guides the model and inspects its work. It works in two places.

First, in the tool results. When a query uses LIMIT, the result includes a note telling the model to run it again without LIMIT. When a result compares three or more items, the note tells the model to make a chart. When a query adds up totals (SUM, COUNT, or AVG), Python automatically runs the coverage check and attaches the result, so the model is told about missing months next to the numbers.

Second, on every answer before it is shown. Python rejects an answer if it contains a number that no tool returned, if it describes an action ("I will run the query", "I can create a chart") instead of doing it, if it shows an image link when no chart was made, or if the question contains a ranking word (such as highest, most, best, top, or compare) and no chart was made. Python also refuses to draw a chart if any of its labels or values didn't appear in a query result. Small whole numbers from 1 to 12 and the year 2025 are not checked, because they are usually months, counts, or product names such as "12-pack".

When an answer is rejected, Python tells the model exactly what was wrong, and the model tries again. If the model gives three rejected answers in a row without calling a tool in between, the answer is blocked and the user is told no verified answer could be produced. Each question is also limited to 10 rounds.

The model asks for a tool, Python runs it and returns the result, and the model uses that result to decide what to do next. This loop repeats until the model gives an answer that passes every check.

**The grader (for testing only).** Separate from the agent, `run_tests.py` contains a grader that I use to measure how well the agent works. It asks each test question automatically and marks the final answer as pass or fail by comparing it with the answer key: for example, whether it has the right figures, names the runner-up, mentions Coquitlam's missing July, and includes a chart when one is required. The checks and the grader both inspect answers, but they are different. The checks are part of the agent and run before every answer is shown, without knowing the correct answers. The grader knows the correct answers, but it is not part of the agent and only runs during testing.

## The database

`inventory.db` is a fictional SQLite database for a retail business with five stores, named after real cities in British Columbia, Canada (Vancouver, Surrey, Burnaby, Coquitlam, and Langley). It covers six products with monthly totals for January to December 2025: units sold, revenue in Canadian dollars, and units on hand at the end of each month. It has 354 records.

The numbers were generated from a formula (store size, typical product sales, a seasonal pattern, and a gentle upward trend) plus a small random variation with a fixed seed, so the database is identical every time it is rebuilt.

Two conditions are built in on purpose for testing. Coquitlam has no July 2025 data (in the story, the store was closed for renovation), which is the missing information case. Laundry Detergent runs very low on stock at every store in December.

All data is invented. No real business, customer, or personal records are used.

## Project files

| File | What it does |
|---|---|
| `requirements.txt` | The Python packages the project needs, for installing with one command. |
| `create_inventory_database.py` | Builds `inventory.db`. Produces identical data every run. |
| `expected_answers.py` | Queries the database directly with SQL to get the correct answers to test questions 1 to 4 and four bonus questions. |
| `answer_key.txt` | The verified correct answers and expected agent behaviour for all five test questions and the reworded versions, the stock question (a known limitation), and the correct answers to the bonus questions. |
| `inventory_database.xlsx` | An Excel copy of the database. Its Answer Check sheet recalculates the answers to test questions 1 to 4 and bonus questions 1, 2, and 4 with formulas, as an independent check on the SQL. |
| `tools.py` | The three tools. Run it directly to test the tools on their own, without the model. |
| `agent.py` | The agent: instructions to the model, the decision loop, and the answer checks. Run it to ask questions. |
| `run_tests.py` | Runs the test questions automatically, grades each answer against the answer key, and measures accuracy. |
| `agent_log.txt` | The record of every session since logging was added: each question, every tool the model requested, what Python did, what came back, every check, and the final answer. Entries up to and including the second test round say “the AI” in their [Check] lines; entries from the third test round onward say “the model”. Only the wording changed, not the agent’s behaviour. |
| `charts/` | Charts saved by the agent and by the tool self-tests. |
| `test_records/` | Evidence from development: `test_run_1.txt` to `test_run_7.txt` (terminal output from the seven development runs; runs 1 to 6 each revealed a problem that was then fixed, and run 7 was the first where all four questions passed), `test_run_8.txt` to `test_run_10.txt` (the stock question and the attempted fixes), and the results of all three test rounds. |

## Setup

These steps are for macOS. I built and tested the project on a MacBook Pro with an M5 chip and 16 GB of memory.

1. Install Anaconda, which includes Python, pandas, and Matplotlib.
2. Install Ollama from ollama.com and open it, so it runs in the background.
3. Download the model (about 4.7 GB):

```bash
ollama pull qwen2.5:7b
```

4. Install the Python packages listed in `requirements.txt` (with Anaconda, pandas and Matplotlib are already installed, so this adds the Ollama library):

```bash
pip install -r requirements.txt
```

Use the `python` command from Anaconda for every step below. On a Mac, `python3` may point to the older built-in Python, which doesn't include pandas or Matplotlib.

## How to run it

Run these from the project folder, in this order.

**1. Build the database**

```bash
python create_inventory_database.py
```

The output should include `monthly_inventory: 354 rows`.

**2. See the correct answers**

```bash
python expected_answers.py
```

**3. Test the tools on their own (optional)**

```bash
python tools.py
```

Runs six self-tests: a normal query, a chart, a missing data query, a refused DELETE, a query with an error, and the coverage check finding Coquitlam's missing July.

**4. Ask the agent questions**

```bash
python agent.py
```

Type a question and press Enter. Type quit to stop. In my tests on a MacBook Pro with an M5 chip and 16 GB of memory, answers took between about 3 and 46 seconds. They may take longer on other computers, especially ones with less memory or without a recent Apple chip or a dedicated graphics card. The first question after starting Ollama is usually slower too, while the model loads into memory.

**5. Run the full test suite**

```bash
python run_tests.py
```

Runs 17 tests, which took about 7 minutes on my Mac. Results are saved to `test_results.csv` and the full record is added to `agent_log.txt`.

## Test questions

| # | Question | Type | Correct answer |
|---|---|---|---|
| 1 | What is the total revenue across all stores in 2025? | Successful case, no chart | $227,577.73 CAD, noting Coquitlam's July is missing |
| 2 | Which store has the highest revenue in 2025? | Successful case, with chart | Vancouver, $60,235.02 CAD; runner-up Surrey, $53,267.65 |
| 3 | Which product sold the most units in 2025? | Successful case, with chart | Granola Bars, 8,203 units; runner-up Bottled Water 12-pack, 7,297 |
| 4 | How much did the Coquitlam store sell in July 2025? | Missing information case | No data exists. Unknown, not zero. |
| 5 | Delete all of Coquitlam's records. | Invalid request | Refused. The agent can only read data. |

I also tested a sixth question, "Which product is running lowest on stock?" (correct answer: Laundry Detergent, 60 units at the end of December 2025). The final agent gets this wrong; see Known limitations.

Questions 1 to 4 were also each tested once with a reworded version, such as "Which branch earned the most money in 2025?" for question 2.

## Results

**First measured round.** Questions 1 to 4, three runs each: 12 of 12 final answers passed the grader. First-answer results were not measured in this round.

**Second measured round.** Questions 1 to 4 three times each, the four reworded versions once each, and question 5 once (17 runs). Two things were measured for each run:

- **First answer passed the checks:** whether the model's first attempt at an answer passed all of Python's checks, without any correction.
- **Final answer passed the grader:** whether the answer finally shown to the user passed the automated grader, which checks it against the answer key (for example, the correct figures, the runner-up, the warning about Coquitlam's July, and whether a chart was made).

| Test group | First answer passed the checks | Final answer passed the grader |
|---|---|---|
| Original questions (12 runs) | 3 of 12 (25%) | 12 of 12 (100%) |
| Reworded questions (4 runs) | 2 of 4 (50%) | 3 of 4 (75%) |
| Invalid request (1 run) | 1 of 1 (100%) | 1 of 1 (100%) |
| **All tests (17 runs)** | **6 of 17 (35%)** | **16 of 17 (94%)** |

Python counted the database rows before and after every run in this round, and there were always 354, so no data was ever changed.

The model's first answers often failed because they contained invented figures, offered to do something instead of doing it, or skipped the required chart. With the checks in place, the final answers passed the grader in 16 of 17 runs. The one failure was a safe failure: the agent blocked its answer instead of showing an unverified one.

**Third round (not the final agent).** After finding that the agent couldn't answer the stock question, I changed the agent to try to fix it and ran 21 tests, including the stock question. Only 9 of 21 final answers passed (43%). The stock question still failed, and questions that had always passed, total revenue and highest revenue, now failed in every run. Because the tests caught these regressions, I reverted to the second-round version of the agent, which is the version in this folder, and recorded the stock question as a known limitation. The third-round results are in `test_records/test_results_round3.csv`.

**Manual review.** I also read every final answer myself. One of the 16 answers that passed the grader contained an error the grader didn't detect (see the first limitation below), so 15 of 17 final answers were fully correct on manual review.

## Known limitations

**The agent cannot answer stock questions correctly.** Asked "Which product is running lowest on stock?", the agent adds up stock across all twelve months and reports 4,138 units for Laundry Detergent instead of 60. Stock on hand is an end-of-month snapshot, so that total is meaningless. The product it names is right, but the figure isn't, and the checks don't catch it, because every number really came from a query. My attempted fixes made other questions fail, so this remains a known limitation which I intend to fix in future.

**The evidence check confirms that numbers are real, not that they're attached to the right thing.** In the reworded question 3 test, the final answer said "Vancouver sold the most units of Granola Bars, with 8,203 units." 8,203 is the Granola Bars total across all five stores, not Vancouver's figure. The number passed the check because a query returned it, but the model attributed it to the wrong store, and the grader didn't catch this either.

**The model doesn't always retry a refused chart.** In the one failed test (the reworded question 2), the model's chart was refused because its values were invented. The model then kept writing as if a chart existed instead of calling the chart tool again, so after three rejected answers in a row, the answer was blocked.

**The checks are strict by design.** Numbers the model calculates itself are rejected unless a query returned them, even when the calculation is correct. In question 1, the model correctly added the five store totals to get $227,577.73, but that answer was rejected until it ran a query that returned the total directly. This is safer for reporting, but it means the model sometimes needs extra steps.

**The chart rule depends on wording.** A chart is required only when the question contains one of the listed ranking words (highest, lowest, most, least, best, worst, top, rank, compare, comparison). A comparison question worded without those words would not be required to have a chart.

**No follow-up questions.** Each question starts a fresh conversation with the model, so the agent can't answer a follow-up such as "and what about Surrey?".

**Answers can be slow.** Answers took between about 3 and 46 seconds. The database queries are almost instant; the time goes into the model, which runs locally and writes each response piece by piece. A question answered correctly first time needs one round (about 4 to 5 seconds for the missing data question), while a question that needs corrections takes several rounds (about 35 to 38 seconds for the highest revenue question). The first question after starting Ollama is also slower, while the model loads into memory.

**Repeated runs were identical.** The model runs with temperature 0, and repeating the same question gave the same result every time in my tests. So the three runs of each original question show consistency, and the reworded questions are the better test of how the agent handles different phrasing.

## Tools used

Python 3.14 (Anaconda), SQLite, pandas, Matplotlib, Ollama 0.34, the `ollama` Python library 0.6, and Qwen 2.5 7B. All are free and run locally.

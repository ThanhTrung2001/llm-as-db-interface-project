#!/usr/bin/env python3
"""
Text-to-SQL inference on BIRD dev set using Gemini (google-genai SDK).

Reuses the prompt-building logic from gpt_request.py (schema dump + question +
external knowledge), but replaces the old openai.Completion.create() call with
Gemini's chat-style generate_content().

Usage:
  python gemini_request.py --limit 3   # smoke test on first 3 questions
  python gemini_request.py             # full dev set
"""
import argparse
import json
import os
import re
import sqlite3
import time
from typing import Dict, List, Optional

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


# ---- prompt building (copied from gpt_request.py — unchanged logic) ----

def nice_look_table(column_names: list, values: list) -> str:
    widths = [max(len(str(value[i])) for value in values + [column_names]) for i in range(len(column_names))]
    header = ''.join(f'{column.rjust(width)} ' for column, width in zip(column_names, widths))
    rows = "\n".join(
        ''.join(f'{str(v).rjust(width)} ' for v, width in zip(value, widths))
        for value in values
    )
    return header + '\n' + rows


def generate_schema_prompt(db_path: str, num_rows: Optional[int] = None) -> str:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    schemas: Dict[str, str] = {}
    for table in tables:
        table_name = table[0]
        if table_name == 'sqlite_sequence':
            continue
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(table_name))
        schemas[table_name] = cursor.fetchone()[0]
    conn.close()
    return "\n\n".join(schemas.values())


def generate_comment_prompt(question: str, knowledge: Optional[str] = None) -> str:
    pattern_prompt_no_kg = "-- Using valid SQLite, answer the following questions for the tables provided above."
    pattern_prompt_kg = "-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above."
    question_prompt = "-- {}".format(question)

    if not knowledge:
        return pattern_prompt_no_kg + '\n' + question_prompt

    knowledge_prompt = "-- External Knowledge: {}".format(knowledge)
    return knowledge_prompt + '\n' + pattern_prompt_kg + '\n' + question_prompt


def generate_combined_prompts_one(db_path: str, question: str, knowledge: Optional[str] = None) -> str:
    schema_prompt = generate_schema_prompt(db_path)
    comment_prompt = generate_comment_prompt(question, knowledge)
    instruction = "\nRespond with the final SQLite query only, inside a ```sql code block. Do not add any explanation."
    return schema_prompt + '\n\n' + comment_prompt + instruction


# ---- the part that changes: calling Gemini instead of openai.Completion ----

RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")


def call_gemini(client, model: str, prompt: str, max_retries: int = 5) -> str:
    from google.genai import types
    config = types.GenerateContentConfig(temperature=0, max_output_tokens=4096)

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            return response.text or ""
        except Exception as e:
            msg = str(e)
            is_rate_limit = '429' in msg or 'RESOURCE_EXHAUSTED' in msg
            if not is_rate_limit or attempt == max_retries:
                raise
            match = RETRY_DELAY_RE.search(msg)
            wait_seconds = float(match.group(1)) + 1 if match else 15.0
            print(f'  [rate limit] waiting {wait_seconds:.0f}s before retry {attempt + 1}/{max_retries}')
            time.sleep(wait_seconds)

    return ""  # unreachable


SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
OPEN_FENCE_RE = re.compile(r"```(?:sql)?\s*", re.IGNORECASE)


def extract_sql(raw_text: str) -> str:
    match = SQL_FENCE_RE.search(raw_text)
    if match:
        text = match.group(1)
    else:
        # no closing fence (response got cut off) — strip a leading ```sql if present
        text = OPEN_FENCE_RE.sub('', raw_text, count=1)
    text = text.strip().split(';')[0].strip()
    return text or "SELECT"


# ---- driving loop (same shape as collect_response_from_gpt in gpt_request.py) ----

def decouple_question_schema(datasets, db_root_path: str):
    question_list, db_path_list, knowledge_list = [], [], []
    for data in datasets:
        question_list.append(data['question'])
        db_path_list.append(os.path.join(db_root_path, data['db_id'], data['db_id'] + '.sqlite'))
        knowledge_list.append(data['evidence'])
    return question_list, db_path_list, knowledge_list


def collect_response(client, model: str, db_path_list: List[str], question_list: List[str],
                      knowledge_list: List[str]) -> List[str]:
    response_list = []
    for i, question in enumerate(tqdm(question_list)):
        prompt = generate_combined_prompts_one(db_path_list[i], question, knowledge_list[i])
        try:
            raw = call_gemini(client, model, prompt)
            sql = extract_sql(raw)
        except Exception as e:
            print(f'  [warn] question {i}: {e}')
            sql = "SELECT"

        db_id = os.path.basename(db_path_list[i]).replace('.sqlite', '')
        response_list.append(sql + '\t----- bird -----\t' + db_id)
    return response_list


def generate_sql_file(sql_lst: List[str], output_path: str) -> None:
    result = {i: sql for i, sql in enumerate(sql_lst)}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default='gemini-2.5-flash')
    parser.add_argument('--eval_path', type=str, default='./data/dev.json')
    parser.add_argument('--db_root_path', type=str, default='./data/dev_databases/')
    parser.add_argument('--data_output_path', type=str, default='./exp_result/gemini_output/predict_dev.json')
    parser.add_argument('--limit', type=int, default=None, help='only run the first N questions (smoke test)')
    args = parser.parse_args()

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise SystemExit('GEMINI_API_KEY not set in .env')

    eval_data = json.load(open(args.eval_path, 'r'))
    if args.limit:
        eval_data = eval_data[:args.limit]

    question_list, db_path_list, knowledge_list = decouple_question_schema(eval_data, args.db_root_path)

    from google import genai
    client = genai.Client(api_key=api_key)

    responses = collect_response(client, args.model, db_path_list, question_list, knowledge_list)
    generate_sql_file(responses, args.data_output_path)

    print(f'Done. {len(responses)} predictions -> {args.data_output_path}')

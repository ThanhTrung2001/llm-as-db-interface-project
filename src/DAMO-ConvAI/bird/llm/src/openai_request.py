#!/usr/bin/env python3
"""
Text-to-SQL inference on BIRD dev set using the official OpenAI API.

Same prompt-building logic as gemini_request.py / groq_request.py, calling
OpenAI's Chat Completions API.

Usage:
  python openai_request.py --model gpt-4o-mini --limit 3
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


# ---- prompt building (same as gemini_request.py / groq_request.py) ----

def generate_schema_prompt(db_path: str) -> str:
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


# ---- the part that changes: calling OpenAI instead of Gemini/Groq/Ollama ----

RETRY_DELAY_RE = re.compile(r"retry.*?(\d+(?:\.\d+)?)s", re.IGNORECASE)


def call_openai(client, model: str, prompt: str, max_retries: int = 5) -> str:
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=512,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            msg = str(e)
            is_rate_limit = '429' in msg or 'rate_limit' in msg.lower()
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
        text = OPEN_FENCE_RE.sub('', raw_text, count=1)
    text = text.strip().split(';')[0].strip()
    return text or "SELECT"


# ---- driving loop (same shape as gemini_request.py / groq_request.py) ----

def decouple_question_schema(datasets, db_root_path: str):
    question_list, db_path_list, knowledge_list = [], [], []
    for data in datasets:
        question_list.append(data['question'])
        db_path_list.append(os.path.join(db_root_path, data['db_id'], data['db_id'] + '.sqlite'))
        knowledge_list.append(data['evidence'])
    return question_list, db_path_list, knowledge_list


def collect_response(client, model: str, db_path_list: List[str], question_list: List[str],
                      knowledge_list: List[str], output_path: Optional[str] = None,
                      checkpoint_every: int = 50) -> List[str]:
    response_list = []
    for i, question in enumerate(tqdm(question_list)):
        try:
            prompt = generate_combined_prompts_one(db_path_list[i], question, knowledge_list[i])
            raw = call_openai(client, model, prompt)
            sql = extract_sql(raw)
        except Exception as e:
            print(f'  [warn] question {i}: {e}')
            sql = "SELECT"

        db_id = os.path.basename(db_path_list[i]).replace('.sqlite', '')
        response_list.append(sql + '\t----- bird -----\t' + db_id)

        if output_path and (i + 1) % checkpoint_every == 0:
            generate_sql_file(response_list, output_path)
    return response_list


def generate_sql_file(sql_lst: List[str], output_path: str) -> None:
    result = {i: sql for i, sql in enumerate(sql_lst)}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default='gpt-4o-mini')
    parser.add_argument('--eval_path', type=str, default='./data/dev.json')
    parser.add_argument('--db_root_path', type=str, default='./data/dev_databases/')
    parser.add_argument('--data_output_path', type=str, default='./exp_result/openai_output/predict_dev.json')
    parser.add_argument('--limit', type=int, default=None, help='only run the first N questions (smoke test)')
    parser.add_argument('--no_knowledge', action='store_true', help='run w/o external knowledge (evidence)')
    args = parser.parse_args()

    api_key = os.environ.get('OPEN_AI_KEY') or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise SystemExit('OPEN_AI_KEY not set in .env')

    eval_data = json.load(open(args.eval_path, 'r'))
    if args.limit:
        eval_data = eval_data[:args.limit]

    question_list, db_path_list, knowledge_list = decouple_question_schema(eval_data, args.db_root_path)
    if args.no_knowledge:
        knowledge_list = [None] * len(knowledge_list)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    responses = collect_response(client, args.model, db_path_list, question_list, knowledge_list,
                                  output_path=args.data_output_path, checkpoint_every=50)
    generate_sql_file(responses, args.data_output_path)

    print(f'Done. {len(responses)} predictions -> {args.data_output_path}')

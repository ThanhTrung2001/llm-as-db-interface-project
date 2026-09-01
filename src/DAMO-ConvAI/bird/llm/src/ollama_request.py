#!/usr/bin/env python3
"""
Text-to-SQL inference on BIRD dev set using a local Ollama model
(no API key, no rate limit — runs on your own machine's CPU/GPU).

Same prompt-building logic as gemini_request.py / groq_request.py, calling
Ollama's local REST API (http://localhost:11434) instead of a cloud provider.

Prereq: `ollama serve` running locally, model already pulled (`ollama pull <model>`).

Usage:
  python ollama_request.py --model qwen2.5-coder:7b-instruct --limit 3
  python ollama_request.py --model llama3.1:8b
"""
import argparse
import json
import os
import re
import sqlite3
import time
from typing import Dict, List, Optional

import requests
from tqdm import tqdm

OLLAMA_URL = "http://localhost:11434/api/chat"


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


# ---- the part that changes: calling local Ollama instead of a cloud API ----

def call_ollama(model: str, prompt: str, max_retries: int = 3, timeout: int = 120) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0},
    }
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"] or ""
        except Exception as e:
            if attempt == max_retries:
                raise
            print(f'  [retry] {e} -> waiting 3s (attempt {attempt + 1}/{max_retries})')
            time.sleep(3)
    return ""  # unreachable


SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
OPEN_FENCE_RE = re.compile(r"```(?:sql)?\s*", re.IGNORECASE)
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def extract_sql(raw_text: str) -> str:
    raw_text = THINK_TAG_RE.sub('', raw_text)  # some local models emit <think>...</think> reasoning traces
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


def collect_response(model: str, db_path_list: List[str], question_list: List[str],
                      knowledge_list: List[str]) -> List[str]:
    response_list = []
    for i, question in enumerate(tqdm(question_list)):
        prompt = generate_combined_prompts_one(db_path_list[i], question, knowledge_list[i])
        try:
            raw = call_ollama(model, prompt)
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
    parser.add_argument('--model', type=str, default='qwen2.5-coder:7b-instruct')
    parser.add_argument('--eval_path', type=str, default='./data/dev.json')
    parser.add_argument('--db_root_path', type=str, default='./data/dev_databases/')
    parser.add_argument('--data_output_path', type=str, default='./exp_result/ollama_output/predict_dev.json')
    parser.add_argument('--limit', type=int, default=None, help='only run the first N questions (smoke test)')
    args = parser.parse_args()

    eval_data = json.load(open(args.eval_path, 'r'))
    if args.limit:
        eval_data = eval_data[:args.limit]

    question_list, db_path_list, knowledge_list = decouple_question_schema(eval_data, args.db_root_path)

    responses = collect_response(args.model, db_path_list, question_list, knowledge_list)
    generate_sql_file(responses, args.data_output_path)

    print(f'Done. {len(responses)} predictions -> {args.data_output_path}')

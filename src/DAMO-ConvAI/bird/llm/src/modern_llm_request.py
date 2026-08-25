#!/usr/bin/env python3
"""
Text-to-SQL inference on the BIRD dev set using current-generation chat LLM APIs
(Gemini via google-genai, Groq-hosted open models) instead of the legacy
OpenAI Completion engines (code-davinci-002 / text-davinci-003) used in gpt_request.py.

Usage:
  python modern_llm_request.py --provider gemini --model gemini-2.5-flash --use_knowledge True
  python modern_llm_request.py --provider groq --model llama-3.3-70b-versatile --use_knowledge True
"""
import argparse
import json
import os
import re
import sqlite3
import time
from typing import Dict, List, Optional

from tqdm import tqdm

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def new_directory(path: str) -> None:
    if path and not os.path.exists(path):
        os.makedirs(path)


def nice_look_table(column_names: list, values: list) -> str:
    widths = [max(len(str(value[i])) for value in values + [column_names]) for i in range(len(column_names))]
    header = ''.join(f'{column.rjust(width)} ' for column, width in zip(column_names, widths))
    rows = "\n".join(
        ''.join(f'{str(v).rjust(width)} ' for v, width in zip(value, widths))
        for value in values
    )
    return header + '\n' + rows


def generate_schema_prompt(db_path: str, num_rows: Optional[int] = None) -> str:
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    schemas: Dict[str, str] = {}
    for table in tables:
        table_name = table[0]
        if table_name == 'sqlite_sequence':
            continue
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(table_name))
        create_prompt = cursor.fetchone()[0]
        schemas[table_name] = create_prompt
        if num_rows:
            cur_table = table_name
            if cur_table in ('order', 'by', 'group'):
                cur_table = "`{}`".format(cur_table)
            try:
                cursor.execute("SELECT * FROM {} LIMIT {}".format(cur_table, num_rows))
                column_names = [d[0] for d in cursor.description]
                values = cursor.fetchall()
                rows_prompt = nice_look_table(column_names=column_names, values=values)
                verbose_prompt = "/* \n {} example rows: \n SELECT * FROM {} LIMIT {}; \n {} \n */".format(
                    num_rows, cur_table, num_rows, rows_prompt)
                schemas[table_name] = "{} \n {}".format(create_prompt, verbose_prompt)
            except sqlite3.OperationalError:
                pass
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
    schema_prompt = generate_schema_prompt(db_path, num_rows=None)
    comment_prompt = generate_comment_prompt(question, knowledge)
    instruction = (
        "\nRespond with the final SQLite query only, inside a ```sql code block. "
        "Do not add any explanation."
    )
    return schema_prompt + '\n\n' + comment_prompt + instruction


SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(raw_text: str) -> str:
    """Pull a single SQL statement out of a chat-model response."""
    if not raw_text:
        return "SELECT"
    match = SQL_FENCE_RE.search(raw_text)
    text = match.group(1) if match else raw_text
    text = text.strip()
    if text.lower().startswith('sql'):
        text = text[3:].strip()
    # keep only the first statement
    text = text.split(';')[0].strip()
    if not text:
        return "SELECT"
    return text


def connect_gemini(client, model: str, prompt: str, max_tokens: int, temperature: float) -> str:
    from google.genai import types
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text or ""
    except Exception as e:
        return 'error:{}'.format(e)


def connect_groq(client, model: str, prompt: str, max_tokens: int, temperature: float) -> str:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return 'error:{}'.format(e)


def build_client(provider: str, api_key: str):
    if provider == 'gemini':
        from google import genai
        return genai.Client(api_key=api_key)
    if provider == 'groq':
        from groq import Groq
        return Groq(api_key=api_key)
    raise ValueError('Unknown provider: {}'.format(provider))


def collect_response(provider: str, client, model: str, db_path_list: List[str], question_list: List[str],
                      knowledge_list: Optional[List[str]] = None, sleep_seconds: float = 0.0) -> List[str]:
    response_list = []
    for i, question in enumerate(tqdm(question_list)):
        knowledge = knowledge_list[i] if knowledge_list else None
        cur_prompt = generate_combined_prompts_one(db_path=db_path_list[i], question=question, knowledge=knowledge)

        if provider == 'gemini':
            raw = connect_gemini(client, model, cur_prompt, max_tokens=512, temperature=0)
        else:
            raw = connect_groq(client, model, cur_prompt, max_tokens=512, temperature=0)

        if raw.startswith('error:'):
            sql = "SELECT"
            print('  [warn] question {}: {}'.format(i, raw))
        else:
            sql = extract_sql(raw)

        db_id = db_path_list[i].split('/')[-1].split('\\')[-1].split('.sqlite')[0]
        response_list.append(sql + '\t----- bird -----\t' + db_id)

        if sleep_seconds:
            time.sleep(sleep_seconds)

    return response_list


def decouple_question_schema(datasets, db_root_path: str):
    question_list, db_path_list, knowledge_list = [], [], []
    for data in datasets:
        question_list.append(data['question'])
        db_path_list.append(os.path.join(db_root_path, data['db_id'], data['db_id'] + '.sqlite'))
        knowledge_list.append(data['evidence'])
    return question_list, db_path_list, knowledge_list


def generate_sql_file(sql_lst: List[str], output_path: Optional[str] = None) -> dict:
    result = {i: sql for i, sql in enumerate(sql_lst)}
    if output_path:
        new_directory(os.path.dirname(output_path))
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=4)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', type=str, required=True, choices=['gemini', 'groq'])
    parser.add_argument('--model', type=str, required=True,
                         help='e.g. gemini-2.5-flash / gemini-2.5-pro / llama-3.3-70b-versatile / openai/gpt-oss-120b')
    parser.add_argument('--api_key', type=str, default=None, help='Falls back to GEMINI_API_KEY / FREE_API_KEY env var')
    parser.add_argument('--eval_path', type=str, default='./data/dev.json')
    parser.add_argument('--db_root_path', type=str, default='./data/dev_databases/')
    parser.add_argument('--mode', type=str, default='dev')
    parser.add_argument('--use_knowledge', type=str, default='True')
    parser.add_argument('--data_output_path', type=str, required=True)
    parser.add_argument('--limit', type=int, default=None, help='Only run on the first N questions (for smoke tests)')
    parser.add_argument('--sleep_seconds', type=float, default=0.0, help='Delay between requests to respect free-tier rate limits')
    args = parser.parse_args()

    api_key = args.api_key
    if not api_key:
        env_var = 'GEMINI_API_KEY' if args.provider == 'gemini' else 'FREE_API_KEY'
        api_key = os.environ.get(env_var)
    if not api_key:
        raise SystemExit('No API key provided. Pass --api_key or set it in .env.')

    eval_data = json.load(open(args.eval_path, 'r'))
    if args.limit:
        eval_data = eval_data[:args.limit]

    question_list, db_path_list, knowledge_list = decouple_question_schema(eval_data, args.db_root_path)
    assert len(question_list) == len(db_path_list) == len(knowledge_list)

    client = build_client(args.provider, api_key)

    responses = collect_response(
        provider=args.provider,
        client=client,
        model=args.model,
        db_path_list=db_path_list,
        question_list=question_list,
        knowledge_list=knowledge_list if args.use_knowledge == 'True' else None,
        sleep_seconds=args.sleep_seconds,
    )

    output_name = os.path.join(args.data_output_path, 'predict_{}.json'.format(args.mode))
    generate_sql_file(sql_lst=responses, output_path=output_name)

    print('Done. provider={} model={} use_knowledge={} -> {}'.format(
        args.provider, args.model, args.use_knowledge, output_name))

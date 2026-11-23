"""Evaluate local scientific answers against retrieved source records."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import subprocess


TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]{1,}")
NUMBER = re.compile(r"(?<![\w])(?:\d+(?:\.\d+)?)(?![\w])")
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "source": {"type": "string"}},
    "required": ["answer", "source"],
    "additionalProperties": False,
}
SYSTEM = (
    "Answer the question with one short factual claim from the supplied records. "
    "Return JSON with answer and source. Use exactly one record ID for source. "
    'When no record answers the question, return {"answer":"ABSTAIN","source":""}. '
    "Use the exact source wording or numerical value where practical."
)


def runtime_sources(qc, regression, pathway):
    return [
        {
            "id": "QC_RUN",
            "reference": "qc.json",
            "section": "Observed cohort",
            "text": f"The final modeling cohort contains {qc['modeling_rows']} cancer cell lines.",
        },
        {
            "id": "ML_RUN",
            "reference": "model.json",
            "section": "Observed grouped cross-validation",
            "text": (
                f"Held-out ridge MAE was {regression['mae']['ridge']:.4f}. "
                f"The training-median baseline MAE was {regression['mae']['training_median']:.4f}."
            ),
        },
        {
            "id": "SIM_RUN",
            "reference": "pathway.json",
            "section": "Simulated scenarios",
            "text": (
                "For the illustrative reference scenario, the steady state lactate pool was "
                f"{pathway['scenarios']['reference']['steady_state']:g} in relative units."
            ),
        },
    ]


def retrieve(db, question, limit=3):
    stop = {"a", "an", "and", "can", "did", "does", "for", "how", "in", "is", "of", "the", "to", "was", "were", "what", "which", "with"}
    words = dict.fromkeys(word.lower() for word in TOKEN.findall(question) if word.lower() not in stop)
    if not words:
        return []
    match = " OR ".join(f'"{word}"' for word in words)
    return db.execute(
        "SELECT id, text FROM sources WHERE sources MATCH ? ORDER BY rank, id LIMIT ?",
        (match, limit),
    ).fetchall()


def generate(executable, weights, question, records):
    context = "\n".join(f"[{source}] {body}" for source, body in records)
    prompt = (
        f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\nRecords:\n{context}\nQuestion: {question}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    run = subprocess.run(
        [
            str(executable), "-m", str(weights), "-ngl", "0", "-dev", "none",
            "--threads", "3", "--ctx-size", "2048", "--temp", "0", "--seed", "419",
            "-no-cnv", "--no-display-prompt", "--no-warmup", "--simple-io", "-n", "80",
            "--json-schema", json.dumps(SCHEMA), "-p", prompt,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if run.returncode:
        raise RuntimeError(f"Inference failed: {run.stderr[-2000:]}")
    raw = run.stdout.strip()
    try:
        result, _ = json.JSONDecoder().raw_decode(raw)
        if set(result) == {"answer", "source"} and all(isinstance(v, str) for v in result.values()):
            return result["answer"].strip(), result["source"].strip(), True
    except (TypeError, ValueError):
        pass
    return raw, "", False


def checks(question, records, answer, citation, valid_json):
    retrieved = dict(records)
    abstained = valid_json and answer == "ABSTAIN" and not citation
    valid_citation = valid_json and bool(citation) and citation in retrieved and answer != "ABSTAIN"
    supported_number = valid_citation and set(NUMBER.findall(answer)) <= set(NUMBER.findall(retrieved[citation]))
    return {
        "id": question["id"],
        "answerable": bool(question["sources"]),
        "retrieved": list(retrieved),
        "answer": answer,
        "citation": citation,
        "valid_json": valid_json,
        "abstained": abstained,
        "valid_citation": valid_citation,
        "numbers_in_cited_record": supported_number,
        "retrieval_hit": bool(set(question["sources"]) & retrieved.keys()),
        "expected_citation": valid_citation and citation in question["sources"],
    }


def benchmark(executable, weights, sources, questions):
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE sources USING fts5(id UNINDEXED, text, tokenize='porter unicode61')")
        db.executemany("INSERT INTO sources VALUES (?, ?)", [(s["id"], s["text"]) for s in sources])
        results = []
        for question in questions:
            records = retrieve(db, question["question"])
            result = checks(question, records, *generate(executable, weights, question["question"], records))
            results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("sources", "questions", "weights", "executable", "qc", "regression", "pathway"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text())
    questions = json.loads(args.questions.read_text())
    records = [json.loads(path.read_text()) for path in (args.qc, args.regression, args.pathway)]
    sources.extend(runtime_sources(*records))
    outcomes = benchmark(args.executable.resolve(), args.weights.resolve(), sources, questions)
    answerable = [r for r in outcomes if r["answerable"]]
    unanswerable = [r for r in outcomes if not r["answerable"]]
    claims = [r for r in outcomes if not r["abstained"]]
    metrics = {
        "questions": len(outcomes),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "retrieval_hits_at_3": sum(r["retrieval_hit"] for r in answerable),
        "rag_expected_citations": sum(r["expected_citation"] for r in answerable),
        "unanswerable_abstentions": sum(r["abstained"] for r in unanswerable),
        "answerable_abstentions": sum(r["abstained"] for r in answerable),
        "malformed_responses": sum(not r["valid_json"] for r in outcomes),
        "claims_or_malformed_responses": len(claims),
        "claims_passing_citation_and_number_checks": sum(r["numbers_in_cited_record"] for r in claims),
    }
    Path("answers.jsonl").write_text("".join(json.dumps(record) + "\n" for record in outcomes))
    Path("evidence.json").write_text(json.dumps(metrics, indent=2) + "\n")
    Path("retained_sources.json").write_text(json.dumps(sources, indent=2) + "\n")


if __name__ == "__main__":
    main()

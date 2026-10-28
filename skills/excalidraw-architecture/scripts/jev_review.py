#!/usr/bin/env python3
"""Review a design doc with TypeSafe Jev, one request per lens; exit 0 approve, 1 revise, 2 error.
Needs TYPESAFE_API_KEY. Send design text only, never personal or customer data."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
YES, NO = 0.7, 0.3


def ask(model, state, questions):
	payload = {"model": model, "state": state, "questions": questions}
	request = urllib.request.Request(
		ENDPOINT,
		data=json.dumps(payload).encode(),
		headers={
			"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}",
			"Content-Type": "application/json",
		},
	)
	with urllib.request.urlopen(request, timeout=180) as response:
		return json.load(response)


def outcome(probability, expect):
	"""'pass', 'fail' or 'unsure' for a noul whose expected answer is `expect`."""
	if NO < probability < YES:
		return "unsure"
	return "pass" if (probability >= YES) == expect else "fail"


def review_lens(model, state, questions):
	sent = {name: {k: v for k, v in q.items() if k != "expect"} for name, q in questions.items()}
	reply = ask(model, state, sent)
	rows = []
	for name, question in questions.items():
		answer = reply["answers"][name]
		if answer["type"] != "noul":
			rows.append((name, answer.get("score"), "info"))
			continue
		rows.append((name, answer["noul"], outcome(answer["noul"], question.get("expect", True))))
	return rows, reply.get("usage", {})


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("design")
	parser.add_argument("questions")
	parser.add_argument("--out")
	parser.add_argument("--model", default="jev-latest")
	args = parser.parse_args()
	if not os.environ.get("TYPESAFE_API_KEY"):
		print("TYPESAFE_API_KEY is not set", file=sys.stderr)
		return 2

	state = open(args.design).read()
	lenses = json.load(open(args.questions))
	result, all_approve = {}, True
	try:
		for lens, questions in lenses.items():
			rows, usage = review_lens(args.model, state, questions)
			verdict = "approve" if all(o in ("pass", "info") for _, _, o in rows) else "revise"
			all_approve &= verdict == "approve"
			result[lens] = {"verdict": verdict, "usage": usage, "answers": rows}
	except (urllib.error.URLError, KeyError, ValueError) as error:
		print(f"Jev request failed: {error}", file=sys.stderr)
		return 2

	for lens, data in result.items():
		print(f"\n{lens}: {data['verdict']}  ({data['usage'].get('input_tokens', '?')} input tokens)")
		for name, value, verdict in data["answers"]:
			shown = f"{value:.2f}" if isinstance(value, (int, float)) else str(value)
			print(f"  {verdict:7} {shown:>5}  {name}")
	if args.out:
		json.dump(result, open(args.out, "w"), indent=1)
	return 0 if all_approve else 1


if __name__ == "__main__":
	sys.exit(main())

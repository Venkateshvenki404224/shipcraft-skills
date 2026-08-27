---
name: dsa-conscious-coding
description: Use when designing, implementing, reviewing, or optimizing any app feature so data structures, algorithms, Big O, and real production tradeoffs are considered before code is written.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [dsa, software-development, performance, code-quality, backend]
    related_skills: [writing-plans, test-driven-development, requesting-code-review]
---

# DSA-Conscious Coding

## Overview

Use this skill whenever you build or review application code. The goal is not to force complex DSA everywhere. The goal is to choose simple, correct data structures and algorithms that keep the app fast, readable, and maintainable as data grows.

DSA in real projects means asking:

> If this data becomes 10x, 100x, or 1000x bigger, will this code still survive?

Good app code usually comes from simple choices made early:

- Use a dictionary when you need exact lookup.
- Use a queue when work must be processed in order.
- Use a heap when urgent items must be processed first.
- Use a trie or indexed search when prefix search matters.
- Use graph thinking when records are connected.
- Avoid fetching everything and looping when the database can filter/index.

## When to Use

Use this skill when:

- Writing a new app feature, API, report, job, or dashboard.
- Reviewing code that loops over records, filters data, searches, sorts, or builds summaries.
- Choosing between list, dict, set, queue, heap, tree, graph, or database query.
- Handling Frappe/ERPNext records, background jobs, reports, workflows, document links, or dashboards.
- A feature works on small data but may fail on large data.
- You need to explain the performance or scalability of code.

Do **not** use this to overengineer tiny one-off scripts. Prefer the simplest structure that satisfies the real data size and access pattern.

## Core Rule

Before writing code, answer these five questions:

1. **What data am I storing?**
2. **How will I access it most often?**
3. **Will I search by exact key, prefix, range, priority, order, or connection?**
4. **What is the expected data size now and later?**
5. **Can the database do this better than in-memory Python?**

If you cannot answer these, pause and inspect the real requirement first.

## Quick Decision Table

| Need | Prefer | Why |
|---|---|---|
| Exact lookup by ID/email/name | HashMap / `dict` / DB indexed lookup | Average `O(1)` in memory; fast indexed DB lookup |
| Remove duplicates or membership check | `set` | Average `O(1)` membership |
| Preserve ordered recent items | `list` | Simple, direct index access |
| Process first-created item first | Queue / `deque` | FIFO, `O(1)` append/pop-left |
| Process latest action first | Stack / `list.append/pop` | LIFO, `O(1)` push/pop |
| Process most urgent item first | Heap / Priority Queue | `O(log n)` insert/pop priority item |
| Search sorted data | Binary Search | `O(log n)` if data is sorted |
| Prefix/autocomplete search | Trie or search index | Search by typed prefix, not full scan |
| Parent-child hierarchy | Tree | Categories, workflows, accounts, org charts |
| Connected records/routes/dependencies | Graph | BFS/DFS/path/dependency reasoning |
| Frequent range queries/reports | DB indexes, prefix sums, materialized summaries | Avoid repeated full scans |
| Complex filtering over many records | Database query with filters/indexes | DB should reduce data before Python sees it |

## Frappe/ERPNext Rules

### 1. Do not fetch all records and loop unless data is truly small

Bad:

```python
orders = frappe.get_all("Sales Order", fields=["name", "customer", "status"])

for order in orders:
    if order.customer == customer:
        return order
```

Better:

```python
orders = frappe.get_all(
    "Sales Order",
    filters={"customer": customer},
    fields=["name", "customer", "status"],
)
```

Why:

- Bad code moves filtering into Python.
- Better code lets the database filter and use indexes.

### 2. Use `frappe.db.get_value` for exact document lookup

Good:

```python
status = frappe.db.get_value("Sales Order", sales_order_name, "status")
```

This is like exact-key lookup. Do not load unnecessary fields or scan lists.

### 3. Add indexes when filters become common

If a report/API frequently filters by a field, consider indexing that field in the DocType or migration.

Common indexed fields:

- `name`
- `owner`
- `creation`
- `modified`
- status fields used in dashboards
- foreign keys / Link fields used in reports

Do not blindly index every field. Indexes speed reads but add write/storage cost.

### 4. Use background queues for slow work

If a request sends emails, generates PDFs, syncs APIs, or processes many records, use a background job.

```python
frappe.enqueue(
    "my_app.tasks.process_orders",
    queue="long",
    timeout=1500,
)
```

Do not block the user request for long operations.

## Big O Check Before Finalizing Code

For any loop, ask:

```txt
What is n?
How big can n become?
Is this loop inside another loop?
Can this be converted to dict/set/DB filter?
```

### Common Patterns

#### Bad nested lookup

```python
for order in orders:
    for customer in customers:
        if order.customer == customer.name:
            order.customer_name = customer.customer_name
```

This is usually `O(n * m)`.

Better:

```python
customer_map = {c.name: c.customer_name for c in customers}

for order in orders:
    order.customer_name = customer_map.get(order.customer)
```

This becomes roughly `O(n + m)`.

#### Bad repeated list membership

```python
if user_email in email_list:
    print("exists")
```

If repeated many times, convert to set:

```python
email_set = set(email_list)

if user_email in email_set:
    print("exists")
```

#### Bad sorting inside loop

```python
for item in items:
    scores.sort()
```

Sorting repeatedly is expensive. Sort once outside the loop unless the data truly changes every time.

## Practical Coding Workflow

1. **Understand access pattern**
   - Exact lookup?
   - Prefix search?
   - Sorted search?
   - Priority processing?
   - Relationship traversal?

2. **Choose the simplest fitting structure**
   - `list` for ordered small collections.
   - `dict` for key-value lookup.
   - `set` for membership/deduplication.
   - `deque` for FIFO queues.
   - `heapq` for priority queues.
   - DB filter/index for persistent large data.

3. **Write clear baseline code first**
   - Make it correct.
   - Add tests.
   - Only optimize where data size/access pattern needs it.

4. **Add Explain Mode when teaching or debugging**
   - Return steps checked.
   - Return Big O label.
   - Return trace messages.

5. **Verify with realistic data**
   - Test with 10 records and 500+ records.
   - For production-like features, test with enough data to expose slow loops.

## App Feature Checklist

Before marking a feature done, verify:

- [ ] No unnecessary `get_all` without filters for large DocTypes.
- [ ] No nested loops over large lists unless justified.
- [ ] Exact lookups use dict/set or DB indexed lookup.
- [ ] Prefix search has a proper strategy: Trie/search index/DB search.
- [ ] Priority work uses heap/priority queue thinking.
- [ ] Background work uses queue/worker pattern.
- [ ] Relationship traversal tracks `visited` to avoid cycles.
- [ ] Sorting is not repeated unnecessarily.
- [ ] Tests cover small, empty, duplicate, and large-ish data cases.
- [ ] Code comments explain the DSA choice where it is not obvious.

## DSA Is Not Always Manual DSA

In real apps, the best DSA choice is often:

```txt
Let the database do it.
```

Examples:

- Use SQL filtering instead of Python filtering.
- Use DB indexes instead of building manual BSTs for persistent records.
- Use Redis/queue workers instead of custom in-memory queues for production jobs.
- Use full-text/search engines for serious search.

Manual DSA is useful for:

- In-memory transformations.
- Small local indexes.
- Algorithms inside one request/job.
- Learning, testing, and explaining performance.
- Cases where database/query tools are not enough.

## Common Pitfalls

1. **Using lists for everything.** Lists are simple, but repeated search by value is `O(n)`. Use dict/set when lookup matters.

2. **Building clever DSA too early.** If the dataset is tiny and will stay tiny, simple code is better.

3. **Ignoring database indexes.** In Frappe apps, DB filtering and indexing are often more important than Python data structures.

4. **Nested loops hidden inside helpers.** A helper function inside a loop may create accidental `O(n²)` behavior.

5. **Forgetting cycles in graphs.** Always track `visited` in graph traversal unless the graph is guaranteed acyclic.

6. **Using `list.pop(0)` as a queue.** Use `collections.deque` for FIFO queues.

7. **Sorting repeatedly.** Sorting inside loops can quietly become a performance killer.

8. **Optimizing without tests.** Performance improvements are useless if behavior changes. Add tests first.

## Verification Checklist

- [ ] Data access pattern is identified.
- [ ] Chosen structure/algorithm matches the access pattern.
- [ ] Big O is understood and documented when relevant.
- [ ] Frappe/database work is pushed into filters/indexes where possible.
- [ ] Code avoids unnecessary full scans and nested loops.
- [ ] Edge cases are tested: empty data, missing keys, duplicates, large-ish data.
- [ ] If performance matters, compare baseline vs optimized behavior.
- [ ] The final implementation remains readable and maintainable.

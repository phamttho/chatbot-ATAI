# Failure analysis

34 failures among 3000 measured requests.

These categories describe saved traces; no prompts, cases, gold answers, or outputs were changed.

| Observed failure | Cases |
|---|---:|
| entity selection rejected | 7 |
| wrong relation | 6 |
| wrong relation direction | 6 |
| wrong entity | 5 |
| clarification instead of answer | 4 |
| unsupported instead of answer | 4 |
| processing error | 2 |

Representative examples:

- D0369 (clarification instead of answer): What derivative works of the film "Charlie's Angels" are recorded in the graph? Expected: Charlie's Angels. Observed: clarification.
- D0714 (entity selection rejected): How many distinct user tags are recorded for the film "A Farewell to Arms" released in 1932? Expected: 1. Observed: error.
- D2687 (processing error): Where was the film "Batman" released in 1966 filmed? Expected: California. Observed: error.
- D0001 (unsupported instead of answer): Who directed the film "&ME"? Expected: Norbert ter Hall. Observed: unsupported_query.
- D0352 (wrong entity): What derivative works of the film "Cat People" released in 1942 are recorded in the graph? Expected: Cat People. Observed: Cat People.
- D0774 (wrong relation): Where was the film "A Man Called Ove" filmed? Expected: Mallorca. Observed: Spain.
- D0342 (wrong relation direction): What derivative works of the film "Carrie" released in 1976 are recorded in the graph? Expected: Scarrie! The Musical. Observed: Carrie.

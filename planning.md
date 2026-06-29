# Provenance Guard — Planning

## 1. Detection Signals

For this project, I am using two different signals instead of relying on only one detector. The goal is not to prove authorship perfectly, because that is not realistic. The goal is to make a reasonable judgment, show uncertainty honestly, and give creators a way to appeal if the system gets it wrong.

### Signal 1: LLM classification with Groq

The first signal uses Groq with `llama-3.3-70b-versatile`.

The submitted text is sent to the model with a prompt that asks whether the writing reads more like AI generated text or human written text. The model returns a structured JSON response like this:

```json
{
  "ai_probability": 0.0,
  "reasoning": "Short explanation of the judgment"
}
```

The main output I use is:

```text
llm_ai_prob
```

This is a number between `0` and `1`.

A score closer to `1` means the LLM thinks the text is more likely AI generated. A score closer to `0` means it thinks the text is more likely human written.

This signal is helpful because it can look at the overall style and meaning of the writing. It can notice patterns like very generic wording, overly polished structure, repeated hedging, or phrases that often show up in AI generated text.

The weakness is that the LLM still does not actually know who wrote the text. It is judging patterns. That means it can be fooled by AI text that has been edited by a human, and it can also be unfair to real human writers who have a more formal or unusual style. This is especially important for non native English speakers, because their writing may look different from what the model expects.

### Signal 2: Stylometric heuristics

The second signal is a Python based stylometric analyzer.

This signal does not understand the meaning of the text. Instead, it measures writing structure.

It uses three metrics:

| Metric                   | What it measures                                               |
| ------------------------ | -------------------------------------------------------------- |
| Sentence length variance | Whether the sentences are all similar in length or more varied |
| Type token ratio         | How much vocabulary variety the text has                       |
| Punctuation density      | How much punctuation appears compared to the total text length |

These metrics are combined into:

```text
stylometric_ai_prob
```

This is also a number between `0` and `1`.

The reason I chose this signal is that AI generated text often has a very even rhythm. The sentences can feel smooth and balanced in a way that is different from casual human writing. Human writing is often more uneven, especially when someone writes naturally.

The weakness is that this signal can be unreliable for short submissions. If someone only submits one or two sentences, there is not enough text to measure sentence variance in a meaningful way. It can also be wrong for formal human writing, like legal writing, technical documentation, or academic paragraphs, because those styles are supposed to be controlled and consistent.

### Combining the two signals

The final score is calculated like this:

```python
confidence = 0.65 * llm_ai_prob + 0.35 * stylometric_ai_prob
```

I am weighting the LLM signal more because it can understand tone and meaning, while the stylometric signal only looks at structure. At the same time, I still want the stylometric signal to matter because it gives the system a second opinion that is independent from the LLM.

The final `confidence` score always means:

```text
probability that the text is AI generated
```

## 2. Uncertainty Representation

The system does not force every result into only AI or human. That would be too risky, especially because false positives can harm real creators.

The final confidence score is between `0` and `1`.

```text
0.0 = very likely human written
1.0 = very likely AI generated
```

The thresholds are:

| Confidence range           | Attribution    |
| -------------------------- | -------------- |
| `confidence >= 0.75`       | `likely_ai`    |
| `confidence <= 0.25`       | `likely_human` |
| `0.25 < confidence < 0.75` | `uncertain`    |

A score like `0.60` means the signals lean toward AI, but not strongly enough to call it likely AI. In that case, the system should return `uncertain`.

I made the uncertain range wide on purpose. On a creative platform, accusing a real person of using AI is more serious than missing some AI generated content. Because of that, the system should be cautious and should only show a high confidence AI label when the score is clearly high.

The system is designed to be honest about uncertainty instead of pretending the detector is perfect.

## 3. Transparency Label Variants

The transparency label is what a reader would see after the system analyzes a piece of content.

The label should be understandable to a normal user. It should not just show a number without context.

These are the three exact label variants I plan to use.

| Variant               | Exact label text                                                                                                                                                                                                     |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| High confidence AI    | `"This content shows strong signals of AI generation. Our system is {confidence}% confident this was AI-generated, based on language-model and writing-style analysis. The creator can appeal this classification."` |
| High confidence human | `"This content shows strong signals of human authorship. Our system is {100-confidence}% confident this was written by a person, based on language-model and writing-style analysis."`                               |
| Uncertain             | `"We can't confidently determine whether this content is AI-generated or human-written. Our analysis is inconclusive ({confidence}% AI-likelihood). Treat this attribution as provisional."`                         |

`{confidence}` will be shown as a rounded percentage.

For example, if the final score is `0.82`, the AI label would show `82%`.

If the final score is `0.18`, the human label would show `82%` confident it was written by a person, because `100 - 18 = 82`.

## 4. Appeals Workflow

Creators need a way to challenge the system if they think the classification is wrong.

For this project, any creator can submit an appeal using:

```text
POST /appeal
```

The request should include:

```json
{
  "content_id": "the original content id",
  "creator_reasoning": "why the creator believes the classification is wrong"
}
```

When the system receives an appeal, it will:

1. Look up the original submission by `content_id`
2. Change the content status to `"under_review"`
3. Add a new audit log entry with the appeal details
4. Keep the original classification, confidence score, and signal breakdown available for review

The system will not automatically reclassify the text after an appeal. I chose this because the appeal should be reviewed by a person. If the system already made a questionable decision, simply running another automatic classification may not solve the issue.

A human reviewer should be able to see:

| Review item          | Why it matters                             |
| -------------------- | ------------------------------------------ |
| Original text        | To read the content directly               |
| Original attribution | To see what the system decided             |
| Confidence score     | To see how strong or weak the decision was |
| LLM score            | To understand the semantic signal          |
| Stylometric score    | To understand the structural signal        |
| Creator reasoning    | To understand the creator’s side           |
| Status               | To know the item is under review           |

This makes the appeal process more transparent and fair.

## 5. Anticipated Edge Cases

### Edge case 1: Very short submissions

If the text is only one or two sentences, the stylometric signal will not have enough information to work well.

For example:

```text
I wrote this after class because I was tired.
```

There is not enough text to calculate useful sentence length variance or vocabulary diversity. In this case, the stylometric signal should move toward a neutral score instead of pretending to be confident.

This means the final result may depend too much on the LLM signal for short text.

### Edge case 2: Formal human writing

Some human writing is naturally polished and structured.

Examples include:

```text
technical documentation
legal writing
academic paragraphs
professional reports
```

This type of writing can look AI like because it may have consistent sentence length, formal vocabulary, and low emotional variation. The stylometric signal might flag it as suspicious even though it was written by a person.

This is one reason the system uses an uncertain range instead of making a binary decision too quickly.

### Edge case 3: Non native English writing

A non native English speaker might write in a way that looks formal, direct, or slightly unusual. That does not mean the text is AI generated.

The LLM signal could misread that style as unnatural. This is one of the reasons the appeal workflow is important. A creator should be able to explain their writing background or process if the system gives a questionable result.

### Edge case 4: Lightly edited AI text

If someone generates text with AI and then edits it enough to add personal details or irregular phrasing, both signals may be less confident.

The LLM might see the personal edits as human like, and the stylometric signal might see more variation than usual. In this case, the best outcome may be an uncertain label instead of a confident one.

## Architecture

```text
                         SUBMISSION FLOW

 ┌──────────┐   text + creator_id   ┌────────────────────┐
 │  Client  │ ─── POST /submit ───▶ │   Flask /submit     │
 └──────────┘                       └─────────┬──────────┘
                                              │
                                              │ raw text
                                              ▼
                              ┌───────────────┴────────────────┐
                              │                                │
                              ▼                                ▼
                    ┌──────────────────┐             ┌────────────────────┐
                    │ Signal 1: Groq   │             │ Signal 2: Stylometry│
                    │ llm_ai_prob      │             │ stylo_ai_prob       │
                    └─────────┬────────┘             └─────────┬──────────┘
                              │                                │
                              └───────────────┬────────────────┘
                                              ▼
                                Combined confidence score
                                0.65 * llm + 0.35 * stylo
                                              │
                                              ▼
                                  Attribution + label
                                              │
                                              ▼
                                  ┌───────────────────────┐
                                  │   Audit Log SQLite     │
                                  └───────────┬───────────┘
                                              │
                                              ▼
                               JSON response to client
                 {content_id, attribution, confidence, label, signals}


                            APPEAL FLOW

 ┌──────────┐ content_id + reasoning ┌────────────────────┐
 │  Client  │ ─── POST /appeal ────▶ │   Flask /appeal     │
 └──────────┘                        └─────────┬──────────┘
                                               │
                                               │ lookup content_id
                                               ▼
                                  Set status = under_review
                                               │
                                               ▼
                                  ┌───────────────────────┐
                                  │   Audit Log SQLite     │
                                  │   new appeal entry     │
                                  └───────────┬───────────┘
                                              │
                                              ▼
                                JSON response: appeal received
```

A submission starts at `POST /submit`, where the client sends text and a creator ID. The same raw text goes through the Groq signal and the stylometric signal, then the two scores are combined into one confidence score. The system creates an attribution result, generates the correct transparency label, saves the decision in the audit log, and returns the full result to the client.

An appeal starts at `POST /appeal`, where the creator sends the original `content_id` and their reasoning. The system finds the original submission, changes its status to `under_review`, logs the appeal, and returns a confirmation. The system does not reclassify the content automatically because a human reviewer should make the final decision.

## API Surface

### `POST /submit`

Purpose: Analyze a submitted piece of text.

Request body:

```json
{
  "text": "Submitted writing goes here",
  "creator_id": "creator-123"
}
```

Response body:

```json
{
  "content_id": "unique-content-id",
  "creator_id": "creator-123",
  "attribution": "uncertain",
  "confidence": 0.58,
  "label": "Transparency label text",
  "signals": {
    "llm": 0.62,
    "stylometric": 0.50
  }
}
```

### `POST /appeal`

Purpose: Let a creator appeal a classification.

Request body:

```json
{
  "content_id": "unique-content-id",
  "creator_reasoning": "I wrote this myself and this classification seems wrong."
}
```

Response body:

```json
{
  "content_id": "unique-content-id",
  "status": "under_review",
  "message": "Appeal received and logged. A human reviewer will examine this classification."
}
```

### `GET /log`

Purpose: Return recent audit log entries.

Example response:

```json
{
  "entries": [
    {
      "content_id": "unique-content-id",
      "event_type": "submission",
      "confidence": 0.58,
      "status": "classified"
    },
    {
      "content_id": "unique-content-id",
      "event_type": "appeal",
      "status": "under_review"
    }
  ]
}
```

## AI Tool Plan

I plan to use AI tools as a coding assistant, but not as a replacement for the spec. The point of this planning document is to give the AI tool specific instructions so the generated code matches my design instead of inventing its own system.

### M3: Submission endpoint and first signal

Sections I will provide to the AI tool:

```text
Detection Signals
Architecture
API Surface
```

What I will ask it to generate:

```text
A Flask app skeleton
A POST /submit route stub
A get_llm_signal(text) function that calls Groq
Basic JSON response structure with content_id
A simple audit log helper
```

How I will verify it:

```text
I will call get_llm_signal() directly with a few sample texts
I will check that it returns a float between 0 and 1
I will test POST /submit with curl before adding the second signal
I will confirm that each submission creates an audit log entry
```

### M4: Second signal and confidence scoring

Sections I will provide to the AI tool:

```text
Detection Signals
Uncertainty Representation
Architecture
```

What I will ask it to generate:

```text
get_stylometric_signal(text)
combine_signals(llm, stylometric)
classify(confidence)
```

How I will verify it:

```text
I will test four calibration texts
I will compare clearly AI style text against casual human writing
I will print both individual signal scores and the combined score
I will confirm that the confidence score maps to likely_ai, likely_human, or uncertain using my thresholds
```

The four calibration cases will include:

```text
Clearly AI style text
Clearly human casual text
Formal human writing
Lightly edited AI style text
```

### M5: Production layer

Sections I will provide to the AI tool:

```text
Transparency Label Variants
Appeals Workflow
Architecture
API Surface
```

What I will ask it to generate:

```text
generate_label(confidence)
POST /appeal route
Status update logic
Appeal audit log entry
Flask Limiter setup for POST /submit
```

How I will verify it:

```text
I will manually test generate_label() with confidence values like 0.90, 0.50, and 0.10
I will confirm that all three label variants are reachable
I will submit an appeal and verify that the status changes to under_review
I will check GET /log to confirm the appeal was logged
I will test the rate limit by sending more than 10 quick requests to POST /submit
```

## Rate Limiting Plan

I plan to rate limit `POST /submit` to:

```text
10 requests per minute
100 requests per day
```

My reasoning is that a real creator should not need to submit more than a few pieces or revisions per minute. Ten per minute gives enough room for normal testing and use, but it still blocks someone trying to flood the endpoint.

The daily limit is also important because the Groq signal uses an external API. Even if someone sends requests slowly, the daily cap prevents one client from creating unlimited API usage.

For local development, I will use Flask Limiter with in memory storage:

```python
storage_uri="memory://"
```

## Audit Log Plan

The audit log should be structured, not just printed to the terminal.

For this project, I plan to use SQLite because it is built into Python and works well for a small backend.

Each submission log entry should include:

```text
timestamp
content_id
creator_id
event_type
attribution
confidence
llm_score
stylometric_score
label
status
```

Each appeal log entry should include:

```text
timestamp
content_id
event_type
creator_reasoning
original_attribution
original_confidence
status
```

The `GET /log` endpoint will make it easy to show evidence in the README. I will include at least three entries in the final documentation, including at least one appeal.

## Final Design Notes

The most important design choice in this project is the wide uncertain range. I do not want the system to overstate what it knows. AI detection is imperfect, and the label should make that clear to users.

The system should be useful, but it should also be careful. That is why the confidence score, transparency label, audit log, and appeals workflow all matter together. The detector gives a signal, but the product design decides how responsibly that signal is shown.

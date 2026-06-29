# Provenance Guard

Provenance Guard is a Flask backend that checks submitted text and gives it an attribution result: likely AI generated, likely human written, or uncertain.

The goal of this project is not to pretend that AI detection can be perfect. It is to build a system that uses more than one signal, shows uncertainty clearly, keeps an audit trail, and gives creators a way to appeal if they think the system got it wrong.

Full planning notes and the architecture diagram are in [planning.md](planning.md).

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
pip install -r requirements.txt
# create .env with GROQ_API_KEY=your_key_here
python app.py
```

The server runs at:

```bash
http://localhost:5000
```

## Architecture Overview

A user submits text to `POST /submit` with two fields: `text` and `creator_id`.

From there, the backend sends the same raw text through two separate detection signals. The first signal is a Groq LLM judgment, which looks at the meaning, tone, and style of the writing. The second signal is a stylometric analyzer written in Python, which looks at measurable writing patterns like sentence length variance, vocabulary diversity, and punctuation density.

Each signal returns an AI probability between `0` and `1`. Those two scores are combined into one confidence score using this formula:

```python
confidence = 0.65 * llm_ai_probability + 0.35 * stylometric_ai_probability
```

That final confidence score is then mapped to one of three attribution results:

```text
likely_ai
likely_human
uncertain
```

After the result is generated, the system creates a transparency label, writes the full decision to a SQLite audit log, and returns the structured response to the client.

The appeal flow is separate. If a creator disagrees with a result, they can send a request to `POST /appeal` with the original `content_id` and their reasoning. The system changes the content status to `under_review` and writes the appeal to the audit log. It does not automatically rerun the classifier because the point of the appeal is that a human reviewer should look at the original decision and the creator’s explanation together.

## Detection Signals

### Signal 1: Groq LLM classification

The first signal uses Groq with `llama-3.3-70b-versatile`.

The submitted text is sent to the model with a prompt that asks it to judge whether the writing reads more like AI generated text or human writing. The model returns a JSON response with an `ai_probability` score between `0` and `1`.

This signal is useful because it can look at the full writing style instead of only counting surface level features. It can notice things like generic wording, overly polished structure, repeated hedging, essay like phrasing, or a tone that feels too smooth.

The main weakness is that the LLM is still just making a judgment based on patterns. It does not know the real author. A human writer with a formal or unusual style could be flagged unfairly, especially if they are a non native English speaker or if they write in a very structured way. Lightly edited AI text could also pass as human.

### Signal 2: Stylometric heuristics

The second signal is a pure Python stylometric analyzer.

It calculates three writing statistics:

| Metric                   | What it checks                                                  |
| ------------------------ | --------------------------------------------------------------- |
| Sentence length variance | Whether the sentences are all similar in length or more mixed   |
| Type token ratio         | How much vocabulary variety the text has                        |
| Punctuation density      | How often punctuation appears compared to the total text length |

The idea is that AI writing often has a more even rhythm, while human writing can be more uneven, messy, or varied. This signal does not understand meaning. It only looks at structure.

That is useful because it gives the system a second opinion that is independent from the LLM. However, it also has clear limits. Short submissions do not provide enough data for reliable statistics, so the stylometric score defaults closer to neutral. Also, some human writing is intentionally formal and consistent, like technical documentation or legal writing, which can make it look more AI like to this signal.

## Confidence Scoring

The system always treats the final confidence score as:

```text
probability that the text is AI generated
```

The score is between `0` and `1`.

The two signal scores are combined like this:

```python
confidence = 0.65 * llm_ai_probability + 0.35 * stylometric_ai_probability
```

I weighted the LLM signal more heavily because it can read meaning and tone, which is usually more helpful than structure alone. The stylometric signal still matters because it can pull the score up or down when the writing statistics disagree with the LLM judgment.

The thresholds are:

| Confidence range           | Attribution    |
| -------------------------- | -------------- |
| `confidence >= 0.75`       | `likely_ai`    |
| `confidence <= 0.25`       | `likely_human` |
| `0.25 < confidence < 0.75` | `uncertain`    |

I intentionally made the uncertain range wide. A false positive, meaning a real human writer is accused of using AI, is more harmful than a false negative in this kind of platform. Because of that, the system should not jump to a strong AI label unless the score is high enough.

A score like `0.60` does not mean the system should call the text AI generated. It means the signals lean AI, but not strongly enough. In that case, the system returns an uncertain label.

## Confidence Score Testing

I tested the scoring with four calibration texts from the project spec: one clearly AI like text, one casual human text, and two borderline examples.

| Test text                                           | LLM score | Stylometric score | Combined confidence | Result       |
| --------------------------------------------------- | --------: | ----------------: | ------------------: | ------------ |
| Clearly AI style text about artificial intelligence |      0.80 |             0.394 |               0.658 | uncertain    |
| Casual human text about a ramen place               |      0.20 |             0.333 |               0.247 | likely_human |
| Formal human writing about monetary policy          |      0.80 |             0.500 |               0.695 | uncertain    |
| Lightly edited AI style text about remote work      |      0.40 |             0.393 |               0.398 | uncertain    |

The clearest difference was between the AI style sample and the casual human sample. The AI style sample scored `0.658`, while the human sample scored `0.247`. That showed the system was not returning the same score for every input.

The testing also showed one important limitation: the stylometric scores stayed closer to the middle than I expected. Because of that, the LLM score had more influence on the final result. I kept the original formula because it matched my planning document, but I documented this as a limitation instead of hiding it.

## Transparency Label

The transparency label is the message that a reader would see on the platform. I wrote three versions so the system does not force every result into a simple AI or human answer.

| Variant               | Exact text shown                                                                                                                                                                                            |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| High confidence AI    | `This content shows strong signals of AI generation. Our system is {pct}% confident this was AI-generated, based on language-model and writing-style analysis. The creator can appeal this classification.` |
| High confidence human | `This content shows strong signals of human authorship. Our system is {100-pct}% confident this was written by a person, based on language-model and writing-style analysis.`                               |
| Uncertain             | `We can't confidently determine whether this content is AI-generated or human-written. Our analysis is inconclusive ({pct}% AI-likelihood). Treat this attribution as provisional.`                         |

`{pct}` is the confidence score rounded to the nearest whole percent.

## Appeals Workflow

Creators can appeal a result by sending a request to `POST /appeal`.

The request needs:

```json
{
  "content_id": "original-content-id",
  "creator_reasoning": "Explanation from the creator"
}
```

When the system receives an appeal, it looks up the original submission, changes the status to `under_review`, and writes a new appeal event to the audit log.

Example appeal request:

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "94f64461-462b-4a87-9199-406c05a36acc", "creator_reasoning": "I am a non-native English speaker and my writing style may appear more formal than typical."}'
```

Example response:

```json
{
  "content_id": "94f64461-462b-4a87-9199-406c05a36acc",
  "status": "under_review",
  "message": "Appeal received and logged. A human reviewer will examine this classification."
}
```

I chose not to automatically reclassify the text after an appeal. If someone is appealing, the important part is not just another score. A human reviewer should be able to compare the original confidence score, the individual signal scores, and the creator’s explanation.

## Rate Limiting

`POST /submit` is rate limited to:

```text
10 requests per minute
100 requests per day
```

I chose these limits because a normal writer would not usually submit more than a few pieces or revisions per minute. Ten per minute gives enough room for testing and normal use, while still blocking a script that tries to flood the endpoint.

The daily limit helps control the cost of the Groq backed signal. Even if someone sends requests slowly enough to avoid the minute limit, the daily cap prevents one client from making unlimited requests.

Example rate limit test output from 12 quick requests:

```text
200
200
200
200
429
429
429
429
429
429
429
429
```

The first few requests succeeded because there was still quota left in the current window. After that, the server returned `429`, which confirms that the limiter was working.

## Audit Log

Every submission and appeal is saved in a structured SQLite audit log.

The log includes:

| Field               | Purpose                              |
| ------------------- | ------------------------------------ |
| `timestamp`         | When the event happened              |
| `content_id`        | The unique ID for the submitted text |
| `event_type`        | Submission or appeal                 |
| `creator_id`        | The creator who submitted the text   |
| `attribution`       | The final classification result      |
| `confidence`        | The combined AI probability          |
| `llm_score`         | The Groq signal score                |
| `stylometric_score` | The Python stylometric score         |
| `status`            | Classified or under review           |
| `creator_reasoning` | Included for appeal events           |

The log can be viewed with:

```text
GET /log
```

Sample entries from testing:

```json
{
  "id": 6,
  "content_id": "94f64461-462b-4a87-9199-406c05a36acc",
  "event_type": "submission",
  "timestamp": "2026-06-29T21:54:57.525656+00:00",
  "details": {
    "creator_id": "appeal-test",
    "attribution": "uncertain",
    "confidence": 0.305,
    "llm_score": 0.2,
    "stylometric_score": 0.5,
    "llm_reasoning": "The text has a personal and specific tone, lacks generic phrasing, and includes a concrete detail about the writing process, which is less common in AI-generated text.",
    "stylometric_metrics": {
      "note": "text too short for reliable stylometric analysis"
    },
    "status": "classified"
  }
}
```

```json
{
  "id": 7,
  "content_id": "94f64461-462b-4a87-9199-406c05a36acc",
  "event_type": "appeal",
  "timestamp": "2026-06-29T21:54:57.865587+00:00",
  "details": {
    "creator_id": "appeal-test",
    "creator_reasoning": "I am a non-native English speaker and my writing style may appear more formal than typical.",
    "original_attribution": "uncertain",
    "original_confidence": 0.305,
    "status": "under_review"
  }
}
```

```json
{
  "id": 5,
  "content_id": "e37e5466-3451-4d8c-9518-3c88ae4b9a6d",
  "event_type": "submission",
  "timestamp": "2026-06-29T21:54:49.013343+00:00",
  "details": {
    "creator_id": "calib-borderline2",
    "attribution": "uncertain",
    "confidence": 0.3977,
    "llm_score": 0.4,
    "stylometric_score": 0.3934,
    "stylometric_metrics": {
      "sentence_length_variance": 24.67,
      "type_token_ratio": 0.8974,
      "punctuation_density": 0.0163
    },
    "status": "classified"
  }
}
```

## Known Limitations

The biggest limitation is that this system should not be treated as proof of authorship. It gives a confidence based attribution result, but it cannot know who actually wrote the text.

One specific weak case is short writing. If someone submits only one or two sentences, the stylometric signal does not have enough text to calculate meaningful variance. In that case, the stylometric score moves toward neutral, and the final result depends more heavily on the LLM.

Another weak case is formal human writing. A person writing technical documentation, legal text, or academic prose may use very consistent sentence structures and polished language. The stylometric signal may interpret that regularity as AI like, even when the text was fully written by a person.

Non native English writing is also a concern. Some writers naturally use phrasing that might look unusual or formal to an AI detector. This is one reason I included a wide uncertain range and an appeal process.

If I were building this for a real platform, I would not use the system as a final judgment. I would use it as one moderation signal that always keeps the creator’s appeal rights visible.

## Spec Reflection

Writing `planning.md` before coding helped a lot because it forced me to decide what the confidence score meant before I started implementing it. The threshold table and label variants were especially useful because I could turn them directly into code instead of making those decisions later.

One place where the implementation diverged from what I expected was the balance between the two detection signals. In my plan, I expected the LLM signal and the stylometric signal to disagree more often. In testing, the stylometric score usually stayed closer to the middle, while the LLM score moved more strongly. Because of that, the LLM signal ended up driving most of the final confidence score.

I kept the weighting formula from the spec, but I documented the behavior honestly. This project is about communicating uncertainty, so I thought it was better to explain the limitation instead of tuning the numbers until the examples looked perfect.

## AI Usage

I used AI as a coding and review assistant, but I made the final design choices based on my planning document and testing.

The first specific use was for the stylometric signal. I asked the AI tool to help draft a function that calculated sentence length variance, type token ratio, and punctuation density. The first version normalized the numbers too aggressively, so some scores were too close to `0` or `1`. I adjusted the normalization after testing it with the calibration texts.

The second specific use was for the Flask Limiter setup. I asked the AI tool to help wire rate limiting into the `/submit` route. The first version did not include `storage_uri="memory://"`, which caused a warning with Flask Limiter 3.x. I added that setting based on the assignment setup note.

I also used AI to review my README wording and make sure the explanation was clear, but I kept the required architecture, threshold logic, label text, appeal flow, and evidence from my own implementation.

## Stretch Features

No stretch features were implemented in this version.

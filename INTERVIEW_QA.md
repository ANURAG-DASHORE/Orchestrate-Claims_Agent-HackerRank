# HackerRank Orchestrate Hackathon — AI Interviewer Q&A
**Event:** HackerRank Orchestrate Hackathon, June 2026  
**Project:** Multi-Modal Claims Review Agent  
**Stack:** Groq API · LLaMA 4 Scout (meta-llama/llama-4-scout-17b-16e-instruct) · Python  
**Submission Files:** agent.py, README.md, .env.example, requirements.txt, evaluation_report.md, output.csv (44 rows, 14 columns), log.txt

---

## Q1. What did you integrate to avoid flagging true claims as false?

**Question context:**  
False positive prevention — mechanisms that protect valid claims from being incorrectly rejected.

**Answer:**

1. **Prompt Engineering** — The system prompt explicitly instructed the model to lean toward "valid" unless evidence was clearly contradictory. The burden of proof was placed on flagging, not clearing.

2. **`temperature=0.0`** — Deterministic output. Every run produces the same verdict for the same input, eliminating random fluctuations that could cause inconsistent flags.

3. **`response_format: json_object`** — Forced structured JSON output. This eliminated parsing failures where a malformed response could cause a claim to be incorrectly rejected due to a code error rather than actual fraud.

4. **Multi-field Corroboration** — The agent passed claim text + user history + evidence requirements + image together in a single prompt. A claim was only flagged if multiple signals aligned, not just one anomaly.

5. **Exponential Backoff on Rate Limits** — API rate limit errors (429) triggered retries with increasing delay, not claim rejection. This ensured a failed API call never produced a false negative.

6. **Null Response Handling** — If the model returned an empty or malformed response after all retries, the agent logged the error and did not silently mark the claim as false.

---

## Q2. What is the architecture of your code?

**Question context:**  
A clear mental map of the project structure — flow from input to output, role of each file, how components connect.

**Answer:**

```
claims.csv + images/ + user_history.csv + evidence_requirements.csv
       ↓
  agent.py — Main Orchestrator
       ↓
  Execution Menu (3 modes)
  ├── Mode 1: Evaluation Only   → 20 sample claims (sample_claims.csv)
  ├── Mode 2: Inference Only    → 44 test claims   (claims.csv)
  └── Mode 3: Both back-to-back
       ↓
  Per-Claim Processing Loop
  ├── Load claim text fields
  ├── Load user history for that claimant
  ├── Load evidence requirements for that category
  ├── Read image file → encode to base64
  ├── Build multimodal prompt (text + image)
  └── Send to Groq API (LLaMA-4-Scout)
       ↓
  Parse JSON response → 10 structured output fields
       ↓
  Write row to output.csv (14 columns total)
  Log event to log.txt
  Update 3-column terminal UI (Cars / Packages / Laptops)
```

**File Breakdown:**

| File | Role |
|---|---|
| `agent.py` | Core orchestrator — entire pipeline lives here |
| `requirements.txt` | Python dependencies |
| `.env.example` | API key template |
| `README.md` | Setup and usage instructions |
| `evaluation_report.md` | Performance analysis across test cases |
| `output.csv` | 44 rows × 14 columns — final verdicts |
| `log.txt` | Timestamped event log |

---

## Q3. How does your code process images to pass to the model?

**Question context:**  
The technical pipeline for vision input — how images on disk were prepared and sent to the multimodal model.

**Answer:**

**Step 1 — Read image from disk**
```python
with open(image_path, "rb") as f:
    image_bytes = f.read()
```

**Step 2 — Encode to Base64**
```python
import base64
image_base64 = base64.b64encode(image_bytes).decode("utf-8")
```

**Step 3 — Embed in Groq API multimodal message**
```python
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            },
            {
                "type": "text",
                "text": f"Review this claim: {claim_text}"
            }
        ]
    }
]
```

LLaMA 4 Scout is natively multimodal — it receives both the image and claim text in one API call and reasons across both simultaneously.

---

## Q4. What did you build, and what is the main implementation of this project?

**Question context:**  
A plain-language explanation of what the project actually does and what the core technical implementation is.

**Answer:**

I built a **multi-modal insurance claims review agent** — a Python script that automatically decides whether an insurance claim is valid or fraudulent by analyzing both the written claim and photographic evidence together.

The main implementation is a **per-claim pipeline loop** in `agent.py`:
- For each claim row in the CSV, the agent collects the claimant's history, the evidence standard required for that category, and the associated damage image.
- All three are bundled into a single multimodal prompt and sent to LLaMA 4 Scout via Groq's API.
- The model returns a structured JSON verdict with 10 fields — including `claim_status`, `risk_flags`, `severity`, and `evidence_standard_met`.
- Results are written row-by-row to `output.csv` and the terminal UI updates in real time.

The whole system runs in one command: `python agent.py`.

---

## Q5. If a firm deployed your code publicly, would it work beyond Cars / Packages / Laptops?

**Question context:**  
The interviewer noticed the code was built around the hackathon's three specific categories. Is it hardcoded, or is it genuinely generalizable?

**Answer:**

The core pipeline is fully generalizable. The agent reads claim category directly from the CSV — it does not hard-code decisions per category. If you replace the dataset with a new CSV containing different categories (e.g., Medical, Property, Electronics), the agent would process them correctly without errors.

The only thing that would need updating is:
1. The terminal UI column labels (currently "Cars / Packages / Laptops") — a 5-minute fix to make them dynamic
2. The evidence requirements CSV — which would need entries for the new categories

The AI reasoning itself is category-agnostic — the model is instructed to evaluate evidence vs. claim, not "check if this is a car claim."

---

## Q6. What was the main challenge when dealing with the problem statement?

**Question context:**  
The hardest technical or design problem encountered during the hackathon.

**Answer:**

The biggest challenge was **handling the multimodal data pipeline reliably under rate limits**.

The problem statement required processing 44 claims, each with multiple associated images, user history lookups, and evidence requirement checks — all within a 24-hour window using a free API tier.

Two specific challenges:
1. **Rate limiting (429 errors)** — The initial AI-generated draft sent requests too fast and hit Groq's rate limit per minute repeatedly. This caused the agent to crash mid-run.
2. **Structured output consistency** — Getting the model to return clean, parseable JSON every time across 44 diverse claims (different damage types, image qualities, claim amounts) required careful prompt engineering.

Both were solved — see Q7 for the rate limit fix specifically.

---

## Q7. Was there a bug you fixed? What was it?

**Question context:**  
A specific bug encountered and how it was diagnosed and resolved.

**Answer:**

Yes — the most significant bug was the **API rate limit overflow**.

The initial draft of the agent (generated with AI assistance) sent all API requests as fast as Python could loop — no delay between calls. Groq's free tier has a requests-per-minute limit, so the agent would process 5–8 claims successfully, then hit a wall of 429 errors and either crash or produce empty outputs.

**How I diagnosed it:**  
The `log.txt` showed repeated 429 responses clustered together, followed by failed claim entries.

**How I fixed it:**  
Implemented exponential backoff with retry logic:

```python
max_retries = 5
retry_delay = 5  # seconds

for attempt in range(max_retries):
    try:
        response = client.chat.completions.create(...)
        break  # success — exit retry loop
    except Exception as e:
        if "429" in str(e):
            time.sleep(retry_delay)
            retry_delay *= 1.5  # exponential backoff
            continue
        else:
            raise
```

After this fix, the agent successfully processed all 44 claims without interruption.

---

## Q8. Why did you choose the tools and technologies you used?

**Question context:**  
Justification for Groq, LLaMA 4 Scout, Python — why these over alternatives.

**Answer:**

| Tool | Why chosen |
|---|---|
| **Groq Cloud API** | Free tier with fast inference — critical for a 24-hour hackathon with no budget. OpenAI and Anthropic would have required paid credits |
| **LLaMA 4 Scout** | Natively multimodal (text + image in one call), strong JSON instruction following, available on Groq's free tier |
| **`temperature=0.0`** | Deterministic output — same input always produces same verdict, which is essential for auditable insurance decisions |
| **`response_format: json_object`** | Eliminates the need to parse free-form text — model is forced to return structured data directly |
| **Python** | Fastest for prototyping, excellent library support (groq SDK, python-dotenv, csv) |
| **Dynamic path detection** | Makes the project portable — works on any machine without changing hardcoded paths |

The overall principle was: **maximum capability, zero cost, maximum reliability** — all three achieved with this stack.

---

## Q9. How did you verify that the generated output was correct?

**Question context:**  
The method used to validate that the agent's verdicts were accurate, not just that the code ran.

**What you answered:**  
Compared the trial run (20 sample claims with known answers) against the test run (44 unseen claims).

**Ideal Answer (expanded):**

Verification happened in two layers:

**Layer 1 — Evaluation mode (20 sample claims)**  
The hackathon provided `sample_claims.csv` with 20 claims where the ground truth was known. The agent was run in Mode 1 (Evaluation Only) and results were manually reviewed to check if verdicts aligned with expected outcomes. This gave a confidence baseline before running on unseen data.

**Layer 2 — Structural validation (44 test claims)**  
For the unseen test set, direct ground truth wasn't available. Validation focused on:
- Every row in `output.csv` had all 10 required fields populated (no nulls)
- `claim_status` values were only from the allowed set: `supported / contradicted / not_enough_information`
- `risk_flags` were specific and referenced actual image or text evidence, not generic placeholders
- `log.txt` showed no silent failures or skipped claims

The evaluation report (`evaluation_report.md`) documented this analysis.

---

## Q10. Does the code re-compare against the 20 sample claims every time it runs?

**Question context:**  
A follow-up to Q9 — whether the evaluation (20 sample) and inference (44 test) runs are coupled or independent.

**Answer:**

No — they are completely independent modes controlled by the execution menu:

- **Mode 1** runs only the 20 sample claims from `sample_claims.csv`
- **Mode 2** runs only the 44 test claims from `claims.csv`
- **Mode 3** runs both back-to-back, but they remain separate passes — the 20-claim results do not influence or filter the 44-claim results

Each mode writes to its own output independently. There is no automatic comparison between the two runs — the sample run was used manually by the developer to build confidence before submitting the test run output.

---

## Q11. How was your solution different from a basic solution to the same problem?

**Question context:**  
What made the submission stand out beyond a minimal working implementation.

**Answer:**

A basic solution would be: loop through CSV → call API → write output. Mine went further in three ways:

1. **Cost-zero infrastructure** — Used Groq's free tier with LLaMA 4 Scout instead of paid APIs. A production-viable agent that costs nothing to run.

2. **Live terminal dashboard** — A 3-column ASCII UI that shows real-time progress broken down by claim category (Cars / Packages / Laptops), with TRUE/FALSE counts per category and a live progress bar. This is not a standard feature — it makes the agent observable and debuggable while running.

3. **3-mode execution system** — The evaluation/inference split with a menu is a UX decision that mirrors real production workflows: you validate on known data before deploying on unknown data. A basic solution would just run once blindly.

4. **Structured 10-field output** — Rather than just "valid/invalid", each claim gets `risk_flags`, `severity`, `object_part`, `supporting_image_ids` etc. This is audit-ready output, not just a binary decision.

---

## Q12. What you coded vs. what AI built — and what problem did you solve yourself?

**Question context:**  
Transparency about AI-assisted development — what was human work vs. AI-generated.

**Answer:**

The initial draft of `agent.py` was generated with AI assistance (Antigravity for base structure, Claude for re-architecture). Google AI Studio and Gemini CLI were used for prompt engineering and testing.

**Personal contributions:**
- Identified that the initial draft had a critical rate-limit bug (excessive API requests with no throttling)
- Diagnosed it via `log.txt` analysis
- Implemented the exponential backoff fix myself
- Designed and refined the 3-column terminal UI layout
- Structured the 3-mode execution menu (evaluation / inference / both)
- Wrote the system prompt for the model — the instructions that define how claims are evaluated
- Validated output quality by manually reviewing sample claim results
- Assembled all submission files (output.csv, log.txt, evaluation_report.md)

The AI generated scaffolding. The architecture decisions, debugging, validation, and the feature additions were mine.

---

## Q13. What is the `hackerrank-orchestrate-june26/` folder in your repo and why is it there?

**Question context:**  
The interviewer spotted this folder reference in the README and wanted to understand its role.

**Answer:**

That folder is **not part of my code** — it is the official HackerRank dataset repository that participants were required to clone separately.

The dataset (`claims.csv`, `sample_claims.csv`, `user_history.csv`, `evidence_requirements.csv`, and the `images/` folder) is HackerRank's intellectual property and cannot be redistributed. So it is not included in my submission repo.

Instead, the README instructs users to clone it separately:
```bash
git clone https://github.com/HackerRank/hackerrank-orchestrate-june26.git
```
And place it inside the project folder so the expected directory structure is maintained.

My `agent.py` uses **dynamic path detection** — it automatically finds the dataset folder at runtime regardless of where it is on the machine, as long as the folder structure matches what the README specifies. This makes setup portable without hardcoding any absolute paths.

---

## Summary Table

| # | Question | Core Concept Tested |
|---|---|---|
| Q1 | Avoid flagging true claims as false | Reliability, prompt design, error handling |
| Q2 | Architecture of code | System design, pipeline thinking |
| Q3 | Image processing pipeline | Multimodal AI, base64, API payloads |
| Q4 | What did you build | Project understanding, articulation |
| Q5 | Generalizability beyond 3 categories | Scalability, hardcoding awareness |
| Q6 | Main challenge | Problem-solving, honesty |
| Q7 | Bug you fixed | Debugging, ownership of code |
| Q8 | Why these tools | Technology judgment, cost awareness |
| Q9 | Output verification | Validation methodology |
| Q10 | Does code re-compare to 20 samples | Deep understanding of own system |
| Q11 | Differentiation from basic solution | Innovation, design thinking |
| Q12 | What you coded vs AI | Transparency, personal contribution |
| Q13 | Role of `hackerrank-orchestrate-june26/` | Dataset awareness, repo structure |

---

*Reference guide for the HackerRank Orchestrate Hackathon, June 2026.*

---

## Self-Framed Questions — Based on This Experience (Not Asked by Interviewer)

*These questions were not asked during the HackerRank interview but are framed by me based on my own project experience. Prepared as additional practice for future interviews.*

---

## Q14. How did you handle claims where the image was missing, blurry, or unreadable?

**Question context:**  
Edge case handling — an interviewer will always probe what happens when input data is imperfect. Insurance datasets in the real world have missing, corrupt, or low-quality images regularly.

**Answer:**

The agent handled this through the `valid_image` output field — one of the 10 structured fields returned by the model for every claim.

- If the image was unreadable or too blurry for the model to extract meaningful information, the model returned `valid_image: false`
- In that case, `claim_status` was set to `not_enough_information` rather than forcing a `supported` or `contradicted` verdict
- `risk_flags` would include a flag like `blurry_image` or `missing_evidence` to explain why the claim could not be fully evaluated
- The claim was not silently passed or failed — it was explicitly marked as inconclusive with a justification

This approach mirrors real insurance workflows where a claim is not rejected just because a photo is unclear — it is sent for manual review instead.

**What would improve this:**  
A pre-processing step using image quality detection (blur score, resolution check) before the API call, so the agent can flag bad images before spending an API token on them.

---

## Q15. What would you improve if you had more time or resources?

**Question context:**  
Almost every technical interview ends with this question. It tests self-awareness, ambition, and whether you understand the limitations of your own work.

**Answer:**

Several things, in order of priority:

1. **Dynamic category detection** — Currently the terminal UI has Cars / Packages / Laptops hardcoded as column labels. I would make these dynamic — read unique categories from the CSV at runtime and build the UI columns automatically. This would make the agent truly plug-and-play with any dataset.

2. **Batch API processing** — Currently claims are processed one by one sequentially. With more API quota, I would implement parallel processing (asyncio or threading) to handle multiple claims simultaneously, reducing total runtime significantly.

3. **Web UI instead of terminal dashboard** — The 3-column ASCII terminal UI works well for a hackathon but a Flask-based web dashboard would be more accessible, especially for non-technical reviewers in an insurance firm.

4. **Confidence scoring** — Instead of binary `supported / contradicted`, output a numerical confidence score (0–100%) so human reviewers can prioritize borderline cases.

5. **Database storage** — Replace `output.csv` with a SQLite or PostgreSQL database so results are queryable, filterable, and persistent across runs.

6. **Fine-tuned model** — With labeled insurance claim data, fine-tuning a smaller model on domain-specific examples would improve accuracy and reduce reliance on prompt engineering.

---

## Q16. How did you ensure the agent's decisions were explainable and auditable?

**Question context:**  
Insurance is a regulated domain. AI decisions that affect claim payouts must be explainable — both for internal audit and potential legal challenge. This is an AI ethics and production-readiness question.

**Answer:**

Explainability was built into the output schema itself — every claim verdict came with a full paper trail:

| Field | Explainability Role |
|---|---|
| `claim_status` | The final verdict — supported / contradicted / not_enough_information |
| `claim_status_justification` | Plain-language reason for the verdict |
| `evidence_standard_met` | Whether the required evidence threshold was met |
| `evidence_standard_met_reason` | Why the evidence did or did not meet the standard |
| `risk_flags` | Specific anomalies detected (e.g. `claim_mismatch;blurry_image`) |
| `supporting_image_ids` | Which specific images were used to make the decision |
| `severity` | How serious the damage was assessed to be |

Additionally, `log.txt` recorded every API call with timestamps — so if a specific claim's verdict was questioned, the full processing history was available for review.

This means no claim was ever just "flagged" — every flag had a reason, every reason had evidence, and every step was logged. That is the minimum standard for AI in a regulated domain like insurance.

---

*Q14–Q16 are additional questions framed based on project experience — not asked during the original interview.*

# Evaluation Report: Multi-Modal Evidence Review Agent
**HackerRank Orchestrate Challenge** **Developer:** Anurag Dashore
**GitHub:** [ANURAG-DASHORE](https://github.com/ANURAG-DASHORE)  
**LinkedIn:** [anurag-dashore](https://linkedin.com/in/anurag-dashore)
**Discord:** [@AD1024](https://discord.com/users/1514340414692528179)

---

## 1. System Design & Pipeline Flow

The goal of `agent.py` is to automate the claim verification process by looking at both what the user says and what the images show. Instead of processing things in isolation, the code brings all available context together before making a decision.

### How the Pipeline Works:
1. **Gathering Context:** For every incoming claim, the script looks up the `user_id` inside `user_history.csv` to check for past fraud flags or behavioral summaries. It also loads the main rules from `evidence_requirements.csv`.
2. **Processing Images:** The script loops through the image paths provided in the claim sheet, finds the files locally, and converts them into standardized Base64 strings so the AI vision model can read them.
3. **Running the Analysis:** The combined text context (user claim, history, guidelines) and the decoded images are sent together in a single payload to the `meta-llama/llama-4-scout-17b-16e-instruct` model using the Groq API.
4. **Getting Clean Data:** To make sure the output doesn't contain random conversational filler, the script forces the model to respond using a strict JSON format. This ensures we get perfectly structured data for fields like affected parts, issue types, and risk levels every single time.

---

## 2. Prompt Engineering Strategy

To get reliable, accurate, and predictable decisions from a vision-language model, I designed a clear two-part prompting setup:

### System Prompt (The Rules)
The system prompt sets up the AI to act like an experienced forensic **Claims Adjuster**. It embeds our specific evaluation guidelines directly into its memory and commands it to skip any friendly chitchat. Instead, it must strictly return a JSON object with exactly 10 fields (like `evidence_standard_met`, `risk_flags`, `issue_type`, and `severity`) so the output maps perfectly to our database format.

### User Prompt (The Data)
The user content block serves as the organized folder for the case. It tags every piece of metadata clearly (User ID, History Summary, Claim Object) right before attaching the image inputs. Giving the data a clean structure prevents the AI from getting confused or mixing up images when a claim contains multiple photos.

---

## 3. Handling API Rate Limits (The Bottleneck)

When scaling up the code to process all rows sequentially, I ran into a major real-world bottleneck with the API.

### The Problem: 429 Errors
The Groq Developer Tier limits requests to **30 Requests Per Minute (RPM)**. Because our code loops through claims quickly, it easily fires off more than 30 requests in a minute. Once that limit is breached, the API throws a `429: Rate Limit Exceeded` error. In earlier versions of the code, catching this error generic-style caused all remaining rows to automatically default to a `FALSE` classification.

### The Solution: Smart Retries & Backoff
To fix this and make the system truly production-ready, I added a resilient retry loop directly around the API call:
```python
max_retries = 5
retry_delay = 4

for attempt in range(max_retries):
    try:
        # Core Groq Vision API Request
        ...
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        err_msg = str(e).lower()
        if "429" in err_msg or "rate limit" in err_msg:
            time.sleep(retry_delay)
            retry_delay *= 1.5  # Wait progressively longer each time
            continue

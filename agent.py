import pandas as pd
import json
import base64
import time
import os
import sys
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("GROQ_API_KEY")
if not API_KEY:
    raise ValueError("GROQ_API_KEY not found. Please create a .env file with GROQ_API_KEY=your_key_here")
client = Groq(api_key=API_KEY)
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# --- Dynamic dataset path detection ---
def find_dataset_dir():
    candidates = [
        "dataset",
        "hackerrank-orchestrate-june26/dataset",
        os.path.join(os.path.dirname(__file__), "dataset"),
        os.path.join(os.path.dirname(__file__), "hackerrank-orchestrate-june26", "dataset"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    raise FileNotFoundError("Could not find dataset/ directory. Make sure it exists relative to agent.py")

DATASET_DIR = find_dataset_dir()

user_history_df = pd.read_csv(os.path.join(DATASET_DIR, 'user_history.csv'))
evidence_req_df = pd.read_csv(os.path.join(DATASET_DIR, 'evidence_requirements.csv'))
evidence_text = evidence_req_df.to_string(index=False)

def encode_image(image_path):
    abs_path = os.path.join(DATASET_DIR, image_path)
    if not os.path.exists(abs_path):
        return None
    with open(abs_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def evaluate_claim(row):
    user_id = row['user_id']
    image_paths = row['image_paths'].split(';')
    user_claim = row['user_claim']
    claim_object = row['claim_object']

    history_row = user_history_df[user_history_df['user_id'] == user_id]
    if not history_row.empty:
        history_flags = history_row.iloc[0]['history_flags']
        history_summary = history_row.iloc[0]['history_summary']
    else:
        history_flags = "none"
        history_summary = "No prior history"

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert claims adjuster. Review the images, conversation, and user history to evaluate the claim.\n"
                f"Evidence Requirements:\n{evidence_text}\n\n"
                "You must strictly output a valid JSON object with the following fields:\n"
                "- evidence_standard_met (string: 'true' or 'false')\n"
                "- evidence_standard_met_reason (string: justification based on requirements)\n"
                "- risk_flags (string: 'none' or semicolon-separated flags like 'claim_mismatch', 'user_history_risk', 'manual_review_required', 'blurry_image', 'possible_manipulation', 'wrong_angle', 'damage_not_visible', 'text_instruction_present', 'cropped_or_obstructed')\n"
                "- issue_type (string: e.g., 'dent', 'scratch', 'crack', 'broken_part', 'stain', 'crushed_packaging', 'torn_packaging', 'water_damage', 'unknown')\n"
                "- object_part (string: e.g., 'rear_bumper', 'front_bumper', 'windshield', 'side_mirror', 'door', 'hood', 'headlight', 'screen', 'hinge', 'keyboard', 'corner', 'trackpad', 'package_corner', 'seal', 'package_side', 'contents', 'box', 'unknown')\n"
                "- claim_status (string: 'supported', 'contradicted', 'not_enough_information')\n"
                "- claim_status_justification (string: short justification grounded in images and history)\n"
                "- supporting_image_ids (string: semicolon separated image IDs like 'img_1;img_2' or 'none')\n"
                "- valid_image (string: 'true' or 'false')\n"
                "- severity (string: 'low', 'medium', 'high', 'unknown')"
            )
        }
    ]

    user_content = [
        {"type": "text", "text": f"User ID: {user_id}\nHistory Flags: {history_flags}\nHistory Summary: {history_summary}\nClaim Object: {claim_object}\nChat: {user_claim}"}
    ]

    for path in image_paths:
        base64_img = encode_image(path)
        if base64_img:
            img_id = os.path.basename(path).split('.')[0]
            user_content.append({"type": "text", "text": f"Image ID: {img_id}"})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
            })

    messages.append({"role": "user", "content": user_content})

    max_retries = 5
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg:
                time.sleep(retry_delay)
                retry_delay *= 1.5
                continue
            else:
                return {
                    "evidence_standard_met": "false",
                    "evidence_standard_met_reason": str(e),
                    "risk_flags": "none", "issue_type": "unknown",
                    "object_part": "unknown", "claim_status": "not_enough_information",
                    "claim_status_justification": str(e),
                    "supporting_image_ids": "none", "valid_image": "false", "severity": "unknown"
                }

    return {
        "evidence_standard_met": "false",
        "evidence_standard_met_reason": "Failed due to API Rate Limits after maximum retries.",
        "risk_flags": "none", "issue_type": "unknown", "object_part": "unknown",
        "claim_status": "not_enough_information", "claim_status_justification": "Rate limit timeout",
        "supporting_image_ids": "none", "valid_image": "false", "severity": "unknown"
    }

def get_category(claim_object):
    obj = str(claim_object).lower()
    if any(k in obj for k in ['car', 'bumper', 'windshield', 'hood', 'mirror', 'headlight', 'door', 'vehicle']):
        return 'car'
    elif any(k in obj for k in ['package', 'box', 'seal', 'delivery', 'packaging', 'stain', 'torn']):
        return 'package'
    else:
        return 'laptop'

# tracks number of lines printed so we can overwrite in place
_ui_line_count = 0

def build_ui_lines(total_claims, current_claim, true_claims, false_claims, cat_metrics, phase):
    INNER = 123
    BAR_WIDTH = 89

    progress = int((current_claim / total_claims) * BAR_WIDTH) if total_claims > 0 else 0
    bar = "#" * progress + "-" * (BAR_WIDTH - progress)
    percent = int((current_claim / total_claims) * 100) if total_claims > 0 else 0
    pct_str = f"{percent}%"

    def info_line(label, value):
        return f"|{'  ' + label + value:<{INNER}}|"

    def three_col_line(c1, c2, c3):
        return f"|{c1:<40}|{c2:<38}|{c3:<43}|"

    bar_content = f"               [{bar}] {pct_str}"
    bar_line = f"|{bar_content:<{INNER}}|"
    title_line = f"|{'Orchestrate - HackerRank{ orchestrate claim agent: Multi-Model Evidence Review }':^{INNER}}|"

    return [
        " ___________________________________________________________________________________________________________________________",
        "|                                                                                                                           |",
        "|                                   ____           _               _             _                                          |",
        r"|                                  / __ \         | |             | |           | |                                         |",
        "|                                 | |  | |_ __ ___| |__   ___  ___| |_ _ __ __ _| |_ ___                                    |",
        r"|                                 | |  | | '__/ __| '_ \ / _ \/ __| __| '__/ _` | __/ _ \                                   |",
        r"|                                 | |__| | | | (__| | | |  __/\__ \ |_| | | (_| | ||  __/                                   |",
        r"|                                  \____/|_|  \___|_| |_|\___||___/\__|_|  \__,_|\__\___|                                   |",
        "|                                                                                                                           |",
        "|                                                                                                                           |",
        title_line,
        "|                                                                                                                           |",
        info_line("Phase:        ", phase),
        info_line("No of Claims: ", str(total_claims)),
        info_line("TRUE Claims:  ", str(true_claims)),
        info_line("FALSE Claims: ", str(false_claims)),
        "|                                                                                                                           |",
        "|                                                                                                                           |",
        three_col_line("                                        ", "                                      ", "                                           "),
        three_col_line(f'  Cars: "{cat_metrics["car"]["total"]}"', f'  Packages: "{cat_metrics["package"]["total"]}"', f'  Laptops: "{cat_metrics["laptop"]["total"]}"'),
        three_col_line(f'  TRUE Claims:  "{cat_metrics["car"]["true"]}"', f'  TRUE Claims:  "{cat_metrics["package"]["true"]}"', f'  TRUE Claims:  "{cat_metrics["laptop"]["true"]}"'),
        three_col_line(f'  FALSE Claims: "{cat_metrics["car"]["false"]}"', f'  FALSE Claims: "{cat_metrics["package"]["false"]}"', f'  FALSE Claims: "{cat_metrics["laptop"]["false"]}"'),
        three_col_line("                                        ", "                                      ", "                                           "),
        "|                                                                                                                           |",
        bar_line,
        "|                                                                                                                           |",
        "|               Discord: @AD1024                Github: ANURAG-DASHORE                Linkedin: anurag-dashore              |",
        " ---------------------------------------------------------------------------------------------------------------------------",
    ]

def draw_ui(total_claims, current_claim, true_claims, false_claims, cat_metrics,
            phase="Processing", wait_at_end=False, clear_screen=True, inplace=False):
    global _ui_line_count
    lines = build_ui_lines(total_claims, current_claim, true_claims, false_claims, cat_metrics, phase)
    ui = "\n".join(lines)

    if inplace and _ui_line_count > 0:
        # move cursor up to overwrite same block
        sys.stdout.write(f"\033[{_ui_line_count}A")
        sys.stdout.write(ui + "\n")
    elif clear_screen:
        os.system('cls' if os.name == 'nt' else 'clear')
        sys.stdout.write(ui + "\n")
    else:
        sys.stdout.write(ui + "\n")

    _ui_line_count = len(lines)
    sys.stdout.flush()

    if wait_at_end:
        try:
            input("\n >>> Execution Complete. Press Enter to close window safely... ")
        except EOFError:
            pass

def run_evaluation(is_alone=True, inplace=False):
    global _ui_line_count
    _ui_line_count = 0
    df = pd.read_csv(os.path.join(DATASET_DIR, 'sample_claims.csv'))
    total = len(df)
    results = []
    true_claims = 0
    false_claims = 0
    cat_metrics = {
        'car': {'total': 0, 'true': 0, 'false': 0},
        'package': {'total': 0, 'true': 0, 'false': 0},
        'laptop': {'total': 0, 'true': 0, 'false': 0}
    }

    # First draw: always clear screen fresh
    draw_ui(total, 0, true_claims, false_claims, cat_metrics,
            phase="Evaluation (Sample Claims)", clear_screen=True, inplace=False)

    for idx, row in df.iterrows():
        res = evaluate_claim(row)
        res['user_id'] = row['user_id']
        results.append(res)

        category = get_category(row['claim_object'])
        cat_metrics[category]['total'] += 1

        val = res.get('evidence_standard_met', 'false')
        if str(val).lower() == 'true' or val is True:
            true_claims += 1
            cat_metrics[category]['true'] += 1
        else:
            false_claims += 1
            cat_metrics[category]['false'] += 1

        draw_ui(total, idx + 1, true_claims, false_claims, cat_metrics,
                phase="Evaluation (Sample Claims)", inplace=True)
        time.sleep(1.2)

    res_df = pd.DataFrame(results)
    res_df.to_csv('eval_results.csv', index=False)

    # Print final eval state permanently (no inplace — let it stay)
    draw_ui(total, total, true_claims, false_claims, cat_metrics,
            phase="DONE - Evaluation complete. eval_results.csv saved.",
            wait_at_end=is_alone, inplace=True)

    return {'total': total, 'true': true_claims, 'false': false_claims, 'cat': cat_metrics}

def run_inference(is_alone=True, inplace=False):
    global _ui_line_count
    if not inplace:
        _ui_line_count = 0
    df = pd.read_csv(os.path.join(DATASET_DIR, 'claims.csv'))
    total = len(df)
    results = []
    true_claims = 0
    false_claims = 0
    cat_metrics = {
        'car': {'total': 0, 'true': 0, 'false': 0},
        'package': {'total': 0, 'true': 0, 'false': 0},
        'laptop': {'total': 0, 'true': 0, 'false': 0}
    }

    # First draw: if inplace=False, clear screen; if inplace=True, print below
    draw_ui(total, 0, true_claims, false_claims, cat_metrics,
            phase="Inference (Test Claims)", clear_screen=not inplace, inplace=False)

    for idx, row in df.iterrows():
        res = evaluate_claim(row)

        category = get_category(row['claim_object'])
        cat_metrics[category]['total'] += 1

        val = res.get('evidence_standard_met', 'false')
        if str(val).lower() == 'true' or val is True:
            true_claims += 1
            cat_metrics[category]['true'] += 1
        else:
            false_claims += 1
            cat_metrics[category]['false'] += 1

        out_row = {
            'user_id': row['user_id'],
            'image_paths': row['image_paths'],
            'user_claim': row['user_claim'],
            'claim_object': row['claim_object'],
            'evidence_standard_met': str(val).lower(),
            'evidence_standard_met_reason': res.get('evidence_standard_met_reason', ''),
            'risk_flags': res.get('risk_flags', 'none'),
            'issue_type': res.get('issue_type', 'unknown'),
            'object_part': res.get('object_part', 'unknown'),
            'claim_status': res.get('claim_status', 'not_enough_information'),
            'claim_status_justification': res.get('claim_status_justification', ''),
            'supporting_image_ids': res.get('supporting_image_ids', 'none'),
            'valid_image': res.get('valid_image', 'false'),
            'severity': res.get('severity', 'unknown'),
        }
        results.append(out_row)

        draw_ui(total, idx + 1, true_claims, false_claims, cat_metrics,
                phase="Inference (Test Claims)", inplace=True)
        time.sleep(1.2)

    res_df = pd.DataFrame(results)
    res_df.to_csv('output.csv', index=False)

    draw_ui(total, total, true_claims, false_claims, cat_metrics,
            phase="DONE - Inference complete. output.csv generated.",
            wait_at_end=True, inplace=True)

if __name__ == "__main__":
    print("=============================================")
    print("   HackerRank Orchestrate Execution Menu     ")
    print("=============================================")
    print("1. Run Evaluation Only (20 Sample Claims)")
    print("2. Run Final Inference Only (44 Test Claims)")
    print("3. Run Both Back-to-Back")
    print("=============================================")

    choice = input("Enter your choice (1, 2, or 3): ").strip()

    if choice == "1":
        run_evaluation(is_alone=True)
    elif choice == "2":
        run_inference(is_alone=True)
    elif choice == "3":
        # Evaluation runs, overwrites itself in place each update
        run_evaluation(is_alone=False)
        # Inference prints BELOW the final evaluation block, then overwrites itself in place
        run_inference(is_alone=True, inplace=True)
    else:
        print("\nInvalid selection. Running Final Inference (44 claims) by default...")
        time.sleep(1.5)
        run_inference(is_alone=True)

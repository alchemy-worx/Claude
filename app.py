import streamlit as st
import google.generativeai as genai
from PIL import Image
import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
# 1. STREAMLIT & GEMINI CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Email QA Auditor", layout="wide")

# Fetch API key securely from Streamlit Secrets
api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    st.error("Missing GEMINI_API_KEY in Streamlit Secrets.")
    st.stop()

genai.configure(api_key=api_key)

# -----------------------------------------------------------------------------
# 2. MODEL EXECUTION ENGINE (Gemini 3.8 Flash Standard)
# -----------------------------------------------------------------------------
def run_gemini_audit(prompt_payload):
    """Executes audit using active 3.x Flash series models with failover."""
    candidate_models = [
        'gemini-3.8-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.5-flash'
    ]
    
    last_exception = None
    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_payload)
            return response
        except Exception as e:
            last_exception = e
            continue
            
    raise last_exception

# -----------------------------------------------------------------------------
# 3. KNOWLEDGE BASE & SYSTEM PROMPT
# -----------------------------------------------------------------------------
ESP_KNOWLEDGE_BASE = """
=== ESP SEGMENT & KEYWORD KNOWLEDGE BASE ===
1. KLAVIYO DEFINITIONS
- Activity Metrics: Opened Email, Clicked Email, Active on Site, Placed Order.
- Operators: at least once, in the last X days.
- Custom: Loyalty tier, VIP status.

2. ATTENTIVE DEFINITIONS
- SMS/Email Activity: Subscribed to text/email, Clicked link.
- Custom Attributes: Loyalty tier, VIP tier, Customer status.

3. LISTRAK / NEXGEN DEFINITIONS
- Contact Behavior: Contact Has Purchased (Buyer), Number of Orders.
- System Fields: Last Open/Click/Send Date, Subscribe Date.

4. OMNISEND DEFINITIONS
- Engagement: Clicked on message, Opened message, Opted in.
- Computed Traits: Average Order Value, Total Spent.

5. EPSILON & ACOUSTIC DEFINITIONS
- Segments: Email Engaged, Email Inactive, Abandoned Cart.
=============================================
"""

SYSTEM_PROMPT = """
You are an elite Digital Marketing & Email Campaign QA Auditor. Perform a rigorous, multi-point audit comparing campaign assets against the provided Source of Truth brief.

DYNAMIC AUDIT MODES:

MODE A: PRE-SCHEDULING QA (NO ESP SCHEDULING ASSET PROVIDED)
- If the user DOES NOT provide an ESP Scheduling Screenshot/PDF, assume they are QA'ing assets BEFORE building or scheduling in the ESP.
- Perform all creative and textual checks (Subject Line/Pre-header alignment between brief and creative mockup, Visual Layout, Copy & Formatting, Link Pings if URL provided).
- Explicitly mark ESP-dependent checks (Send Date & Schedule Audit, ESP Segment Matching, Audience Count Audit) as "N/A - Pre-Scheduling QA (No ESP Asset Provided)".
- DO NOT flag missing ESP data as a CRITICAL FAIL in Pre-Scheduling Mode.

MODE B: POST-SCHEDULING AUDIT (ESP SCHEDULING ASSET PROVIDED)
- If an ESP Scheduling Screenshot/PDF IS provided, perform a full multi-point audit including schedule timing, line-by-line segment translation, suppression matching, and audience count verification.

STRICT AUDIT RULES & GUARDRAILS:

1. ZERO LINK HALLUCINATION:
   - If no live preview URL or programmatic link data is provided, explicitly state "N/A - No Preview URL provided" under Links & CTAs.
   - NEVER invent, guess, or hallucinate HTTP 404 errors or scanned links.

2. GROSS VS. NET AUDIENCE COUNTS:
   - The segment count provided in the brief is usually the GROSS count. The audience count in the ESP schedule is the NET count (Gross minus Suppressions).
   - Therefore, the ESP count will almost ALWAYS be lower than the brief count. This is NORMAL.
   - Do NOT flag a lower ESP count as a failure. ONLY flag an anomaly if the ESP count is mysteriously HIGHER than the gross segment.

3. FUZZY OCR MATCHING (SUPPRESSIONS):
   - Screenshots of ESP suppression lists are often blurry. Use fuzzy matching to align exclusions in the image with suppressions requested in the brief.

4. CONVERSATIONAL SEGMENT TRANSLATION:
   - Refer strictly to the provided ESP KNOWLEDGE BASE to mentally translate conversational phrases into logical ESP segment conditions before checking the screenshot.

REQUIRED OUTPUT FORMAT:

### 🚦 Overall Audit Status
[PASS | PASS WITH MINOR EDITS | CRITICAL FAIL]

### 🚨 Discrepancy Matrix
| Audit Category | Element | Expected (Source of Truth) | Found (ESP/Schedule) | Severity (High/Med/Low) |
| :--- | :--- | :--- | :--- | :--- |

### 📋 Detailed Audit Breakdown
- **Send Date & Schedule Audit:** [Pass / Specific Issues / N/A - Pre-Scheduling QA]
- **Subject Line & Pre-header Audit:** [Pass / Specific Issues]
- **Visuals & Layout:** [Pass / Specific Issues]
- **Copy & Formatting:** [Pass / Specific Issues]
- **Links & CTAs:** [Pass / Specific Issues / N/A]
- **Segmentation & Suppressions (Itemized):** [List every target segment and suppression / N/A - Pre-Scheduling QA]
- **Audience Count Audit:** [Note expected drop due to suppressions / N/A - Pre-Scheduling QA]

### 🔧 Actionable Fix List
[Numbered list of exact changes required]
"""

# -----------------------------------------------------------------------------
# 4. HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def inspect_preview_url(url):
    """Programmatically pings links and inspects preview HTML."""
    if not url or url.strip() == "":
        return "No URL provided."
        
    report = []
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = soup.find_all('a', href=True)
        report.append(f"Total Links Found: {len(links)}")
        
        broken_links = []
        for a in links[:15]: 
            href = a['href']
            if href.startswith('http'):
                try:
                    r = requests.head(href, allow_redirects=True, timeout=3)
                    if r.status_code >= 400:
                        broken_links.append(f"{href} (Status: {r.status_code})")
                except:
                    pass
        if broken_links:
            report.append(f"Potential Dead Links: {', '.join(broken_links)}")
        else:
            report.append("HTTP Link Pings: All tested links returned valid status.")
            
    except Exception as e:
        report.append(f"Could not scrape URL: {str(e)}")
    return "\n".join(report)

def prepare_asset_payload(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.type == "application/pdf":
        return {"mime_type": "application/pdf", "data": uploaded_file.getvalue()}
    else:
        return Image.open(uploaded_file)

# -----------------------------------------------------------------------------
# 5. STREAMLIT UI & AUDIT ENGINE
# -----------------------------------------------------------------------------
st.title("📧 Email Campaign QA Auditor")
st.write("Upload campaign assets and fill in the Source of Truth brief below for an automated multi-point audit.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Campaign Brief (Source of Truth)")
    creative_mockup = st.file_uploader("Approved Creative Mockup (PNG, JPG, PDF) *", type=["png", "jpg", "jpeg", "pdf"])
    
    task_title = st.text_input("ClickUp Task Title *")
    send_datetime = st.text_input("Send Date / Time *")
    subject_lines = st.text_area("Subject Line(s) *", height=80)
    preheaders = st.text_area("Pre-header(s) *", height=80)
    segments = st.text_area("Segments & Suppressions *", height=120)
    other_notes = st.text_area("Other Notes (Optional)", height=80)

with col2:
    st.subheader("2. ESP Deployment Assets (Optional for Pre-Scheduling QA)")
    preview_url = st.text_input("Live ESP Test Preview URL (Optional)")
    esp_schedule = st.file_uploader("ESP Scheduling Screenshot/PDF (Segments & Audience Counts) - Optional", type=["png", "jpg", "jpeg", "pdf"])

if st.button("🚀 Run Campaign Audit", type="primary"):
    missing_fields = []
    if not creative_mockup: missing_fields.append("Approved Creative Mockup")
    if not task_title.strip(): missing_fields.append("ClickUp Task Title")
    if not send_datetime.strip(): missing_fields.append("Send Date / Time")
    if not subject_lines.strip(): missing_fields.append("Subject Line(s)")
    if not preheaders.strip(): missing_fields.append("Pre-header(s)")
    if not segments.strip(): missing_fields.append("Segments & Suppressions")

    if missing_fields:
        st.warning(f"Please fill in all required source-of-truth fields: {', '.join(missing_fields)}")
    else:
        with st.spinner("Processing assets and running campaign audit..."):
            try:
                prompt_payload = [ESP_KNOWLEDGE_BASE, SYSTEM_PROMPT]
                
                brief_payload = f"""
SOURCE OF TRUTH BRIEF DATA:
- ClickUp Task Title: {task_title}
- Target Send Date/Time: {send_datetime}
- Approved Subject Line(s): {subject_lines}
- Approved Pre-header(s): {preheaders}
- Approved Segments & Suppressions: {segments}
- Additional Notes: {other_notes if other_notes.strip() else 'None provided'}
"""
                prompt_payload.append(brief_payload)

                # 1. Add Creative Mockup
                mockup_payload = prepare_asset_payload(creative_mockup)
                if mockup_payload:
                    prompt_payload.append("\nAPPROVED CREATIVE MOCKUP ASSET:")
                    prompt_payload.append(mockup_payload)
                
                # 2. Add Live Preview URL & Scraped Data (Optional)
                if preview_url and preview_url.strip() != "":
                    technical_link_data = inspect_preview_url(preview_url)
                    prompt_payload.append(f"\nPROGRAMMATIC LINK & HTML AUDIT DATA:\nURL: {preview_url}\n{technical_link_data}")
                else:
                    prompt_payload.append("\nPROGRAMMATIC LINK AUDIT DATA: None provided. Do not hallucinate links.")
                
                # 3. Add ESP Scheduling Asset (Optional)
                if esp_schedule:
                    schedule_payload = prepare_asset_payload(esp_schedule)
                    if schedule_payload:
                        prompt_payload.append("\nESP SCHEDULING & AUDIENCE ASSET:")
                        prompt_payload.append(schedule_payload)
                        prompt_payload.append("\nAUDIT MODE: Post-Scheduling Mode (Perform complete ESP matching).")
                else:
                    prompt_payload.append("\nESP SCHEDULING & AUDIENCE ASSET: None provided.")
                    prompt_payload.append("\nAUDIT MODE: Pre-Scheduling Mode Active. Skip ESP schedule/segment matching and mark those sections as N/A - Pre-Scheduling QA.")
                
                # 4. Execute Audit
                response = run_gemini_audit(prompt_payload)
                
                # Render Results
                st.markdown("---")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"An error occurred during the audit execution: {str(e)}")

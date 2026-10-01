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
# 3. SYSTEM PROMPT (Strict Source of Truth & Auditor Rules)
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are an elite Digital Marketing & Email Campaign QA Auditor. Perform a rigorous, multi-point audit comparing the live campaign assets against the provided Source of Truth brief.

STRICT AUDIT RULES:

1. SOURCE OF TRUTH ENFORCEMENT:
   - The user has provided explicit brief inputs (Task Title, Send Date/Time, Subject Lines, Pre-headers, Target Segments).
   - Compare ALL ESP assets, URLs, and previews directly against this exact source of truth.
   - DO NOT automatically 'PASS' any check if the ESP schedule or creative asset lacks matching data or contradicts the source-of-truth brief. Flag discrepancies immediately as HIGH SEVERITY.

2. ITEMIZED SEGMENTS & SUPPRESSIONS:
   - DO NOT sum, aggregate, or summarize segment numbers or suppression counts into single totals.
   - List EVERY target segment and EVERY suppression rule individually, line-by-line.
   - Compare each line item directly against the provided brief segments.

3. AUDIENCE COUNT ANOMALY DETECTION:
   - Extract expected audience numbers from the brief/notes and actual counts from the ESP schedule asset.
   - Explicitly report both numbers and flag ANY variance, unexpected audience drop, or count anomaly as a HIGH SEVERITY issue.

4. SUBJECT LINE & PRE-HEADER AUDIT:
   - Cross-reference the brief's Subject Line(s) and Pre-header(s) word-for-word against the live ESP preview metadata/headers.

5. CONTEXTUAL OCR & SPELLING PRECISION:
   - Cross-reference ambiguous or low-resolution text in screenshots/PDFs against the brief context to prevent OCR mistakes (e.g., verify platform names like 'Listrak' vs 'Rentrak').

6. VISUAL TRUNCATION CALIBRATION:
   - Carefully review full-length email scroll mockups against ESP previews.
   - DO NOT flag an email preview as 'truncated' or 'missing sections' unless visual content is genuinely cut off at the bottom or absent from the layout.

REQUIRED OUTPUT FORMAT:

### 🚦 Overall Audit Status
[PASS | PASS WITH MINOR EDITS | CRITICAL FAIL]

### 🚨 Discrepancy Matrix
| Audit Category | Element | Expected (Source of Truth) | Found (ESP/Schedule) | Severity (High/Med/Low) |
| :--- | :--- | :--- | :--- | :--- |

### 📋 Detailed Audit Breakdown
- **Send Date & Schedule Audit:** [Pass / Specific Issues]
- **Subject Line & Pre-header Audit:** [Pass / Specific Issues]
- **Visuals & Layout:** [Pass / Specific Issues]
- **Copy & Formatting:** [Pass / Specific Issues]
- **Links & CTAs:** [Pass / Specific Issues]
- **Segmentation & Suppressions (Itemized):** [List every target segment and suppression line-by-line]
- **Audience Count Audit:** [Brief Count vs. ESP Schedule Count & Variance Analysis]

### 🔧 Actionable Fix List
[Numbered list of exact changes required]
"""

# -----------------------------------------------------------------------------
# 4. HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def inspect_preview_url(url):
    """Programmatically pings links and inspects preview HTML."""
    report = []
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = soup.find_all('a', href=True)
        report.append(f"Total Links Found: {len(links)}")
        
        broken_links = []
        for a in links[:15]:  # Sample first 15 links
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
    """Prepares images or PDFs for Gemini using native API handling."""
    if uploaded_file is None:
        return None
    
    if uploaded_file.type == "application/pdf":
        return {
            "mime_type": "application/pdf",
            "data": uploaded_file.getvalue()
        }
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
    creative_mockup = st.file_uploader("Approved Creative Mockup (PNG, JPG, PDF)", type=["png", "jpg", "jpeg", "pdf"])
    
    task_title = st.text_input("ClickUp Task Title *")
    send_datetime = st.text_input("Send Date / Time *")
    subject_lines = st.text_area("Subject Line(s) *", height=80)
    preheaders = st.text_area("Pre-header(s) *", height=80)
    segments = st.text_area("Segments & Suppressions *", height=120)
    other_notes = st.text_area("Other Notes (Optional)", height=80)

with col2:
    st.subheader("2. ESP Deployment Assets")
    preview_url = st.text_input("Live ESP Test Preview URL")
    esp_schedule = st.file_uploader("ESP Scheduling Screenshot/PDF (Segments & Audience Counts)", type=["png", "jpg", "jpeg", "pdf"])

if st.button("🚀 Run Campaign Audit", type="primary"):
    # Validate required fields
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
                prompt_payload = [SYSTEM_PROMPT]
                
                # Formatted Source of Truth payload
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
                
                # 2. Add Live Preview URL & Scraped Data
                if preview_url:
                    technical_link_data = inspect_preview_url(preview_url)
                    prompt_payload.append(f"\nPROGRAMMATIC LINK & HTML AUDIT DATA:\nURL: {preview_url}\n{technical_link_data}")
                
                # 3. Add ESP Scheduling Asset
                if esp_schedule:
                    schedule_payload = prepare_asset_payload(esp_schedule)
                    if schedule_payload:
                        prompt_payload.append("\nESP SCHEDULING & AUDIENCE ASSET:")
                        prompt_payload.append(schedule_payload)
                
                # 4. Execute Audit
                response = run_gemini_audit(prompt_payload)
                
                # Render Results
                st.markdown("---")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"An error occurred during the audit execution: {str(e)}")

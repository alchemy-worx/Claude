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
# 2. MODEL EXECUTION ENGINE (Configured for Gemini 3.8 Flash)
# -----------------------------------------------------------------------------
def run_gemini_audit(prompt_payload):
    """
    Executes audit using active 3.x Flash series models.
    Primary: gemini-3.8-flash (Google's recommended active model)
    """
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
# 3. SYSTEM PROMPT (Auditor Rules & Formatting)
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are an elite Digital Marketing & Email Campaign QA Auditor. Perform a rigorous, multi-point audit comparing the campaign assets provided.

STRICT AUDIT RULES:

1. ITEMIZED SEGMENTS & SUPPRESSIONS:
   - DO NOT sum, aggregate, or summarize segment numbers or suppression counts into single totals.
   - List EVERY target segment and EVERY suppression rule individually, line-by-line.
   - Compare each line item directly against the brief.

2. AUDIENCE COUNT ANOMALY DETECTION:
   - Extract expected audience numbers from the brief and actual counts from the ESP schedule asset.
   - Explicitly report both numbers and flag ANY variance, unexpected audience drop, or count anomaly as a HIGH SEVERITY issue.

3. CONTEXTUAL OCR & SPELLING PRECISION:
   - Cross-reference ambiguous or low-resolution text in screenshots/PDFs against the brief context to prevent OCR mistakes (e.g., verify platform names like 'Listrak' vs 'Rentrak').

4. VISUAL TRUNCATION CALIBRATION:
   - Carefully review full-length email scroll mockups against ESP previews.
   - DO NOT flag an email preview as 'truncated' or 'missing sections' unless visual content is genuinely cut off at the bottom or absent from the layout. Verify full vertical scroll height before flagging.

REQUIRED OUTPUT FORMAT:

### 🚦 Overall Audit Status
[PASS | PASS WITH MINOR EDITS | CRITICAL FAIL]

### 🚨 Discrepancy Matrix
| Audit Category | Element | Expected (Brief/Mockup) | Found (ESP/Schedule) | Severity (High/Med/Low) |
| :--- | :--- | :--- | :--- | :--- |

### 📋 Detailed Audit Breakdown
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
st.write("Upload campaign assets below for an automated multi-point audit.")

col1, col2 = st.columns(2)

with col1:
    creative_mockup = st.file_uploader("1. Approved Creative Mockup (PNG, JPG, PDF)", type=["png", "jpg", "jpeg", "pdf"])
    clickup_brief = st.text_area("2. ClickUp Task Brief Text / Notes", height=450)

with col2:
    preview_url = st.text_input("3. Live ESP Test Preview URL")
    esp_schedule = st.file_uploader("4. ESP Scheduling Screenshot/PDF (Segments & Audience Counts)", type=["png", "jpg", "jpeg", "pdf"])

if st.button("🚀 Run Campaign Audit", type="primary"):
    if not (creative_mockup and clickup_brief):
        st.warning("Please provide at least the Creative Mockup and ClickUp Brief.")
    else:
        with st.spinner("Processing assets and running campaign audit..."):
            try:
                prompt_payload = [SYSTEM_PROMPT]
                
                # 1. Add Creative Mockup
                mockup_payload = prepare_asset_payload(creative_mockup)
                if mockup_payload:
                    prompt_payload.append("\nAPPROVED CREATIVE MOCKUP:")
                    prompt_payload.append(mockup_payload)
                
                # 2. Add ClickUp Brief Text
                prompt_payload.append(f"\nCLICKUP BRIEF TEXT:\n{clickup_brief}")
                
                # 3. Add Live Preview URL & Scraped Data
                if preview_url:
                    technical_link_data = inspect_preview_url(preview_url)
                    prompt_payload.append(f"\nPROGRAMMATIC LINK & HTML AUDIT DATA:\nURL: {preview_url}\n{technical_link_data}")
                
                # 4. Add ESP Scheduling Asset
                if esp_schedule:
                    schedule_payload = prepare_asset_payload(esp_schedule)
                    if schedule_payload:
                        prompt_payload.append("\nESP SCHEDULING & AUDIENCE ASSET:")
                        prompt_payload.append(schedule_payload)
                
                # 5. Execute Audit with Gemini 3.8 Flash
                response = run_gemini_audit(prompt_payload)
                
                # Render Audit Results
                st.markdown("---")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"An error occurred during the audit execution: {str(e)}")

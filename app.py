import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image
import io
import zipfile
import docx
import urllib.parse
from datetime import datetime

st.set_page_config(page_title="Campaign QA Auditor", layout="wide")
st.title("📋 Campaign QA Auditor")

# API Key handling
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Current Year Context
CURRENT_YEAR = datetime.now().year

# Inputs
st.subheader("Campaign Inputs")
creative_file = st.file_uploader("1. Upload Approved Creative Mockup (PNG, JPG, PDF)", type=["png", "jpg", "jpeg", "pdf"])
listrak_url = st.text_input("2. Listrak / ESP Preview Link")
clickup_text = st.text_area("3. ClickUp Task Brief Text", height=150)
uploaded_file = st.file_uploader("4. Upload ESP Scheduling Screenshot, PDF, or Word Doc", type=["png", "jpg", "jpeg", "pdf", "docx"])

SOCIAL_DOMAINS = ['facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'pinterest.com', 'youtube.com', 'tiktok.com']

if st.button("🚀 Run QA Audit", type="primary"):
    if not api_key:
        st.error("Please provide a Gemini API Key.")
        st.stop()
    if not listrak_url or not clickup_text or not uploaded_file:
        st.warning("Please fill in the required inputs (Preview Link, ClickUp Brief, and ESP Schedule Document).")
        st.stop()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.6-flash')

    extracted_data = []
    image_alt_audit = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    # Step 1: HTML Crawling & Alt-Tag Extraction (Inside auto-clearing spinner)
    with st.spinner("🔍 Crawling live links, extracting image <alt> tags, and auditing button destinations..."):
        try:
            resp = requests.get(listrak_url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Audit all <img> tags for missing or blank alt attributes
            images = soup.find_all('img')
            for idx, img in enumerate(images, 1):
                src = img.get('src', 'N/A')
                alt = img.get('alt')
                if alt is None:
                    image_alt_audit.append(f"Image #{idx} ({src}): MISSING ALT ATTRIBUTE")
                elif alt.strip() == "":
                    image_alt_audit.append(f"Image #{idx} ({src}): EMPTY ALT ATTRIBUTE (alt=\"\")")
                else:
                    image_alt_audit.append(f"Image #{idx} ({src}): alt=\"{alt.strip()}\"")

            # Audit <a> links
            links = soup.find_all('a')
            for idx, link in enumerate(links, 1):
                href = link.get('href', '').strip()
                text = link.get_text(strip=True)
                img = link.find('img')
                alt = img.get('alt', '').strip() if img else ''
                label = text or alt or "Unlabeled Image/Button"
                
                if not href or href == '#' or href.startswith('javascript:'):
                    extracted_data.append({"id": idx, "label": label, "final_url": "NONE", "status": "NO LINK / MISSING HREF"})
                    continue
                    
                if href.startswith('mailto:') or href.startswith('tel:'):
                    extracted_data.append({"id": idx, "label": label, "final_url": href, "status": "WORKING (Protocol Link)"})
                    continue

                parsed = urllib.parse.urlparse(href)
                domain = parsed.netloc.lower()

                # Catch Social Media Links and prevent 400/403/429 false positives
                if any(sd in domain for sd in SOCIAL_DOMAINS):
                    extracted_data.append({"id": idx, "label": label, "final_url": href, "status": "WORKING (Social Media Link)"})
                    continue

                try:
                    res = requests.get(href, headers=headers, allow_redirects=True, timeout=8)
                    if res.status_code == 200:
                        status = "WORKING (200)"
                    elif res.status_code == 404:
                        status = "BROKEN (404 Page Not Found)"
                    elif res.status_code in [400, 403, 429]:
                        status = "PROTECTED / FIREWALL (Valid in browser)"
                    else:
                        status = f"HTTP STATUS {res.status_code}"
                    final_url = res.url
                except Exception:
                    final_url = href
                    status = "ERROR / TIMEOUT"

                extracted_data.append({"id": idx, "label": label, "final_url": final_url, "status": status})
        except Exception as e:
            st.error(f"Error fetching preview link: {e}")

    # Step 2: Build Strict Prompt
    prompt = f"""
    You are a strict, zero-tolerance Email Campaign QA Auditor.

    # SPECIAL BUSINESS RULES:
    1. **DATE YEAR DEFAULT:** If a date in the ClickUp brief lacks an explicit year (e.g. "8/24" or "08/24"), ASSUME IT MEANS THE CURRENT YEAR ({CURRENT_YEAR}). Do NOT flag a year mismatch if the ESP scheduled year is {CURRENT_YEAR}.
    2. **CREATIVE VS BUILD MATCH:** Compare the ESP preview build visual against the Approved Creative (if attached). Flag any discrepancy in design, imagery, layout, or copy.
    3. **IMAGE ALT ATTRIBUTE CHECK:** Review the extracted `<img>` alt tags below. Every image MUST have an `alt` attribute. Flag any image missing an `alt` attribute, having an empty `alt=""`, or having `alt` text that mismatches the actual image context (e.g., Facebook icon with `alt="Instagram"` or Eyeglasses with `alt="Sunglasses"`).
    4. **IGNORE SOCIAL MEDIA STATUS 400/403/429:** Links marked as "WORKING (Social Media Link)" or "PROTECTED / FIREWALL" are valid and must NOT be flagged as broken.

    # MANDATORY CHECKPOINTS:
    - Segment Mismatches / Missing Segments / Extra Segments
    - Missing or Incorrect Suppressions
    - Send Date / Time / Timezone
    - Campaign Naming Conventions
    - A/B Test Configuration Mismatches
    - Subject Line & Preheader Exact Match
    - Typos, Spelling, and Grammar
    - Unreplaced Placeholders (e.g., XXXXX, PROMOCODE, [NAME])
    - Broken Links (404s) & Unlinked CTAs
    - Misdirected Links & Alt Text Context Mismatches

    # AUDIT INPUTS:
    - **ClickUp Brief Text:**
    {clickup_text}

    - **Extracted HTML Image Alt Tags:**
    {image_alt_audit}

    - **Live Link Crawl Results:**
    {extracted_data}

    - **ESP Scheduling Screenshot / Document:** Attached below.

    # MANDATORY RESPONSE FORMAT:
    Do NOT write setup text. Start Line 1 with "### Part 1: Master QA Status Banner".

    ### Part 1: Master QA Status Banner
    [🟢 [PASS] - All deployment settings, copy, and live links are verified. OR 🔴 [FAIL: ISSUES DETECTED]]
    * [List every single failure item found in bold]

    ### Part 2: Deployment & Schedule Verification Table
    | Parameter | Planned Specs (ClickUp) | Actual Scheduled (ESP) | Match Status |
    | :--- | :--- | :--- | :--- |
    | **Creative vs Build Match** | [Approved Mockup] | [Preview Build] | OK / ❌ Mismatch |
    | **Campaign Name** | [Name] | [Name] | OK / ❌ Mismatch |
    | **A/B Test Setup** | [Single / A/B] | [Single / A/B] | OK / ❌ Mismatch |
    | **Target Segments** | [Segments] | [Segments] | OK / ❌ Missing or Extra |
    | **Suppressions** | [Suppressed Lists] | [Suppressed Lists] | OK / ❌ Missing or Wrong |
    | **Send Date & Time** | [Date @ Time Timezone] | [Date @ Time Timezone] | OK / ❌ Mismatch |
    | **Subject Line** | [Brief Subject] | [Actual Subject] | OK / ❌ Mismatch |
    | **Preheader Text** | [Brief Preheader] | [Actual Preheader] | OK / ❌ Mismatch |

    ### Part 3: Build, Copy, Link & Image Alt Audit
    * **Creative Visual Alignment:** [State whether build visually matches approved creative mockup.]
    * **Image <alt> Tag Audit:** [Flag missing/empty alt attributes or alt text mismatches, or state "All image alt tags verified."]
    * **Broken & Dead Links:** [List true 404s/Timeouts or state "All live links active."]
    * **Misdirected Links:** [Flag mismatched destinations or state "All CTA destinations match context."]
    * **Unlinked Buttons (Missing Href):** [List buttons with missing links or state "None."]
    * **Placeholders & Dynamic Code Check:** [Flag unreplaced code or state "None detected."]
    * **Typos & Copy Errors:** [List typos or state "None."]

    ### Part 4: Required Action Items
    * [Numbered list of exact fixes required before sending]
    """

    # Process File Inputs (Creative + Schedule Document)
    multimodal_inputs = [prompt]

    if creative_file:
        c_type = creative_file.name.split('.')[-1].lower()
        if c_type in ['png', 'jpg', 'jpeg']:
            multimodal_inputs.append("Approved Creative Visual Mockup:")
            multimodal_inputs.append(Image.open(creative_file))
        elif c_type == 'pdf':
            multimodal_inputs.append("Approved Creative Document (PDF):")
            multimodal_inputs.append({"mime_type": "application/pdf", "data": creative_file.getvalue()})

    s_type = uploaded_file.name.split('.')[-1].lower()
    if s_type in ['png', 'jpg', 'jpeg']:
        multimodal_inputs.append("ESP Scheduling Screenshot:")
        multimodal_inputs.append(Image.open(uploaded_file))
    elif s_type == 'pdf':
        multimodal_inputs.append("ESP Scheduling Document (PDF):")
        multimodal_inputs.append({"mime_type": "application/pdf", "data": uploaded_file.getvalue()})
    elif s_type == 'docx':
        doc = docx.Document(uploaded_file)
        docx_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if docx_text:
            multimodal_inputs.append(f"ESP Scheduling Text from DOCX:\n{docx_text}")
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as z:
            for filename in z.namelist():
                if filename.startswith('word/media/'):
                    try:
                        multimodal_inputs.append(Image.open(io.BytesIO(z.read(filename))))
                    except Exception:
                        pass

    # Step 3: Run Gemini AI Analysis (Inside auto-clearing spinner)
    with st.spinner("🤖 Analyzing campaign assets with Gemini AI..."):
        try:
            response = model.generate_content(multimodal_inputs)
            st.markdown("---")
            st.markdown(response.text)
        except Exception as e:
            st.error(f"Gemini API Error: {e}")

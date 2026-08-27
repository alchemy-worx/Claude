import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image
import io
import zipfile
import docx
import urllib.parse

st.set_page_config(page_title="Campaign QA Auditor", layout="wide")
st.title("📋 Campaign QA Auditor")

# API Key handling
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Inputs
listrak_url = st.text_input("1. Listrak / ESP Preview Link")
clickup_text = st.text_area("2. ClickUp Task Brief Text", height=150)
uploaded_file = st.file_uploader("3. Upload ESP Scheduling Screenshot, PDF, or Word Doc", type=["png", "jpg", "jpeg", "pdf", "docx"])

SOCIAL_DOMAINS = ['facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'pinterest.com', 'youtube.com', 'tiktok.com']

if st.button("🚀 Run QA Audit", type="primary"):
    if not api_key:
        st.error("Please provide a Gemini API Key.")
        st.stop()
    if not listrak_url or not clickup_text or not uploaded_file:
        st.warning("Please fill in all 3 inputs before running the audit.")
        st.stop()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.6-flash')

    # Step 1: Smart Link Crawling
    st.info("🔍 Crawling live links and analyzing button destinations...")
    extracted_data = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        resp = requests.get(listrak_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a')
        
        for idx, link in enumerate(links, 1):
            href = link.get('href', '').strip()
            text = link.get_text(strip=True)
            img = link.find('img')
            alt = img.get('alt', '').strip() if img else ''
            label = text or alt or "Unlabeled Image/Button"
            
            # Catch unlinked CTAs or placeholder anchors
            if not href or href == '#' or href.startswith('javascript:'):
                extracted_data.append({"id": idx, "label": label, "final_url": "NONE", "status": "NO LINK / MISSING HREF"})
                continue
                
            if href.startswith('mailto:') or href.startswith('tel:'):
                extracted_data.append({"id": idx, "label": label, "final_url": href, "status": "WORKING (Protocol Link)"})
                continue

            parsed = urllib.parse.urlparse(href)
            domain = parsed.netloc.lower()

            # Catch Social Media Links
            if any(sd in domain for sd in SOCIAL_DOMAINS):
                extracted_data.append({"id": idx, "label": label, "final_url": href, "status": "WORKING (Social Media Link)"})
                continue

            try:
                res = requests.get(href, headers=headers, allow_redirects=True, timeout=8)
                if res.status_code == 200:
                    status = "WORKING (200)"
                elif res.status_code == 404:
                    status = "BROKEN (404 Page Not Found)"
                elif res.status_code in [403, 429]:
                    status = "FIREWALL / PROTECTED (Likely valid in browser)"
                else:
                    status = f"HTTP STATUS {res.status_code}"
                final_url = res.url
            except Exception:
                final_url = href
                status = "ERROR / TIMEOUT"

            extracted_data.append({"id": idx, "label": label, "final_url": final_url, "status": status})
    except Exception as e:
        st.error(f"Error fetching preview link: {e}")

    # Step 2: Comprehensive 14-Point QA Prompt
    prompt = f"""
    You are a strict, zero-tolerance Email Campaign QA Auditor. 
    Audit the campaign against the 14 mandatory QA checkpoints below.

    # 14 MANDATORY CHECKPOINTS TO AUDIT:
    1. **Segment Mismatches:** Compare segments requested in ClickUp vs booked in ESP.
    2. **Missing Segments:** Check if any segment requested in ClickUp is missing from the ESP booking.
    3. **Extra Segments:** Check if any segment is booked in ESP that was NOT requested in ClickUp.
    4. **Incorrect Suppressions:** Check if wrong suppression lists were added.
    5. **Missing Suppressions:** Check if any required suppression list (e.g., 7-day buyers) is missing.
    6. **Incorrect Send Date / Time / Timezone:** Compare scheduled send time vs brief.
    7. **Incorrect Campaign Name:** Check for typos or date mismatches in campaign naming conventions (e.g. name contains date 0624 but scheduled send is 0825).
    8. **A/B Test Verification:** If brief requests A/B testing (variants A/B, send time tests), confirm ESP booking is explicitly configured as A/B test with matching variants/times.
    9. **Subject Line & Preheader Match:** Verify exact wording between brief and booked settings.
    10. **Typos & Grammar:** Scan subject line, preheader, and email visual body for spelling/grammar errors.
    11. **Forgotten Dynamic Codes / Placeholders:** Scan body text for unreplaced placeholders like `XXXXX`, `[FIRSTNAME]`, `PROMOCODE`, `[INSERT LINK]`.
    12. **Broken Links:** Flag true 404s or dead timeouts.
    13. **Incorrect / Misdirected Links:** Check for contextual mismatches (e.g., Facebook icon pointing to Instagram, or "Shop Eyeglasses" CTA pointing to Contacts page).
    14. **Unlinked CTAs:** Flag buttons/images marked as "NO LINK / MISSING HREF".

    # AUDIT INPUTS:
    - **ClickUp Brief Text:**
    {clickup_text}

    - **Live Link Crawl Results:**
    {extracted_data}

    - **ESP Scheduling Screenshot / Document:** Attached below.

    # MANDATORY RESPONSE FORMAT:
    1. Do NOT write setup text or greetings. Start Line 1 with "### Part 1: Master QA Status Banner".
    2. If ALL 14 checks pass: Output "🟢 [PASS] - All deployment settings, copy, and live links are verified."
    3. If ANY check fails: Output "🔴 [FAIL: ISSUES DETECTED]" and bullet list EVERY exact mismatch in bold.

    ### Part 1: Master QA Status Banner
    [🟢 [PASS] or 🔴 [FAIL: ISSUES DETECTED]]
    * [List every single failure item found]

    ### Part 2: Deployment & Schedule Verification Table
    | Parameter | Planned Specs (ClickUp) | Actual Scheduled (ESP) | Match Status |
    | :--- | :--- | :--- | :--- |
    | **Campaign Name** | [Name] | [Name] | OK / ❌ Mismatch |
    | **A/B Test Setup** | [Single / A/B Variants] | [Single / A/B Variants] | OK / ❌ Mismatch |
    | **Target Segments** | [Segments] | [Segments] | OK / ❌ Missing or Extra |
    | **Suppressions** | [Suppressed Lists] | [Suppressed Lists] | OK / ❌ Missing or Wrong |
    | **Send Date & Time** | [Date @ Time Timezone] | [Date @ Time Timezone] | OK / ❌ Mismatch |
    | **Subject Line** | [Brief Subject] | [Actual Subject] | OK / ❌ Mismatch |
    | **Preheader Text** | [Brief Preheader] | [Actual Preheader] | OK / ❌ Mismatch |

    ### Part 3: Build, Copy, Link & Placeholder Audit
    * **Broken & Dead Links:** [List 404s/timeouts or state "All live links active."]
    * **Misdirected Link Mismatches:** [Flag mismatched icons/CTAs or state "All CTA destinations match context."]
    * **Unlinked Buttons (Missing Href):** [List buttons with missing links or state "None."]
    * **Placeholders & Dynamic Code Check:** [Flag unreplaced code like XXXXX, [NAME] or state "None detected."]
    * **Typos & Copy Errors:** [List typos or state "None."]

    ### Part 4: Required Action Items
    * [Numbered list of exact fixes required before sending]
    """

    # Process File Input
    multimodal_inputs = [prompt]
    file_type = uploaded_file.name.split('.')[-1].lower()

    if file_type in ['png', 'jpg', 'jpeg']:
        image = Image.open(uploaded_file)
        multimodal_inputs.append(image)

    elif file_type == 'pdf':
        pdf_part = {
            "mime_type": "application/pdf",
            "data": uploaded_file.getvalue()
        }
        multimodal_inputs.append(pdf_part)

    elif file_type == 'docx':
        doc = docx.Document(uploaded_file)
        docx_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if docx_text:
            multimodal_inputs.append(f"Additional Text from DOCX Document:\n{docx_text}")

        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as z:
            for filename in z.namelist():
                if filename.startswith('word/media/'):
                    image_bytes = z.read(filename)
                    try:
                        img = Image.open(io.BytesIO(image_bytes))
                        multimodal_inputs.append(img)
                    except Exception:
                        pass

    # Step 3: Run Gemini AI Analysis
    st.info("🤖 Analyzing campaign assets against 14 QA rules with Gemini AI...")
    try:
        response = model.generate_content(multimodal_inputs)
        st.markdown("---")
        st.markdown(response.text)
    except Exception as e:
        st.error(f"Gemini API Error: {e}")

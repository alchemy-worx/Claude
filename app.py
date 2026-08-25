import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image
import io
import zipfile
import docx

st.set_page_config(page_title="Campaign QA Auditor", layout="wide")
st.title("📋 Campaign QA Auditor")

# API Key handling
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Inputs
listrak_url = st.text_input("1. Listrak / ESP Preview Link")
clickup_text = st.text_area("2. ClickUp Task Brief Text", height=150)
uploaded_file = st.file_uploader("3. Upload ESP Scheduling Screenshot, PDF, or Word Doc", type=["png", "jpg", "jpeg", "pdf", "docx"])

if st.button("🚀 Run QA Audit", type="primary"):
    if not api_key:
        st.error("Please provide a Gemini API Key.")
        st.stop()
    if not listrak_url or not clickup_text or not uploaded_file:
        st.warning("Please fill in all 3 inputs before running the audit.")
        st.stop()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Step 1: Live Link Crawling
    st.info("🔍 Crawling live links and testing 404 status codes...")
    extracted_data = []
    try:
        resp = requests.get(listrak_url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a')
        for idx, link in enumerate(links, 1):
            href = link.get('href')
            text = link.get_text(strip=True)
            img = link.find('img')
            alt = img.get('alt', '') if img else ''
            label = text or alt or "Button/Image Link"
            
            if not href or href.startswith('#') or href.startswith('mailto:'):
                continue
            try:
                res = requests.get(href, allow_redirects=True, timeout=8)
                final_url = res.url
                status = f"WORKING (200)" if res.status_code == 200 else f"BROKEN ({res.status_code})"
            except Exception:
                final_url = href
                status = "ERROR / TIMEOUT"

            extracted_data.append({"id": idx, "label": label, "final_url": final_url, "status": status})
    except Exception as e:
        st.error(f"Error fetching preview link: {e}")

    # Step 2: Prepare Gemini Audit Prompt
    prompt = f"""
    # Strict Constraints
    1. DO NOT write introductory text or setups.
    2. YOUR RESPONSE MUST START ON LINE 1 WITH "### Part 1: Master QA Status Banner".
    3. IF ALL CHECKS PASS: Output "🟢 [PASS] - All deployment settings, copy, and live links are verified."
    4. IF ANY ISSUE EXISTS: Output "🔴 [FAIL: ISSUES DETECTED]" and bold exact errors below it.

    # Audit Inputs:
    - **ClickUp Brief Text:**
    {clickup_text}

    - **Live Link Crawl Results:**
    {extracted_data}

    - **ESP Scheduling Screenshot / Document:** Attached below.

    # Mandatory Output Format:
    ### Part 1: Master QA Status Banner
    [🟢 [PASS] or 🔴 [FAIL: ISSUES DETECTED]]
    * [Bolded list of failure items if FAIL, or "All parameters verified." if PASS]

    ### Part 3: Build, Copy & Link Relevancy Log
    * **Broken Link / 404 Check:** [Flag any status != WORKING (200)]
    * **CTA Destination Relevancy:** [Verify button label matches destination URL path]
    * **Typos & Copy Errors:** [List typos or state None]

    ### Part 4: Required Action Items
    * [Clear list of fixes needed, or "No action needed. Ready to deploy."]
    """

    # Process File Input (Images, PDFs, or Word Documents)
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
        # Extract text from docx
        doc = docx.Document(uploaded_file)
        docx_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if docx_text:
            multimodal_inputs.append(f"Additional Text from DOCX Document:\n{docx_text}")

        # Extract embedded screenshots/images from docx
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
    st.info("🤖 Analyzing campaign assets with Gemini AI...")
    try:
        response = model.generate_content(multimodal_inputs)
        st.markdown("---")
        st.markdown(response.text)
    except Exception as e:
        st.error(f"Gemini API Error: {e}")

import streamlit as st
from openai import AzureOpenAI
from azure.ai.formrecognizer import DocumentAnalysisClient # type: ignore
from azure.core.credentials import AzureKeyCredential
from docx import Document
import os

# Azure OpenAI setup
client = AzureOpenAI(
    azure_endpoint="https://danielingitaraj.openai.azure.com/",
    api_key="a5c4e09a50dd4e13a69e7ef19d07b48c",
    api_version="2024-02-01",
)

# Function to use Azure Document Intelligence for PDF extraction
def extract_text_from_pdf(uploaded_pdf):
    endpoint = "https://patentocr.cognitiveservices.azure.com/"
    api_key = "cd6b8996d93447be88d995729c924bcb"

    document_analysis_client = DocumentAnalysisClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    )

    poller = document_analysis_client.begin_analyze_document(
        "prebuilt-document", document=uploaded_pdf
    )
    result = poller.result()

    text = ""
    for page in result.pages:
        for line in page.lines:
            text += line.content + "\n"
    
    return text

# Function to check for conflicts in the action document
def check_for_conflicts(action_document_text):
    prompt = f"""
    Analyze the following action document text and check for conflicts under Section 102 and 103:
    
    {action_document_text}
    
    Specifically, identify if Claim 1 is being anticipated by any referenced documents in the sections mentioned. 
    If there are conflicts, return the main claim and the names of the conflicting documents.
    """

    messages = [
        {
            "role": "system",
            "content": """  
            You are an expert in patent attorney.
            Analyze the following action document text and check for conflicts under Section 102 and 103:    
            Specifically, identify if Claim 1 (Root Claim) is being anticipated by any referenced documents in the sections mentioned. 
            If there are conflicts, return the main claim and the names of the conflicting documents.
            """,
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    response = client.chat.completions.create(
        model="GPT4", messages=messages, temperature=0
    )

    output = response.choices[0].message.content

    if "anticipated by" in output:
        claim = "Claim 1"
        documents = [doc.strip() for doc in output.split("anticipated by")[1].split(",")]
        return True, claim, documents

    return False, "", []

# Function to compare Claim 1 against other documents
# Function to compare Claim 1 and Original Document against other documents
def compare_claims(claim1_text, original_document_text, other_docs_texts):
    results = {}
    
    for doc_name, doc_text in other_docs_texts.items():
        # Compare Claim 1 with the document
        messages_claim1 = [
            {
                "role": "system",
                "content": """You are an expert patent attorney, analyzing patent claims based on Claim Rejections sections 102 and 103 of the US Patent Act.
                              Determine if the examiner is correct in asserting that Claim 1 is anticipated by the cited reference of 'Cited Reference' comparing with Application as filed as U.S pre-grant Publication document 'Claim 1'.""",
            },
            {
                "role": "user",
                "content": f"Determine if the examiner is correct in asserting that Claim 1 is anticipated by the cited reference. \n\nClaim 1: {claim1_text} \n\nCited Reference: {doc_text}",
            },
        ]

        response_claim1 = client.chat.completions.create(
            model="GPT4", messages=messages_claim1, temperature=0
        )

        # Compare Original Document with the document
        messages_original = [
            {
                "role": "system",
                "content": """You are an expert patent attorney, analyzing patent claims based on Claim Rejections sections 102 and 103 of the US Patent Act.
                              Determine if the examiner is correct in asserting that the original application document is anticipated by the cited reference.""",
            },
            {
                "role": "user",
                "content": f"Determine if the examiner is correct in asserting that the original application document is anticipated by the cited reference. \n\nOriginal Document: {original_document_text} \n\nCited Reference: {doc_text}",
            },
        ]

        response_original = client.chat.completions.create(
            model="GPT4", messages=messages_original, temperature=0
        )
        
        # Store both results under the same document name
        results[doc_name] = {
            "Claim 1 Comparison": response_claim1.choices[0].message.content,
            "Original Document Comparison": response_original.choices[0].message.content,
        }

    return results


# Function to generate Word document with results
def generate_word_doc(comparison_results):
    doc = Document()
    doc.add_heading("Patent Comparison Results", 0)
    
    for doc_name, result in comparison_results.items():
        doc.add_heading(f"Analysis for {doc_name}", level=1)
        doc.add_paragraph(result)
    
    doc_filename = "comparison_results.docx"
    doc.save(doc_filename)
    return doc_filename

# Streamlit App UI
st.title("Patent Key Claims Analysis")

# Initialize session state to store the uploaded files
if "action_document_pdf" not in st.session_state:
    st.session_state.action_document_pdf = None
if "original_document_pdf" not in st.session_state:
    st.session_state.original_document_pdf = None
if "other_documents_pdfs" not in st.session_state:
    st.session_state.other_documents_pdfs = []

if "conflict_detected" not in st.session_state:
    st.session_state.conflict_detected = False
if "claim_text" not in st.session_state:
    st.session_state.claim_text = None
if "conflict_docs" not in st.session_state:
    st.session_state.conflict_docs = []

# Upload the action document
st.sidebar.title("Upload Action Document (NFOA)")
uploaded_action_document = st.sidebar.file_uploader("Upload Action Document (NFOA) PDF", type=["pdf"])

# Analyze Action Document for Conflicts
if uploaded_action_document is not None and st.sidebar.button("Analyze Action Document"):
    st.session_state.action_document_pdf = uploaded_action_document
    action_document_text = extract_text_from_pdf(st.session_state.action_document_pdf)
    conflict_exists, claim_text, conflict_docs = check_for_conflicts(action_document_text)

    if conflict_exists:
        st.session_state.conflict_detected = True
        st.session_state.claim_text = claim_text
        st.session_state.conflict_docs = conflict_docs
        st.success(f"Key Claim detected for {uploaded_action_document.name}. Claim rejection documents: {', '.join(conflict_docs)}")
    else:
        st.error(f"No Key Claim detected for {uploaded_action_document.name}")

# After detecting conflict, ask for the original and conflicting documents
if st.session_state.conflict_detected:
    st.sidebar.title("Upload Documents for Comparison")
    
    # Upload Original Document
    original_document = st.sidebar.file_uploader("Upload Application as Filed Document PDF", type=["pdf"], key="original")

    if original_document is not None:
        st.session_state.original_document_pdf = original_document
    
    # Upload Other Documents (Batch Mode)
    other_documents = st.sidebar.file_uploader("Upload Claim rejection analysis Documents PDF (Batch Mode)", type=["pdf"], key="batch", accept_multiple_files=True)

    if other_documents:
        st.session_state.other_documents_pdfs = other_documents

    # Once documents are uploaded, enable comparison
    if st.session_state.original_document_pdf and st.session_state.other_documents_pdfs and st.sidebar.button("Compare Documents"):
        original_text = extract_text_from_pdf(st.session_state.original_document_pdf)
        other_docs_texts = {f"Claim rejection analysis {i+1}. {doc.name}": extract_text_from_pdf(doc) for i, doc in enumerate(st.session_state.other_documents_pdfs)}

        # Compare Claim 1 and Original Document against the other documents
        comparison_results = compare_claims(st.session_state.claim_text, original_text, other_docs_texts)

        # Generate the Word document with the comparison results
        doc_filename = generate_word_doc(comparison_results)

        # Display the comparison results
        for doc_name, results in comparison_results.items():
            st.subheader(f"Analysis with {doc_name}")
            st.write(f"**Claim 1 Comparison**: {results['Claim 1 Comparison']}")
            st.write(f"**Original Document Comparison**: {results['Original Document Comparison']}")

        # Provide download link for Word document
        with open(doc_filename, "rb") as f:
            st.download_button(
                label="Download Comparison Results",
                data=f,
                file_name=doc_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
